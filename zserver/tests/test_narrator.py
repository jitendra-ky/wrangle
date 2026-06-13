"""Tests for LLMNarrativeBuilder."""

import json
from unittest.mock import MagicMock

import pandas as pd
from django.test import SimpleTestCase

from zserver.services.llm.narrator import LLMNarrativeBuilder
from zserver.services.llm.client import LLMError


def _make_processed_df() -> pd.DataFrame:
    return pd.DataFrame({
        "txn_id":     ["T1", "T2", "T3"],
        "merchant":   ["Swiggy", "Amazon", "MakeMyTrip"],
        "amount":     [100.0, 200.0, 5000.0],
        "currency":   ["INR", "USD", "INR"],
        "category":   ["Food", "Shopping", "Travel"],
        "is_anomaly": [False, False, True],
        "status":     ["SUCCESS", "SUCCESS", "PENDING"],
    })


def _llm_response() -> str:
    return json.dumps({
        "total_spend_inr": 5100.0,
        "total_spend_usd": 200.0,
        "top_merchants": {"MakeMyTrip": 5000.0, "Amazon": 200.0, "Swiggy": 100.0},
        "anomaly_count": 1,
        "narrative": "Test narrative.",
        "risk_level": "low",
    })


class TestNarrativeBuilderSuccess(SimpleTestCase):
    def test_returns_dict_with_required_keys(self):
        client = MagicMock()
        client.call.return_value = _llm_response()
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(_make_processed_df())
        for key in ("total_spend_inr", "total_spend_usd", "top_merchants",
                    "anomaly_count", "narrative", "risk_level", "category_spend"):
            self.assertIn(key, result, f"Missing key: {key}")

    def test_category_spend_always_present(self):
        client = MagicMock()
        client.call.return_value = _llm_response()
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(_make_processed_df())
        self.assertIsInstance(result["category_spend"], list)


class TestNarrativeBuilderFallback(SimpleTestCase):
    def test_llm_failure_returns_stub(self):
        client = MagicMock()
        client.call.side_effect = LLMError("API down")
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(_make_processed_df())
        self.assertIn("narrative", result)
        self.assertIn("risk_level", result)

    def test_json_decode_returns_stub(self):
        client = MagicMock()
        client.call.return_value = "not valid json"
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(_make_processed_df())
        self.assertIn("risk_level", result)

    def test_stub_risk_level_low_when_no_anomalies(self):
        df = _make_processed_df()
        df["is_anomaly"] = False
        client = MagicMock()
        client.call.side_effect = LLMError("fail")
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(df)
        self.assertEqual(result["risk_level"], "low")

    def test_stub_risk_level_medium(self):
        df = _make_processed_df()
        # Create 3 anomalies (2-5 range → medium)
        df = pd.concat([df] * 2, ignore_index=True)
        df["is_anomaly"] = [True, True, True, False, False, False]
        client = MagicMock()
        client.call.side_effect = LLMError("fail")
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(df)
        self.assertEqual(result["risk_level"], "medium")

    def test_stub_risk_level_high(self):
        df = _make_processed_df()
        df = pd.concat([df] * 3, ignore_index=True)
        df["is_anomaly"] = True  # 9 anomalies > 5 → high
        client = MagicMock()
        client.call.side_effect = LLMError("fail")
        builder = LLMNarrativeBuilder(client=client)
        result = builder.build(df)
        self.assertEqual(result["risk_level"], "high")
