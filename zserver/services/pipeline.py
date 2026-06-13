"""
PipelineOrchestrator + PipelineResult
======================================
Single responsibility: wire all services together and return a typed result.

The orchestrator owns NO business logic — it only calls collaborators in order:
  1. Load CSV → raw DataFrame
  2. DataCleaner.clean()
  3. AnomalyDetector.detect()
  4. LLMClassifier.classify()
  5. LLMNarrativeBuilder.build()
  6. Package into PipelineResult

No Django imports — the Celery task (tasks.py) handles ORM persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .cleaner import DataCleaner
from .anomaly import AnomalyDetector
from .llm.client import LLMClient
from .llm.classifier import LLMClassifier
from .llm.narrator import LLMNarrativeBuilder


_OUTPUT_COLS = [
    "txn_id", "date", "merchant", "amount", "currency",
    "status", "category", "account_id", "notes",
    "is_anomaly", "anomaly_reason", "llm_category", "llm_failed",
]


@dataclass
class PipelineResult:
    """Immutable output bag returned by PipelineOrchestrator.run()."""

    row_count_raw:        int
    row_count_clean:      int
    cleaned_transactions: list[dict] = field(default_factory=list)
    anomalies:            list[dict] = field(default_factory=list)
    category_spend:       list[dict] = field(default_factory=list)
    llm_summary:          dict       = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "row_count_raw":        self.row_count_raw,
            "row_count_clean":      self.row_count_clean,
            "cleaned_transactions": self.cleaned_transactions,
            "anomalies":            self.anomalies,
            "category_spend":       self.category_spend,
            "llm_summary":          self.llm_summary,
        }


class PipelineOrchestrator:
    """
    Runs the full transaction processing pipeline.

    All collaborators are injected — pass mocks in tests.

    Parameters
    ----------
    cleaner    : DataCleaner instance.
    detector   : AnomalyDetector instance.
    classifier : LLMClassifier instance.
    narrator   : LLMNarrativeBuilder instance.
    """

    def __init__(
        self,
        cleaner:    DataCleaner            | None = None,
        detector:   AnomalyDetector        | None = None,
        classifier: LLMClassifier          | None = None,
        narrator:   LLMNarrativeBuilder    | None = None,
    ):
        client             = LLMClient()
        self.cleaner       = cleaner    or DataCleaner()
        self.detector      = detector   or AnomalyDetector()
        self.classifier    = classifier or LLMClassifier(client)
        self.narrator      = narrator   or LLMNarrativeBuilder(client)

    # ── Public interface ──────────────────────────────────────────────────────

    def run(self, csv_path: str | Path) -> PipelineResult:
        """
        Execute the full pipeline on *csv_path*.

        Parameters
        ----------
        csv_path : Path to the raw CSV file.

        Returns
        -------
        PipelineResult
        """
        csv_path = Path(csv_path)

        # 1. Load
        df_raw        = pd.read_csv(csv_path, dtype=str).dropna(how="all")
        row_count_raw = len(df_raw)

        # 2. Clean
        df = self.cleaner.clean(df_raw)

        # 3. Anomaly detection
        df = self.detector.detect(df)

        # 4. LLM classification
        df = self.classifier.classify(df)

        # 5. LLM narrative
        llm_summary = self.narrator.build(df)

        # 6. Package
        return self._build_result(df, row_count_raw, llm_summary)

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_result(
        self,
        df:            pd.DataFrame,
        row_count_raw: int,
        llm_summary:   dict,
    ) -> PipelineResult:
        out_cols = [c for c in _OUTPUT_COLS if c in df.columns]
        df_out   = df[out_cols].copy()

        # Serialise — convert numpy/pandas types to plain Python
        records    = self._to_records(df_out)
        anomalies  = self._to_records(df_out[df_out["is_anomaly"] == True])

        category_spend = llm_summary.pop("category_spend", [])

        return PipelineResult(
            row_count_raw        = row_count_raw,
            row_count_clean      = len(df_out),
            cleaned_transactions = records,
            anomalies            = anomalies,
            category_spend       = category_spend,
            llm_summary          = llm_summary,
        )

    @staticmethod
    def _to_records(df: pd.DataFrame) -> list[dict]:
        """Convert DataFrame to list of plain-Python dicts (safe for JSON)."""
        return [
            {
                k: (None if pd.isna(v) else (bool(v) if isinstance(v, (bool,)) else v))
                for k, v in row.items()
            }
            for row in df.to_dict(orient="records")
        ]
