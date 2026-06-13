"""Tests for DataCleaner."""

import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from zserver.services.cleaner import DataCleaner


def _make_df(**overrides) -> pd.DataFrame:
    """Return a minimal valid raw DataFrame."""
    base = {
        "txn_id":     ["TXN001", "TXN002", ""],
        "date":       ["04-09-2024", "2024/02/05", "2024-07-15"],
        "merchant":   ["Swiggy", "Amazon", "Zomato"],
        "amount":     ["150.00", "$200.50", "300"],
        "currency":   ["inr", "usd", "INR"],
        "status":     ["success", "FAILED", "pending"],
        "category":   ["Food", "", ""],
        "account_id": ["ACC1", "ACC2", "ACC1"],
        "notes":      ["", "Duplicate?", "SUSPICIOUS"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class TestDataCleanerDates(SimpleTestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_dd_mm_yyyy_format(self):
        df = _make_df(date=["04-09-2024", "04-09-2024", "04-09-2024"])
        result = self.cleaner.clean(df)
        self.assertEqual(result["date"].iloc[0], "2024-09-04")

    def test_yyyy_slash_mm_slash_dd_format(self):
        df = _make_df(date=["2024/02/05", "2024/02/05", "2024/02/05"])
        result = self.cleaner.clean(df)
        self.assertEqual(result["date"].iloc[0], "2024-02-05")

    def test_already_iso_format(self):
        df = _make_df(date=["2024-07-15", "2024-07-15", "2024-07-15"])
        result = self.cleaner.clean(df)
        self.assertEqual(result["date"].iloc[0], "2024-07-15")

    def test_invalid_date_flagged(self):
        df = _make_df(date=["not-a-date", "not-a-date", "not-a-date"])
        result = self.cleaner.clean(df)
        self.assertTrue(result["date"].iloc[0].startswith("INVALID:"))


class TestDataCleanerAmounts(SimpleTestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_strips_dollar_sign(self):
        df = _make_df(amount=["$200.50", "$200.50", "$200.50"])
        result = self.cleaner.clean(df)
        self.assertAlmostEqual(float(result["amount"].iloc[0]), 200.50)

    def test_plain_number_unchanged(self):
        df = _make_df(amount=["150.00", "150.00", "150.00"])
        result = self.cleaner.clean(df)
        self.assertAlmostEqual(float(result["amount"].iloc[0]), 150.00)

    def test_empty_amount_is_nan(self):
        df = _make_df(amount=["", "", ""])
        result = self.cleaner.clean(df)
        self.assertTrue(np.isnan(result["amount"].iloc[0]))


class TestDataCleanerCasing(SimpleTestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_status_uppercased(self):
        df = _make_df(status=["success", "failed", "pending"])
        result = self.cleaner.clean(df)
        self.assertTrue(all(s == s.upper() for s in result["status"]))

    def test_currency_uppercased(self):
        df = _make_df(currency=["inr", "usd", "INR"])
        result = self.cleaner.clean(df)
        self.assertTrue(all(c == c.upper() for c in result["currency"]))


class TestDataCleanerCategory(SimpleTestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_blank_category_filled(self):
        df = _make_df(category=["", "", ""])
        result = self.cleaner.clean(df)
        self.assertTrue(all(c == "Uncategorised" for c in result["category"]))

    def test_existing_category_preserved(self):
        df = _make_df(category=["Food", "Food", "Food"])
        result = self.cleaner.clean(df)
        self.assertTrue(all(c == "Food" for c in result["category"]))


class TestDataCleanerSyntheticIds(SimpleTestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_blank_txn_id_gets_synthetic(self):
        df = _make_df(txn_id=["TXN001", "TXN002", ""])
        result = self.cleaner.clean(df)
        self.assertTrue(result["txn_id"].iloc[2].startswith("SYN"))

    def test_existing_ids_unchanged(self):
        df = _make_df(txn_id=["TXN001", "TXN002", "TXN003"])
        result = self.cleaner.clean(df)
        self.assertEqual(result["txn_id"].iloc[0], "TXN001")


class TestDataCleanerDedup(SimpleTestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_exact_duplicates_removed(self):
        df = pd.DataFrame({
            "txn_id":     ["TXN001", "TXN001"],
            "date":       ["2024-01-01", "2024-01-01"],
            "merchant":   ["Swiggy", "Swiggy"],
            "amount":     ["100", "100"],
            "currency":   ["INR", "INR"],
            "status":     ["SUCCESS", "SUCCESS"],
            "category":   ["Food", "Food"],
            "account_id": ["ACC1", "ACC1"],
            "notes":      ["", ""],
        })
        result = self.cleaner.clean(df)
        self.assertEqual(len(result), 1)

    def test_non_duplicates_kept(self):
        df = _make_df()
        result = self.cleaner.clean(df)
        # All 3 rows have different txn_ids so all should survive
        self.assertEqual(len(result), 3)
