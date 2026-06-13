"""
Celery tasks for zserver.

process_job:
  1. Loads Job from DB
  2. Calls PipelineOrchestrator.run()
  3. Persists PipelineResult → Transaction rows + JobSummary
  4. Updates Job status
"""

from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task

from zserver.models import Job, JobStatus, Transaction, JobSummary
from zserver.services.pipeline import PipelineOrchestrator

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="zserver.process_job")
def process_job(self, job_id: int) -> None:
    """
    Run the pipeline for *job_id* and persist results.

    Parameters
    ----------
    job_id : PK of the Job record.  The CSV path is derived from job.file.path.
    """
    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        logger.error("process_job: Job %s not found", job_id)
        return

    job.mark_processing()
    logger.info("process_job: starting pipeline for job %s", job_id)

    try:
        csv_path = job.file.path
        result = PipelineOrchestrator().run(csv_path)
        _persist_result(job, result)
        job.mark_completed(result.row_count_raw, result.row_count_clean)
        logger.info("process_job: completed job %s", job_id)

    except Exception as exc:
        logger.exception("process_job: pipeline failed for job %s", job_id)
        job.mark_failed(str(exc))


# ── Private helpers ───────────────────────────────────────────────────────────

def _persist_result(job: Job, result) -> None:
    """Bulk-create Transaction rows and create JobSummary."""
    transactions = [
        Transaction(
            job           = job,
            txn_id        = row.get("txn_id") or "",
            date          = row.get("date"),
            merchant      = row.get("merchant") or "",
            amount        = Decimal(str(row["amount"])) if row.get("amount") is not None else None,
            currency      = row.get("currency") or "",
            status        = row.get("status") or "",
            category      = row.get("category") or "",
            account_id    = row.get("account_id") or "",
            notes         = row.get("notes") or "",
            is_anomaly     = bool(row.get("is_anomaly", False)),
            anomaly_reason = row.get("anomaly_reason") or "",
            llm_category   = row.get("llm_category"),
            llm_failed     = bool(row.get("llm_failed", False)),
        )
        for row in result.cleaned_transactions
    ]
    Transaction.objects.bulk_create(transactions)

    summary = result.llm_summary
    JobSummary.objects.create(
        job             = job,
        total_spend_inr = Decimal(str(summary.get("total_spend_inr", 0))),
        total_spend_usd = Decimal(str(summary.get("total_spend_usd", 0))),
        top_merchants   = summary.get("top_merchants", {}),
        anomaly_count   = int(summary.get("anomaly_count", 0)),
        narrative       = summary.get("narrative", ""),
        risk_level      = summary.get("risk_level", "low"),
        category_spend  = result.category_spend,
    )
