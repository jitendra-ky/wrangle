"""Tests for LLMClassifier."""

import json
from unittest.mock import MagicMock

import pandas as pd
from django.test import SimpleTestCase

from zserver.services.llm.classifier import LLMClassifier
from zserver.services.llm.client import LLMError


def _make_uncat_df() -> pd.DataFrame:
    return pd.DataFrame({
        "txn_id":   ["T1", "T2", "T3"],
        "merchant": ["Swiggy", "Amazon", "MakeMyTrip"],
        "amount":   [100.0, 200.0, 5000.0],
        "currency": ["INR", "USD", "INR"],
        "category": ["Uncategorised", "Uncategorised", "Uncategorised"],
        "notes":    ["", "", ""],
    })


def _mock_client(response: str) -> MagicMock:
    client = MagicMock()
    client.call.return_value = response
    return client


class TestLLMClassifierSuccess(SimpleTestCase):
    def test_categories_applied(self):
        payload = json.dumps({"T1": "Food", "T2": "Shopping", "T3": "Travel"})
        classifier = LLMClassifier(client=_mock_client(payload), batch_size=10)
        df = classifier.classify(_make_uncat_df())
        self.assertEqual(df.loc[0, "category"], "Food")
        self.assertEqual(df.loc[1, "category"], "Shopping")
        self.assertEqual(df.loc[2, "category"], "Travel")

    def test_llm_category_column_set(self):
        payload = json.dumps({"T1": "Food", "T2": "Shopping", "T3": "Travel"})
        classifier = LLMClassifier(client=_mock_client(payload), batch_size=10)
        df = classifier.classify(_make_uncat_df())
        self.assertEqual(df.loc[0, "llm_category"], "Food")

    def test_llm_failed_false_on_success(self):
        payload = json.dumps({"T1": "Food", "T2": "Shopping", "T3": "Travel"})
        classifier = LLMClassifier(client=_mock_client(payload), batch_size=10)
        df = classifier.classify(_make_uncat_df())
        self.assertFalse(df["llm_failed"].any())

    def test_invalid_category_falls_back_to_other(self):
        payload = json.dumps({"T1": "NotACategory", "T2": "Shopping", "T3": "Travel"})
        classifier = LLMClassifier(client=_mock_client(payload), batch_size=10)
        df = classifier.classify(_make_uncat_df())
        self.assertEqual(df.loc[0, "category"], "Other")


class TestLLMClassifierFailure(SimpleTestCase):
    def test_llm_error_marks_batch_failed(self):
        client = MagicMock()
        client.call.side_effect = LLMError("API down")
        classifier = LLMClassifier(client=client, batch_size=10)
        df = classifier.classify(_make_uncat_df())
        self.assertTrue(df["llm_failed"].all())

    def test_json_decode_error_marks_batch_failed(self):
        client = _mock_client("this is not json")
        classifier = LLMClassifier(client=client, batch_size=10)
        df = classifier.classify(_make_uncat_df())
        self.assertTrue(df["llm_failed"].all())

    def test_failure_does_not_raise(self):
        client = MagicMock()
        client.call.side_effect = LLMError("fail")
        classifier = LLMClassifier(client=client, batch_size=10)
        # Should NOT raise — pipeline must continue
        try:
            classifier.classify(_make_uncat_df())
        except Exception as e:
            self.fail(f"classify() raised unexpectedly: {e}")


class TestLLMClassifierSkipsAlreadyCategorised(SimpleTestCase):
    def test_already_categorised_rows_skipped(self):
        df = pd.DataFrame({
            "txn_id":   ["T1"],
            "merchant": ["Swiggy"],
            "amount":   [100.0],
            "currency": ["INR"],
            "category": ["Food"],   # already set
            "notes":    [""],
        })
        client = MagicMock()
        classifier = LLMClassifier(client=client, batch_size=10)
        result = classifier.classify(df)
        client.call.assert_not_called()
        self.assertEqual(result.loc[0, "category"], "Food")


class TestLLMClassifierBatching(SimpleTestCase):
    def test_batches_correctly(self):
        n = 5
        df = pd.DataFrame({
            "txn_id":   [f"T{i}" for i in range(n)],
            "merchant": ["X"] * n,
            "amount":   [100.0] * n,
            "currency": ["INR"] * n,
            "category": ["Uncategorised"] * n,
            "notes":    [""] * n,
        })
        payload = json.dumps({f"T{i}": "Other" for i in range(n)})
        client = _mock_client(payload)
        classifier = LLMClassifier(client=client, batch_size=2)
        classifier.classify(df)
        # 5 rows ÷ batch_size 2 = 3 calls
        self.assertEqual(client.call.call_count, 3)
