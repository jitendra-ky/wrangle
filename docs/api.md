# API Reference

Base URL (local dev): `http://localhost:8000`

---

## Endpoints

### `POST /jobs/upload`

Upload a CSV file to start a new processing job.

**Request**
```
Content-Type: multipart/form-data
Field: file  (the .csv file)
```

**Response — 202 Accepted**
```json
{ "job_id": 1, "status": "pending" }
```

**Response — 400 Bad Request**
```json
{ "error": "Invalid file type 'foo.txt'. Only .csv files are accepted." }
```

**curl example**
```bash
curl -X POST http://localhost:8000/jobs/upload \
     -F "file=@transactions.csv"
```

---

### `GET /jobs/`

List all jobs, most-recent first.

**Query params**

| Param | Values | Description |
|-------|--------|-------------|
| `status` | `pending \| processing \| completed \| failed` | Filter by job status |

**Response — 200 OK**
```json
[
  {
    "id": 1,
    "filename": "transactions.csv",
    "status": "completed",
    "row_count_raw": 90,
    "row_count_clean": 85,
    "created_at": "2025-01-01T10:00:00Z"
  }
]
```

**curl examples**
```bash
curl http://localhost:8000/jobs/
curl "http://localhost:8000/jobs/?status=completed"
```

---

### `GET /jobs/{job_id}/status`

Poll the current status of a job.  When the job is `completed`, the response includes a `summary` block.

**Response — 200 OK (processing)**
```json
{
  "id": 1,
  "filename": "transactions.csv",
  "status": "processing",
  "row_count_raw": null,
  "row_count_clean": null,
  "created_at": "2025-01-01T10:00:00Z",
  "completed_at": null,
  "error_message": "",
  "summary": null
}
```

**Response — 200 OK (completed)**
```json
{
  "id": 1,
  "filename": "transactions.csv",
  "status": "completed",
  "row_count_raw": 90,
  "row_count_clean": 85,
  "created_at": "2025-01-01T10:00:00Z",
  "completed_at": "2025-01-01T10:02:30Z",
  "error_message": "",
  "summary": {
    "total_spend_inr": "52000.00",
    "total_spend_usd": "1200.00",
    "top_merchants": { "Flipkart": 18000, "Swiggy": 5000, "Ola": 3200 },
    "anomaly_count": 10,
    "narrative": "Spending is concentrated in e-commerce with notable USD anomalies on domestic merchants.",
    "risk_level": "high",
    "category_spend": [
      { "category": "Shopping", "currency": "INR", "total_spend": 20000, "txn_count": 12 }
    ]
  }
}
```

**Response — 404 Not Found**
```json
{ "error": "Job 99 not found." }
```

**curl example**
```bash
curl http://localhost:8000/jobs/1/status
```

---

### `GET /jobs/{job_id}/results`

Retrieve the full pipeline output for a completed job.

**Response — 200 OK**
```json
{
  "job_id": 1,
  "cleaned_transactions": [
    {
      "id": 101,
      "txn_id": "TXN001",
      "date": "2024-01-15",
      "merchant": "Flipkart",
      "amount": "4999.00",
      "currency": "INR",
      "status": "SUCCESS",
      "category": "Shopping",
      "account_id": "ACC001",
      "notes": "",
      "is_anomaly": false,
      "anomaly_reason": "",
      "llm_category": "Shopping",
      "llm_failed": false
    }
  ],
  "anomalies": [...],
  "category_spend": [
    { "category": "Shopping", "currency": "INR", "total_spend": 20000, "txn_count": 12 }
  ],
  "llm_summary": {
    "total_spend_inr": "52000.00",
    "total_spend_usd": "1200.00",
    "top_merchants": { "Flipkart": 18000 },
    "anomaly_count": 10,
    "narrative": "...",
    "risk_level": "high"
  }
}
```

**Response — 202 Accepted** (job still pending or processing)
```json
{ "status": "processing", "message": "Results are not ready yet." }
```

**Response — 404 Not Found**
```json
{ "error": "Job 99 not found." }
```

**curl example**
```bash
curl http://localhost:8000/jobs/1/results
```

---

## Error Format

All errors return a JSON object with an `error` key:

```json
{ "error": "<human-readable message>" }
```

---

## Critical Next Step — Pagination on `GET /jobs/`

Currently `GET /jobs/` returns the **full list** of jobs in a single response.
This is fine for development but will degrade at scale.

**Recommended approach**: add DRF's `PageNumberPagination` (or `CursorPagination` for stable ordering):

```python
# zserver/pagination.py
from rest_framework.pagination import PageNumberPagination

class JobPagination(PageNumberPagination):
    page_size            = 20
    page_size_query_param = "page_size"
    max_page_size        = 100
```

Wire it into `list_jobs` via `pagination_class` on a class-based view, or apply
it manually in the function view with `paginator.paginate_queryset(qs, request)`.

The response would then follow the standard DRF envelope:
```json
{
  "count": 150,
  "next": "http://localhost:8000/jobs/?page=2",
  "previous": null,
  "results": [...]
}
```
