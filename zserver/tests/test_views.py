"""
API endpoint tests for zserver.

Endpoints covered
─────────────────
GET  /health/
POST /jobs/upload
GET  /jobs/
GET  /jobs/<job_id>/status
GET  /jobs/<job_id>/results
"""

import io
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from zserver.models import Job, JobStatus, JobSummary, Transaction


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_csv_file(content: str = None, name: str = "test.csv") -> io.BytesIO:
    """Return an in-memory CSV file-like object."""
    if content is None:
        content = (
            "txn_id,date,merchant,amount,currency,status,category,account_id,notes\n"
            "TXN001,2024-01-10,Swiggy,150.00,INR,SUCCESS,Food,ACC1,\n"
            "TXN002,2024-01-11,Amazon,200.00,USD,SUCCESS,Shopping,ACC2,\n"
        )
    buf = io.BytesIO(content.encode())
    buf.name = name
    return buf


def _make_job(**kwargs) -> Job:
    """Create a minimal Job without an uploaded file."""
    return Job.objects.create(**kwargs)


def _make_completed_job() -> Job:
    """Create a fully-completed Job with transactions and a summary."""
    job = _make_job()
    job.mark_completed(row_count_raw=2, row_count_clean=2)

    Transaction.objects.create(
        job=job, txn_id="TXN001", date="2024-01-10",
        merchant="Swiggy", amount=Decimal("150.00"), currency="INR",
        status="SUCCESS", category="Food", account_id="ACC1",
        is_anomaly=False,
    )
    Transaction.objects.create(
        job=job, txn_id="TXN002", date="2024-01-11",
        merchant="Amazon", amount=Decimal("200.00"), currency="USD",
        status="SUCCESS", category="Shopping", account_id="ACC2",
        is_anomaly=True, anomaly_reason="currency mismatch",
    )
    JobSummary.objects.create(
        job=job,
        total_spend_inr=Decimal("15000.00"),
        total_spend_usd=Decimal("200.00"),
        top_merchants={"Swiggy": 150, "Amazon": 200},
        anomaly_count=1,
        narrative="Spending looks normal.",
        risk_level="low",
        category_spend=[{"category": "Food", "total_spend": 150}],
    )
    return job


# ── Health check ──────────────────────────────────────────────────────────────

class TestHealthCheck(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_200(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)

    def test_response_body(self):
        response = self.client.get("/health/")
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("service", data)

    def test_method_not_allowed_post(self):
        response = self.client.post("/health/")
        self.assertEqual(response.status_code, 405)


# ── POST /jobs/upload ─────────────────────────────────────────────────────────

class TestUploadJobNoFile(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_missing_file_returns_400(self):
        response = self.client.post("/jobs/upload", format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_missing_file_error_message(self):
        response = self.client.post("/jobs/upload", format="multipart")
        self.assertIn("error", response.json())

    def test_wrong_extension_returns_400(self):
        buf = io.BytesIO(b"col1,col2\n1,2")
        buf.name = "data.xlsx"
        response = self.client.post("/jobs/upload", {"file": buf}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_wrong_extension_error_message(self):
        buf = io.BytesIO(b"col1,col2\n1,2")
        buf.name = "data.xlsx"
        response = self.client.post("/jobs/upload", {"file": buf}, format="multipart")
        self.assertIn("error", response.json())

    def test_method_not_allowed_get(self):
        response = self.client.get("/jobs/upload")
        self.assertEqual(response.status_code, 405)


class TestUploadJobSuccess(TestCase):
    """Tests for a valid CSV upload — Celery task is stubbed out."""

    def setUp(self):
        self.client = APIClient()
        self.patcher = patch("zserver.views.process_job.delay")
        self.mock_delay = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_returns_202(self):
        response = self.client.post(
            "/jobs/upload", {"file": _make_csv_file()}, format="multipart"
        )
        self.assertEqual(response.status_code, 202)

    def test_response_contains_job_id(self):
        response = self.client.post(
            "/jobs/upload", {"file": _make_csv_file()}, format="multipart"
        )
        self.assertIn("job_id", response.json())

    def test_response_status_is_pending(self):
        response = self.client.post(
            "/jobs/upload", {"file": _make_csv_file()}, format="multipart"
        )
        self.assertEqual(response.json()["status"], "pending")

    def test_job_created_in_db(self):
        before = Job.objects.count()
        self.client.post(
            "/jobs/upload", {"file": _make_csv_file()}, format="multipart"
        )
        self.assertEqual(Job.objects.count(), before + 1)

    def test_celery_task_enqueued(self):
        response = self.client.post(
            "/jobs/upload", {"file": _make_csv_file()}, format="multipart"
        )
        job_id = response.json()["job_id"]
        self.mock_delay.assert_called_once_with(job_id)

    def test_csv_lowercase_extension_accepted(self):
        buf = _make_csv_file(name="data.CSV")
        response = self.client.post("/jobs/upload", {"file": buf}, format="multipart")
        self.assertEqual(response.status_code, 202)


# ── GET /jobs/ ────────────────────────────────────────────────────────────────

class TestListJobs(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.job1 = _make_job()
        self.job2 = _make_job()
        self.job2.mark_completed(row_count_raw=5, row_count_clean=5)

    def test_returns_200(self):
        response = self.client.get("/jobs/")
        self.assertEqual(response.status_code, 200)

    def test_returns_list(self):
        response = self.client.get("/jobs/")
        self.assertIsInstance(response.json(), list)

    def test_returns_all_jobs(self):
        response = self.client.get("/jobs/")
        self.assertEqual(len(response.json()), 2)

    def test_each_item_has_required_fields(self):
        response = self.client.get("/jobs/")
        item = response.json()[0]
        for field in ("id", "filename", "status", "row_count_raw", "row_count_clean", "created_at"):
            self.assertIn(field, item, f"Missing field: {field}")

    def test_filter_by_valid_status(self):
        response = self.client.get("/jobs/?status=completed")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["status"], "completed")

    def test_filter_by_pending(self):
        response = self.client.get("/jobs/?status=pending")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(all(j["status"] == "pending" for j in data))

    def test_filter_by_invalid_status_returns_400(self):
        response = self.client.get("/jobs/?status=unknown")
        self.assertEqual(response.status_code, 400)

    def test_filter_by_invalid_status_error_message(self):
        response = self.client.get("/jobs/?status=bogus")
        self.assertIn("error", response.json())

    def test_status_filter_is_case_insensitive(self):
        response = self.client.get("/jobs/?status=COMPLETED")
        self.assertEqual(response.status_code, 200)

    def test_method_not_allowed_post(self):
        response = self.client.post("/jobs/")
        self.assertEqual(response.status_code, 405)

    def test_empty_list_when_no_jobs(self):
        Job.objects.all().delete()
        response = self.client.get("/jobs/")
        self.assertEqual(response.json(), [])


# ── GET /jobs/<job_id>/status ─────────────────────────────────────────────────

class TestJobStatus(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.job = _make_job()

    def test_returns_200_for_existing_job(self):
        response = self.client.get(f"/jobs/{self.job.id}/status")
        self.assertEqual(response.status_code, 200)

    def test_returns_404_for_missing_job(self):
        response = self.client.get("/jobs/99999/status")
        self.assertEqual(response.status_code, 404)

    def test_404_error_message(self):
        response = self.client.get("/jobs/99999/status")
        self.assertIn("error", response.json())

    def test_pending_job_has_correct_status(self):
        response = self.client.get(f"/jobs/{self.job.id}/status")
        self.assertEqual(response.json()["status"], "pending")

    def test_response_has_required_fields(self):
        response = self.client.get(f"/jobs/{self.job.id}/status")
        data = response.json()
        for field in ("id", "filename", "status", "created_at", "completed_at", "error_message"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_pending_job_summary_is_null(self):
        response = self.client.get(f"/jobs/{self.job.id}/status")
        self.assertIsNone(response.json()["summary"])

    def test_completed_job_summary_is_populated(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/status")
        data = response.json()
        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data["summary"])

    def test_completed_job_summary_has_required_keys(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/status")
        summary = response.json()["summary"]
        for key in ("total_spend_inr", "total_spend_usd", "anomaly_count", "narrative", "risk_level"):
            self.assertIn(key, summary, f"Missing summary key: {key}")

    def test_failed_job_has_error_message(self):
        self.job.mark_failed("pipeline exploded")
        response = self.client.get(f"/jobs/{self.job.id}/status")
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_message"], "pipeline exploded")

    def test_method_not_allowed_post(self):
        response = self.client.post(f"/jobs/{self.job.id}/status")
        self.assertEqual(response.status_code, 405)


# ── GET /jobs/<job_id>/results ────────────────────────────────────────────────

class TestJobResults(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_returns_404_for_missing_job(self):
        response = self.client.get("/jobs/99999/results")
        self.assertEqual(response.status_code, 404)

    def test_404_error_message(self):
        response = self.client.get("/jobs/99999/results")
        self.assertIn("error", response.json())

    def test_pending_job_returns_202(self):
        job = _make_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertEqual(response.status_code, 202)

    def test_pending_job_response_has_status(self):
        job = _make_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertIn("status", response.json())

    def test_processing_job_returns_202(self):
        job = _make_job()
        job.mark_processing()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertEqual(response.status_code, 202)

    def test_failed_job_returns_202(self):
        job = _make_job()
        job.mark_failed("something broke")
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertEqual(response.status_code, 202)

    def test_completed_job_returns_200(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertEqual(response.status_code, 200)

    def test_completed_results_have_required_keys(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        data = response.json()
        for key in ("job_id", "cleaned_transactions", "anomalies", "category_spend", "llm_summary"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_job_id_in_results_matches(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertEqual(response.json()["job_id"], job.id)

    def test_cleaned_transactions_is_list(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertIsInstance(response.json()["cleaned_transactions"], list)

    def test_cleaned_transactions_count(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        # _make_completed_job creates 2 transactions
        self.assertEqual(len(response.json()["cleaned_transactions"]), 2)

    def test_anomalies_is_list(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertIsInstance(response.json()["anomalies"], list)

    def test_anomalies_count(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        # _make_completed_job marks 1 transaction as anomaly
        self.assertEqual(len(response.json()["anomalies"]), 1)

    def test_anomaly_txn_id_correct(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        anomaly_ids = [a["txn_id"] for a in response.json()["anomalies"]]
        self.assertIn("TXN002", anomaly_ids)

    def test_llm_summary_populated_when_summary_exists(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        summary = response.json()["llm_summary"]
        self.assertIn("narrative", summary)
        self.assertIn("risk_level", summary)

    def test_llm_summary_empty_when_no_summary(self):
        # Completed job but no JobSummary record
        job = _make_job()
        job.mark_completed(row_count_raw=0, row_count_clean=0)
        response = self.client.get(f"/jobs/{job.id}/results")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["llm_summary"], {})

    def test_transaction_fields_present(self):
        job = _make_completed_job()
        response = self.client.get(f"/jobs/{job.id}/results")
        txn = response.json()["cleaned_transactions"][0]
        for field in ("id", "txn_id", "merchant", "amount", "currency", "status",
                      "category", "is_anomaly"):
            self.assertIn(field, txn, f"Missing transaction field: {field}")

    def test_method_not_allowed_post(self):
        job = _make_completed_job()
        response = self.client.post(f"/jobs/{job.id}/results")
        self.assertEqual(response.status_code, 405)
