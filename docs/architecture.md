# Architecture

## Overview

The system is a Django REST Framework API that processes dirty financial CSV files through an AI-powered pipeline.

```
CSV Upload → Job (DB) → Celery Task → Pipeline → Results (DB)
```

All business logic lives in `zserver/services/` — **no Django imports** inside services, so every class is independently testable.

---

## Directory Structure

```
zserver/
├── models.py               # ORM: Job, Transaction, JobSummary
├── tasks.py                # Celery task stub (process_job)
├── views.py                # DRF API endpoints
└── services/
    ├── cleaner.py          # DataCleaner
    ├── anomaly.py          # AnomalyDetector
    ├── pipeline.py         # PipelineOrchestrator + PipelineResult
    └── llm/
        ├── client.py       # LLMClient  (Gemini SDK + retry)
        ├── classifier.py   # LLMClassifier  (batch categorise)
        └── narrator.py     # LLMNarrativeBuilder  (summary call)
```

---

## Class Diagram

```mermaid
classDiagram
    direction TB

    class PipelineOrchestrator {
        -cleaner: DataCleaner
        -detector: AnomalyDetector
        -classifier: LLMClassifier
        -narrator: LLMNarrativeBuilder
        +run(csv_path: Path) PipelineResult
        -_build_result(df, row_count_raw, llm_summary) PipelineResult
        -_to_records(df) list
    }

    class PipelineResult {
        +row_count_raw: int
        +row_count_clean: int
        +cleaned_transactions: list
        +anomalies: list
        +category_spend: list
        +llm_summary: dict
        +to_dict() dict
    }

    class DataCleaner {
        +clean(df: DataFrame) DataFrame
        -_strip_whitespace(df)
        -_normalise_dates(df)
        -_clean_amounts(df)
        -_uppercase_fields(df)
        -_fill_missing_category(df)
        -_assign_synthetic_ids(df)
        -_remove_duplicates(df)
    }

    class AnomalyDetector {
        -outlier_multiplier: float
        -domestic_merchants: frozenset
        +detect(df: DataFrame) DataFrame
        -_flag_statistical_outliers(df)
        -_flag_currency_mismatches(df)
        -_append_reason(df, idx, reason)
    }

    class LLMClient {
        -model_name: str
        -max_retries: int
        -backoff_base: float
        +call(prompt: str, expect_json: bool) str
        -_with_retry(prompt)
        -_invoke(prompt)
    }

    class LLMClassifier {
        -client: LLMClient
        -valid_categories: list
        -batch_size: int
        +classify(df: DataFrame) DataFrame
        -_process_batch(df, batch_idx)
        -_build_prompt(batch_df)
    }

    class LLMNarrativeBuilder {
        -client: LLMClient
        +build(df: DataFrame) dict
        -_compute_stats(df)
        -_build_prompt(stats)
        -_compute_stub(stats)
    }

    PipelineOrchestrator --> DataCleaner
    PipelineOrchestrator --> AnomalyDetector
    PipelineOrchestrator --> LLMClassifier
    PipelineOrchestrator --> LLMNarrativeBuilder
    PipelineOrchestrator ..> PipelineResult : returns

    LLMClassifier --> LLMClient
    LLMNarrativeBuilder --> LLMClient
```

---

## Design Principles

| Principle | How it's applied |
|---|---|
| **Single Responsibility** | Each class does exactly one thing — `DataCleaner` only cleans, `AnomalyDetector` only flags, etc. |
| **Dependency Injection** | `PipelineOrchestrator`, `LLMClassifier`, and `LLMNarrativeBuilder` all accept collaborators in `__init__` — swap mocks in tests |
| **Open/Closed** | Add a new anomaly rule by adding a private method to `AnomalyDetector` — callers unchanged |
| **No Django in services** | `zserver/services/` has zero ORM imports — pure pandas/stdlib, independently testable |
