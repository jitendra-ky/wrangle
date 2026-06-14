# Testing Guide

## Running the tests

All tests use Django's built-in test runner. No external services (Redis, Celery, LLM API) are required — they are stubbed out automatically.

> [!IMPORTANT]
> Always pass an explicit dotted label (e.g. `zserver.tests`).
> Running the bare `python manage.py test` **will crash** with an `ImportError`
> because Python's unittest discoverer finds `zserver/tests/` via filesystem
> traversal and tries to import it as a top-level `tests` module, which
> conflicts with the already-imported `zserver` package. Providing the label
> skips filesystem discovery and imports the module directly by its dotted path.

```bash
# ✅ Run the full test suite (always use the explicit label)
python manage.py test zserver.tests --settings=zproject.settings_dev

# ✅ Verbose output (shows each test name)
python manage.py test zserver.tests --settings=zproject.settings_dev -v 2

# ✅ Run a single test module
python manage.py test zserver.tests.test_views --settings=zproject.settings_dev

# ✅ Run a single test class
python manage.py test zserver.tests.test_views.TestUploadJobSuccess --settings=zproject.settings_dev

# ✅ Run a single test method
python manage.py test zserver.tests.test_views.TestUploadJobSuccess.test_returns_202 --settings=zproject.settings_dev

# ❌ Do NOT use — bare discovery crashes with an ImportError
# python manage.py test
```

> The test database is an **in-memory SQLite** instance created fresh on every run and destroyed afterwards. No data from `db.sqlite3` is touched.

---

## Test layout

```
zserver/tests/
├── __init__.py
├── test_anomaly.py     # AnomalyDetector rules
├── test_classifier.py  # LLMClassifier batching & error handling
├── test_cleaner.py     # DataCleaner transformations
├── test_models.py      # Django ORM models & status transitions
├── test_narrator.py    # LLMNarrativeBuilder success & fallback
├── test_pipeline.py    # PipelineOrchestrator end-to-end (uses real CSV)
└── test_views.py       # REST API endpoints (HTTP-level)
```

---

## What each suite covers

### `test_views.py` — API endpoints
Tests every endpoint at the HTTP level using DRF's `APIClient`.
Celery's `process_job.delay` is patched so uploads never touch Redis.

| Endpoint | Key scenarios tested |
|---|---|
| `GET /health/` | 200 response, body shape, 405 on POST |
| `POST /jobs/upload` | Missing file → 400, wrong extension → 400, valid CSV → 202, job created in DB, Celery task enqueued |
| `GET /jobs/` | Lists all jobs, `?status=` filter, invalid filter → 400, case-insensitive filter |
| `GET /jobs/<id>/status` | 200/404, pending/processing/failed/completed states, `summary` null vs populated |
| `GET /jobs/<id>/results` | 404, 202 while not completed, 200 when completed, full payload shape, anomaly sub-list |

### `test_models.py` — Django models
Covers `Job`, `Transaction`, and `JobSummary`:
- Default `status` is `pending`
- `mark_processing()`, `mark_completed()`, `mark_failed()` transitions
- Cascade deletes (Transaction and JobSummary removed when Job is deleted)
- One-to-one constraint on `JobSummary`

### `test_cleaner.py` — DataCleaner
Tests the CSV cleaning step in isolation:
- Date normalisation (DD-MM-YYYY, YYYY/MM/DD, ISO, invalid)
- Amount stripping (`$` sign, empty → NaN)
- Currency and status uppercasing
- Blank category → `"Uncategorised"`
- Synthetic IDs for blank `txn_id`
- Exact-duplicate removal

### `test_anomaly.py` — AnomalyDetector
- Statistical outlier rule (per-account IQR/median multiplier)
- Currency-mismatch rule (USD on a domestic-only merchant)
- Both rules combined append reasons with `|`
- Original DataFrame is never mutated

### `test_classifier.py` — LLMClassifier
- Successful batch → categories applied, `llm_category` set, `llm_failed=False`
- Invalid category name falls back to `"Other"`
- `LLMError` or bad JSON → `llm_failed=True`, no exception raised
- Already-categorised rows are skipped (LLM not called)
- Batching: `n` rows with `batch_size=k` produces `ceil(n/k)` calls

### `test_narrator.py` — LLMNarrativeBuilder
- Successful LLM call → dict with all required keys including `category_spend`
- `LLMError` or bad JSON → stub fallback (never raises)
- Stub `risk_level` derived from anomaly count: `low` (0–1), `medium` (2–5), `high` (>5)

### `test_pipeline.py` — PipelineOrchestrator (integration)
Runs the full pipeline against `local_assets/transactions.csv` with the LLM stubbed out.
- Returns a `PipelineResult`
- `row_count_raw > 0`, `row_count_clean ≤ row_count_raw`
- Anomalies are a subset of cleaned transactions
- Output is fully JSON-serialisable

---

## Adding new tests

1. Create (or add to) a file in `zserver/tests/`.
2. Subclass `django.test.TestCase` for tests that need the database, or `django.test.SimpleTestCase` for pure-logic tests.
3. Use `unittest.mock.patch` to stub Celery tasks, LLM calls, or file I/O.
4. Run `python manage.py test zserver.tests --settings=zproject.settings_dev` to verify.
