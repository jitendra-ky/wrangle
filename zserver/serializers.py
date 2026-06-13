"""
Serializers for zserver API.

JobListSerializer       – used by GET /jobs/
JobStatusSerializer     – used by GET /jobs/{id}/status
JobSummarySerializer    – nested inside JobStatusSerializer
TransactionSerializer   – used by GET /jobs/{id}/results
JobResultsSerializer    – assembles the full results response
"""

import os

from rest_framework import serializers

from .models import Job, JobSummary, Transaction


def _filename(job: Job) -> str:
    """Return just the basename of the uploaded file (e.g. 'transactions.csv')."""
    return os.path.basename(job.file.name) if job.file else ""


def _file_url(job: Job, request=None) -> str | None:
    """Return the fully-qualified URL to the uploaded file, or None."""
    if not job.file:
        return None
    try:
        url = job.file.url
        return request.build_absolute_uri(url) if request else url
    except ValueError:
        return None


# ── JobSummary ────────────────────────────────────────────────────────────────

class JobSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model  = JobSummary
        fields = [
            "total_spend_inr",
            "total_spend_usd",
            "top_merchants",
            "anomaly_count",
            "narrative",
            "risk_level",
            "category_spend",
        ]


# ── Job (list view) ───────────────────────────────────────────────────────────

class JobListSerializer(serializers.ModelSerializer):
    filename = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model  = Job
        fields = [
            "id",
            "filename",
            "file_url",
            "status",
            "row_count_raw",
            "row_count_clean",
            "created_at",
        ]

    def get_filename(self, job: Job) -> str:
        return _filename(job)

    def get_file_url(self, job: Job) -> str | None:
        return _file_url(job, self.context.get("request"))


# ── Job (status view) ─────────────────────────────────────────────────────────

class JobStatusSerializer(serializers.ModelSerializer):
    """
    Full job status.  When the job is completed, `summary` will be populated
    from the related JobSummary; otherwise it is null.
    """

    filename = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    summary  = serializers.SerializerMethodField()

    class Meta:
        model  = Job
        fields = [
            "id",
            "filename",
            "file_url",
            "status",
            "row_count_raw",
            "row_count_clean",
            "created_at",
            "completed_at",
            "error_message",
            "summary",
        ]

    def get_filename(self, job: Job) -> str:
        return _filename(job)

    def get_file_url(self, job: Job) -> str | None:
        return _file_url(job, self.context.get("request"))

    def get_summary(self, job: Job):
        """Return serialized JobSummary only when the job is completed."""
        if job.status != "completed":
            return None
        try:
            return JobSummarySerializer(job.summary).data
        except JobSummary.DoesNotExist:
            return None


# ── Transaction ───────────────────────────────────────────────────────────────

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Transaction
        fields = [
            "id",
            "txn_id",
            "date",
            "merchant",
            "amount",
            "currency",
            "status",
            "category",
            "account_id",
            "notes",
            "is_anomaly",
            "anomaly_reason",
            "llm_category",
            "llm_failed",
        ]


# ── Full results ──────────────────────────────────────────────────────────────

class JobResultsSerializer(serializers.Serializer):
    """
    Read-only composite serializer for GET /jobs/{id}/results.

    Accepts a dict built in the view:
        {
            "job_id":               int,
            "cleaned_transactions": list[Transaction],
            "anomalies":            list[Transaction],
            "category_spend":       list,
            "llm_summary":          dict,
        }
    """

    job_id                = serializers.IntegerField()
    cleaned_transactions  = TransactionSerializer(many=True)
    anomalies             = TransactionSerializer(many=True)
    category_spend        = serializers.ListField()
    llm_summary           = serializers.DictField()
