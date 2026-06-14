"""Integration tests for PipelineOrchestrator using the real transactions.csv."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from zserver.services.pipeline import PipelineOrchestrator, PipelineResult
from zserver.services.cleaner import DataCleaner
from zserver.services.anomaly import AnomalyDetector
from zserver.services.llm.classifier import LLMClassifier
from zserver.services.llm.narrator import LLMNarrativeBuilder

CSV_PATH = Path(__file__).resolve().parent / "fixtures" / "transactions.csv"



def _stub_classifier() -> LLMClassifier:
    """Classifier whose LLM always returns 'Other' for every txn_id."""
    client = MagicMock()

    def fake_call(prompt, **kwargs):
        # Parse txn_ids from the prompt and return {id: "Other"}
        import re
        ids = re.findall(r"txn_id=([\w]+)", prompt)
        return json.dumps({tid: "Other" for tid in ids})

    client.call.side_effect = fake_call
    return LLMClassifier(client=client)


def _stub_narrator() -> LLMNarrativeBuilder:
    """Narrator that always returns a fixed stub."""
    client = MagicMock()
    client.call.side_effect = Exception("stub")
    return LLMNarrativeBuilder(client=client)


class TestPipelineOrchestratorResult(SimpleTestCase):
    def setUp(self):
        self.orchestrator = PipelineOrchestrator(
            classifier=_stub_classifier(),
            narrator=_stub_narrator(),
        )

    def test_returns_pipeline_result(self):
        result = self.orchestrator.run(CSV_PATH)
        self.assertIsInstance(result, PipelineResult)

    def test_row_count_raw_positive(self):
        result = self.orchestrator.run(CSV_PATH)
        self.assertGreater(result.row_count_raw, 0)

    def test_row_count_clean_lte_raw(self):
        result = self.orchestrator.run(CSV_PATH)
        self.assertLessEqual(result.row_count_clean, result.row_count_raw)

    def test_cleaned_transactions_is_list_of_dicts(self):
        result = self.orchestrator.run(CSV_PATH)
        self.assertIsInstance(result.cleaned_transactions, list)
        self.assertIsInstance(result.cleaned_transactions[0], dict)

    def test_anomalies_subset_of_cleaned(self):
        result = self.orchestrator.run(CSV_PATH)
        anomaly_ids = {r["txn_id"] for r in result.anomalies}
        all_ids     = {r["txn_id"] for r in result.cleaned_transactions}
        self.assertTrue(anomaly_ids.issubset(all_ids))

    def test_category_spend_is_list(self):
        result = self.orchestrator.run(CSV_PATH)
        self.assertIsInstance(result.category_spend, list)

    def test_llm_summary_has_required_keys(self):
        result = self.orchestrator.run(CSV_PATH)
        for key in ("total_spend_inr", "total_spend_usd", "risk_level", "narrative"):
            self.assertIn(key, result.llm_summary, f"Missing summary key: {key}")

    def test_to_dict_serialisable(self):
        result = self.orchestrator.run(CSV_PATH)
        d = result.to_dict()
        # Should not raise
        json.dumps(d, default=str)


class TestPipelineOrchestratorCleaningApplied(SimpleTestCase):
    def setUp(self):
        self.orchestrator = PipelineOrchestrator(
            classifier=_stub_classifier(),
            narrator=_stub_narrator(),
        )

    def test_no_dollar_signs_in_amounts(self):
        result = self.orchestrator.run(CSV_PATH)
        for row in result.cleaned_transactions:
            amt = row.get("amount")
            if amt is not None:
                self.assertNotIn("$", str(amt))

    def test_all_currencies_uppercase(self):
        result = self.orchestrator.run(CSV_PATH)
        for row in result.cleaned_transactions:
            self.assertEqual(row["currency"], row["currency"].upper())

    def test_all_statuses_uppercase(self):
        result = self.orchestrator.run(CSV_PATH)
        for row in result.cleaned_transactions:
            self.assertEqual(row["status"], row["status"].upper())

    def test_no_blank_categories(self):
        result = self.orchestrator.run(CSV_PATH)
        for row in result.cleaned_transactions:
            self.assertTrue(row["category"])
