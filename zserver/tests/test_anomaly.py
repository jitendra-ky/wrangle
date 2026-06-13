"""Tests for AnomalyDetector."""

import pandas as pd
from django.test import SimpleTestCase

from zserver.services.anomaly import AnomalyDetector


def _make_df(amounts, currencies, merchants, account_ids=None) -> pd.DataFrame:
    n = len(amounts)
    return pd.DataFrame({
        "txn_id":     [f"T{i}" for i in range(n)],
        "amount":     amounts,
        "currency":   currencies,
        "merchant":   merchants,
        "account_id": account_ids or ["ACC1"] * n,
    })


class TestStatisticalOutlier(SimpleTestCase):
    def setUp(self):
        self.detector = AnomalyDetector(outlier_multiplier=3.0)

    def test_outlier_flagged(self):
        # median of [100, 100, 100] = 100; 400 > 3*100 → outlier
        df = _make_df([100, 100, 100, 400], ["INR"] * 4, ["Swiggy"] * 4)
        result = self.detector.detect(df)
        self.assertTrue(result.loc[3, "is_anomaly"])
        self.assertIn("account median", result.loc[3, "anomaly_reason"])

    def test_normal_not_flagged(self):
        df = _make_df([100, 110, 90, 105], ["INR"] * 4, ["Amazon"] * 4)
        result = self.detector.detect(df)
        self.assertFalse(result["is_anomaly"].any())

    def test_each_account_uses_own_median(self):
        # ACC1 median=100, ACC2 median=1000 — only ACC1's 350 is an outlier
        df = pd.DataFrame({
            "txn_id":     ["T0", "T1", "T2", "T3"],
            "amount":     [100.0, 100.0, 1000.0, 350.0],
            "currency":   ["INR"] * 4,
            "merchant":   ["X"] * 4,
            "account_id": ["ACC1", "ACC1", "ACC2", "ACC1"],
        })
        result = self.detector.detect(df)
        # T3 (350 > 3*100) should be flagged; T2 (1000 is the only ACC2 row) is not
        self.assertTrue(result.loc[3, "is_anomaly"])
        self.assertFalse(result.loc[2, "is_anomaly"])


class TestCurrencyMismatch(SimpleTestCase):
    def setUp(self):
        self.detector = AnomalyDetector()

    def test_usd_on_domestic_flagged(self):
        df = _make_df([100.0], ["USD"], ["Swiggy"])
        result = self.detector.detect(df)
        self.assertTrue(result.loc[0, "is_anomaly"])
        self.assertIn("domestic-only", result.loc[0, "anomaly_reason"])

    def test_inr_on_domestic_not_flagged(self):
        df = _make_df([100.0], ["INR"], ["Swiggy"])
        result = self.detector.detect(df)
        self.assertFalse(result.loc[0, "is_anomaly"])

    def test_usd_on_foreign_merchant_not_flagged(self):
        df = _make_df([100.0], ["USD"], ["Amazon"])
        result = self.detector.detect(df)
        self.assertFalse(result.loc[0, "is_anomaly"])

    def test_custom_domestic_merchants(self):
        detector = AnomalyDetector(domestic_merchants=frozenset({"testmerchant"}))
        df = _make_df([100.0], ["USD"], ["TestMerchant"])
        result = detector.detect(df)
        self.assertTrue(result.loc[0, "is_anomaly"])


class TestBothRulesCombined(SimpleTestCase):
    def test_both_reasons_appended(self):
        # median of [100, 100] = 100; 500 > 300 → outlier + USD on swiggy
        df = pd.DataFrame({
            "txn_id":     ["T0", "T1", "T2"],
            "amount":     [100.0, 100.0, 500.0],
            "currency":   ["INR", "INR", "USD"],
            "merchant":   ["Amazon", "Amazon", "Swiggy"],
            "account_id": ["ACC1", "ACC1", "ACC1"],
        })
        detector = AnomalyDetector(outlier_multiplier=3.0)
        result = detector.detect(df)
        self.assertTrue(result.loc[2, "is_anomaly"])
        self.assertIn("|", result.loc[2, "anomaly_reason"])


class TestDetectAddsColumns(SimpleTestCase):
    def test_columns_always_added(self):
        df = _make_df([50.0], ["INR"], ["Flipkart"])
        result = AnomalyDetector().detect(df)
        self.assertIn("is_anomaly", result.columns)
        self.assertIn("anomaly_reason", result.columns)

    def test_original_df_not_mutated(self):
        df = _make_df([50.0], ["INR"], ["Flipkart"])
        AnomalyDetector().detect(df)
        self.assertNotIn("is_anomaly", df.columns)
