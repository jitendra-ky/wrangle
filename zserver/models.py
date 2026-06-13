import os

from django.db import models
from django.utils import timezone


class JobStatus(models.TextChoices):
    PENDING    = "pending",    "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED  = "completed",  "Completed"
    FAILED     = "failed",     "Failed"


class Job(models.Model):
    """Tracks a single CSV upload and its pipeline run."""

    file          = models.FileField(upload_to="uploads/", blank=True)
    status        = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
    )
    row_count_raw   = models.IntegerField(null=True, blank=True)
    row_count_clean = models.IntegerField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    completed_at    = models.DateTimeField(null=True, blank=True)
    error_message   = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job({self.id}, {os.path.basename(self.file.name)}, {self.status})"

    # ── Status transitions ────────────────────────────────────────────────────

    def mark_processing(self):
        self.status = JobStatus.PROCESSING
        self.save(update_fields=["status"])

    def mark_completed(self, row_count_raw: int, row_count_clean: int):
        self.status          = JobStatus.COMPLETED
        self.row_count_raw   = row_count_raw
        self.row_count_clean = row_count_clean
        self.completed_at    = timezone.now()
        self.save(update_fields=["status", "row_count_raw", "row_count_clean", "completed_at"])

    def mark_failed(self, error: str):
        self.status        = JobStatus.FAILED
        self.error_message = error
        self.completed_at  = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at"])


class Transaction(models.Model):
    """One cleaned & enriched row from the uploaded CSV."""

    job           = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="transactions")
    txn_id        = models.CharField(max_length=50)
    date          = models.DateField(null=True, blank=True)
    merchant      = models.CharField(max_length=200)
    amount        = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency      = models.CharField(max_length=3)
    status        = models.CharField(max_length=20)
    category      = models.CharField(max_length=50)
    account_id    = models.CharField(max_length=50)
    notes         = models.TextField(blank=True, default="")

    # Pipeline-output columns
    is_anomaly      = models.BooleanField(default=False)
    anomaly_reason  = models.TextField(blank=True, default="")
    llm_category    = models.CharField(max_length=50, null=True, blank=True)
    llm_failed      = models.BooleanField(default=False)

    class Meta:
        ordering = ["date", "txn_id"]

    def __str__(self):
        return f"Transaction({self.txn_id}, {self.merchant}, {self.amount} {self.currency})"


class RiskLevel(models.TextChoices):
    LOW    = "low",    "Low"
    MEDIUM = "medium", "Medium"
    HIGH   = "high",   "High"


class JobSummary(models.Model):
    """LLM-generated summary produced once the pipeline completes."""

    job             = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="summary")
    total_spend_inr = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_spend_usd = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    top_merchants   = models.JSONField(default=dict)   # {merchant: total_spend}
    anomaly_count   = models.IntegerField(default=0)
    narrative       = models.TextField(blank=True, default="")
    risk_level      = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW,
    )
    category_spend  = models.JSONField(default=list)   # [{category, currency, total_spend, txn_count}]

    def __str__(self):
        return f"JobSummary(job={self.job_id}, risk={self.risk_level})"
