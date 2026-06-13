"""
API views for zserver.

Endpoints
─────────
POST  /jobs/upload           – upload CSV, create Job, enqueue pipeline
GET   /jobs/                 – list all jobs (supports ?status= filter)
GET   /jobs/<job_id>/status  – poll job status + summary when completed
GET   /jobs/<job_id>/results – full results: transactions, anomalies, narrative
"""

from __future__ import annotations

import logging
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import Job, JobSummary, Transaction
from .serializers import (
    JobListSerializer,
    JobResultsSerializer,
    JobStatusSerializer,
)
from .tasks import process_job

logger = logging.getLogger(__name__)


# ── Health check (already mounted at /health/ in zproject/urls.py) ────────────

@api_view(["GET"])
def health_check(request):
    return Response({"status": "healthy", "service": "wrangle-api"}, status=status.HTTP_200_OK)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_job_or_404(job_id: int):
    """Return (Job, None) or (None, 404 Response)."""
    try:
        return Job.objects.get(pk=job_id), None
    except Job.DoesNotExist:
        return None, Response(
            {"error": f"Job {job_id} not found."},
            status=status.HTTP_404_NOT_FOUND,
        )


# ── POST /jobs/upload ─────────────────────────────────────────────────────────

@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload_job(request):
    """
    Accept a CSV file upload, create a Job record, and enqueue the pipeline.

    Request  : multipart/form-data  { file: <csv file> }
    Response : 202  { job_id, status }
               400  { error }  – if no file or wrong extension
    """
    csv_file = request.FILES.get("file")

    if csv_file is None:
        return Response(
            {"error": "No file uploaded. Send the CSV as multipart field 'file'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not csv_file.name.lower().endswith(".csv"):
        return Response(
            {"error": f"Invalid file type '{csv_file.name}'. Only .csv files are accepted."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Create the Job record (Django FileField saves the file automatically) ──
    job = Job.objects.create(file=csv_file)

    # ── Enqueue the Celery task ───────────────────────────────────────────────
    process_job.delay(job.id)
    logger.info("upload_job: enqueued job %s for file '%s'", job.id, job.file.name)

    return Response(
        {"job_id": job.id, "status": job.status},
        status=status.HTTP_202_ACCEPTED,
    )


# ── GET /jobs/ ────────────────────────────────────────────────────────────────

@api_view(["GET"])
def list_jobs(request):
    """
    List all jobs, ordered by most-recent first.

    Query params
    ────────────
    ?status=pending|processing|completed|failed   – optional filter

    Response : 200  [ { id, filename, status, row_count_raw,
                         row_count_clean, created_at }, … ]
               400  { error }  – if ?status value is invalid
    """
    VALID_STATUSES = {"pending", "processing", "completed", "failed"}

    qs = Job.objects.all()

    status_filter = request.query_params.get("status")
    if status_filter is not None:
        status_filter = status_filter.lower()
        if status_filter not in VALID_STATUSES:
            return Response(
                {
                    "error": (
                        f"Invalid status '{status_filter}'. "
                        f"Choose from: {', '.join(sorted(VALID_STATUSES))}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(status=status_filter)

    serializer = JobListSerializer(qs, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ── GET /jobs/<job_id>/status ─────────────────────────────────────────────────

@api_view(["GET"])
def job_status(request, job_id: int):
    """
    Return current job status.  When the job is completed the response
    includes a `summary` block with high-level stats.

    Response : 200  { id, filename, status, row_count_raw, row_count_clean,
                       created_at, completed_at, error_message, summary|null }
               404  { error }
    """
    job, err = _get_job_or_404(job_id)
    if err:
        return err

    serializer = JobStatusSerializer(job)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ── GET /jobs/<job_id>/results ────────────────────────────────────────────────

@api_view(["GET"])
def job_results(request, job_id: int):
    """
    Return full pipeline output for a completed job.

    Response : 200  { job_id, cleaned_transactions, anomalies,
                       category_spend, llm_summary }
               202  { status }  – job still pending / processing
               404  { error }   – job not found
    """
    job, err = _get_job_or_404(job_id)
    if err:
        return err

    if job.status != "completed":
        return Response(
            {"status": job.status, "message": "Results are not ready yet."},
            status=status.HTTP_202_ACCEPTED,
        )

    transactions = Transaction.objects.filter(job=job)
    anomalies    = transactions.filter(is_anomaly=True)

    try:
        summary = job.summary
        llm_summary = {
            "total_spend_inr": str(summary.total_spend_inr),
            "total_spend_usd": str(summary.total_spend_usd),
            "top_merchants":   summary.top_merchants,
            "anomaly_count":   summary.anomaly_count,
            "narrative":       summary.narrative,
            "risk_level":      summary.risk_level,
        }
        category_spend = summary.category_spend
    except JobSummary.DoesNotExist:
        llm_summary    = {}
        category_spend = []

    payload = {
        "job_id":               job.id,
        "cleaned_transactions": list(transactions),
        "anomalies":            list(anomalies),
        "category_spend":       category_spend,
        "llm_summary":          llm_summary,
    }

    serializer = JobResultsSerializer(payload)
    return Response(serializer.data, status=status.HTTP_200_OK)