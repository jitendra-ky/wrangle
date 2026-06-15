# AI-Powered Transaction Processing Pipeline

This project is a backend API that accepts a CSV file of raw financial transactions, processes it asynchronously through a job queue, uses an LLM to classify transactions and flag anomalies, and generates a structured summary report.

## Tech Stack
- **Framework**: Django REST Framework
- **Database**: PostgreSQL
- **Job Queue**: Celery + Redis
- **LLM**: Google Gemini API
- **Containerisation**: Docker & Docker Compose

## Prerequisites
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Setup Instructions

1. **Environment Variables**: 
   Ensure you have a `.env.docker` file in the root directory (or edit the existing one) to provide your Gemini API key:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
   *(Note: The `docker-compose.yml` is configured to automatically load `.env.docker`).*

2. **Start the Application**:
   Run the entire stack with a single command. This will spin up PostgreSQL, Redis, the Django API (on port `8000`), and the Celery worker without any manual setup steps:
   ```bash
   docker compose up --build -d
   ```

## API Documentation & Examples

### 1. Upload Transactions CSV
Accepts a CSV file upload, validates it, creates a Job record, and enqueues the processing task.

**Endpoint:** `POST /jobs/upload`

**Example Request:**
```bash
curl -X POST http://localhost:8000/jobs/upload \
  -F "file=@local_assets/transactions.csv"
```

### 2. List All Jobs
List all jobs with their status, filename, row count, and creation timestamp. Supports optional filtering by status.

**Endpoint:** `GET /jobs/` (or `GET /jobs/?status=completed`)

**Example Request:**
```bash
curl -X GET "http://localhost:8000/jobs/"
```

### 3. Check Job Status
Return the current status of the job (`pending`, `processing`, `completed`, or `failed`). If completed, it also includes a high-level summary.

**Endpoint:** `GET /jobs/<job_id>/status`

**Example Request:**
```bash
curl -X GET "http://localhost:8000/jobs/1/status"
```

### 4. Get Job Results
Return the full structured output: cleaned transactions list, flagged anomalies, per-category spend breakdown, and the LLM-generated narrative summary.

**Endpoint:** `GET /jobs/<job_id>/results`

**Example Request:**
```bash
curl -X GET "http://localhost:8000/jobs/1/results"
```

## Submission Details
- **[System Design Diagram](https://drive.google.com/file/d/1Xyu8lzipk673td7jcRY_TLAPQ7sxdKAs/view?usp=sharing)**

## 3-Minute Technical Video Review**
https://youtu.be/ZOb_ZmaFAww
