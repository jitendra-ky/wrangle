"""
AnomalyDetector
===============
Single responsibility: flag anomalous transactions in a cleaned DataFrame.

Rules:
  1. Statistical outlier  — amount > OUTLIER_MULTIPLIER × account median
  2. Currency mismatch    — USD transaction on a domestic-only merchant

Both rules append to `anomaly_reason`; a row can be flagged by both.

No Django imports — pure pandas/stdlib.
"""

from __future__ import annotations

import pandas as pd

_DEFAULT_OUTLIER_MULTIPLIER = 3.0

_DEFAULT_DOMESTIC_MERCHANTS: frozenset[str] = frozenset(
    {"swiggy", "ola", "irctc", "zomato", "jio recharge", "bookmyshow"}
)


class AnomalyDetector:
    """
    Flags anomalous rows in a cleaned transactions DataFrame.

    Usage::

        detector = AnomalyDetector()
        df = detector.detect(df_clean)
        # df now has: is_anomaly (bool), anomaly_reason (str)
    """

    def __init__(
        self,
        outlier_multiplier: float = _DEFAULT_OUTLIER_MULTIPLIER,
        domestic_merchants: frozenset[str] | None = None,
    ):
        self.outlier_multiplier = outlier_multiplier
        self.domestic_merchants = domestic_merchants or _DEFAULT_DOMESTIC_MERCHANTS

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add is_anomaly and anomaly_reason columns. Returns a new DataFrame."""
        df = df.copy()
        df["is_anomaly"]     = False
        df["anomaly_reason"] = ""
        df = self._flag_statistical_outliers(df)
        df = self._flag_currency_mismatches(df)
        return df

    # ── Private rules ─────────────────────────────────────────────────────────

    def _flag_statistical_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        account_medians = df.groupby("account_id")["amount"].median()

        for idx, row in df.iterrows():
            median = account_medians.get(row["account_id"])
            if median and median > 0 and row["amount"] > self.outlier_multiplier * median:
                reason = (
                    f"amount ({row['amount']:.2f}) > "
                    f"{self.outlier_multiplier}x account median ({median:.2f})"
                )
                df = self._append_reason(df, idx, reason)
        return df

    def _flag_currency_mismatches(self, df: pd.DataFrame) -> pd.DataFrame:
        for idx, row in df.iterrows():
            if (
                str(row["currency"]).upper() == "USD"
                and str(row["merchant"]).lower() in self.domestic_merchants
            ):
                reason = f"USD on domestic-only merchant '{row['merchant']}'"
                df = self._append_reason(df, idx, reason)
        return df

    @staticmethod
    def _append_reason(df: pd.DataFrame, idx: int, reason: str) -> pd.DataFrame:
        existing = df.at[idx, "anomaly_reason"]
        df.at[idx, "is_anomaly"]     = True
        df.at[idx, "anomaly_reason"] = f"{existing} | {reason}" if existing else reason
        return df
