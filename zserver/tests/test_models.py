"""Tests for Django models: Job, Transaction, JobSummary."""

from django.test import TestCase

from zserver.models import Job, JobStatus, Transaction, JobSummary, RiskLevel


class TestJobStatusTransitions(TestCase):
    def setUp(self):
        self.job = Job.objects.create(filename="test.csv")

    def test_initial_status_is_pending(self):
        self.assertEqual(self.job.status, JobStatus.PENDING)

    def test_mark_processing(self):
        self.job.mark_processing()
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.PROCESSING)

    def test_mark_completed(self):
        self.job.mark_completed(row_count_raw=90, row_count_clean=85)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.COMPLETED)
        self.assertEqual(self.job.row_count_raw, 90)
        self.assertEqual(self.job.row_count_clean, 85)
        self.assertIsNotNone(self.job.completed_at)

    def test_mark_failed(self):
        self.job.mark_failed("something went wrong")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertEqual(self.job.error_message, "something went wrong")
        self.assertIsNotNone(self.job.completed_at)

    def test_str(self):
        self.assertIn("test.csv", str(self.job))


class TestTransactionModel(TestCase):
    def setUp(self):
        self.job = Job.objects.create(filename="test.csv")

    def test_create_transaction(self):
        txn = Transaction.objects.create(
            job        = self.job,
            txn_id     = "TXN001",
            date       = "2024-01-15",
            merchant   = "Swiggy",
            amount     = "150.00",
            currency   = "INR",
            status     = "SUCCESS",
            category   = "Food",
            account_id = "ACC1",
        )
        self.assertEqual(txn.merchant, "Swiggy")
        self.assertFalse(txn.is_anomaly)
        self.assertFalse(txn.llm_failed)

    def test_transaction_cascade_delete(self):
        Transaction.objects.create(
            job=self.job, txn_id="T1", merchant="X",
            currency="INR", status="SUCCESS", category="Food", account_id="A1",
        )
        job_id = self.job.id
        self.job.delete()
        self.assertEqual(Transaction.objects.filter(job_id=job_id).count(), 0)

    def test_str(self):
        txn = Transaction(txn_id="TXN001", merchant="Swiggy", amount=150, currency="INR")
        self.assertIn("TXN001", str(txn))


class TestJobSummaryModel(TestCase):
    def setUp(self):
        self.job = Job.objects.create(filename="test.csv")

    def test_create_summary(self):
        summary = JobSummary.objects.create(
            job             = self.job,
            total_spend_inr = "50000.00",
            total_spend_usd = "500.00",
            top_merchants   = {"Swiggy": 5000, "Amazon": 3000},
            anomaly_count   = 3,
            narrative       = "Test narrative.",
            risk_level      = RiskLevel.MEDIUM,
            category_spend  = [{"category": "Food", "total_spend": 5000}],
        )
        self.assertEqual(summary.risk_level, RiskLevel.MEDIUM)
        self.assertEqual(summary.top_merchants["Swiggy"], 5000)

    def test_one_to_one_constraint(self):
        JobSummary.objects.create(job=self.job)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            JobSummary.objects.create(job=self.job)

    def test_summary_cascade_delete(self):
        JobSummary.objects.create(job=self.job)
        job_id = self.job.id
        self.job.delete()
        self.assertEqual(JobSummary.objects.filter(job_id=job_id).count(), 0)

    def test_str(self):
        summary = JobSummary(job=self.job, risk_level="low")
        self.assertIn("risk", str(summary))
