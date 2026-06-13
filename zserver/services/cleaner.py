"""
DataCleaner
===========
Single responsibility: normalise a raw transactions DataFrame.

Steps (in order):
  1. Strip whitespace from all string columns
  2. Normalise date formats → ISO 8601
  3. Strip currency symbols from amount → float
  4. Uppercase status & currency
  5. Fill blank category → 'Uncategorised'
  6. Assign synthetic txn_id for blank rows
  7. Remove exact duplicate rows

No Django imports — pure pandas/stdlib so this is independently testable.
"""

from __future__ import annotations

import re
from datetime import datetime

import numpy as np
import pandas as pd


_DATE_FORMATS = [
    "%d-%m-%Y",   # 04-09-2024
    "%Y/%m/%d",   # 2024/02/05
    "%Y-%m-%d",   # 2024-07-15 (already ISO)
    "%m/%d/%Y",   # fallback US
]

_DEDUP_COLS = ["txn_id", "date", "merchant", "amount", "currency", "status", "account_id"]


def _parse_date(raw: str) -> str | None:
    """Return ISO 8601 string, or 'INVALID:<raw>' if unparseable."""
    if not raw or pd.isna(raw):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(raw).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return pd.to_datetime(raw, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return f"INVALID:{raw}"


def _clean_amount(val: str) -> float:
    """Strip non-numeric chars (e.g. '$') and cast to float."""
    if pd.isna(val) or str(val).strip() == "":
        return np.nan
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return np.nan


class DataCleaner:
    """
    Cleans a raw transactions DataFrame.

    Usage::

        cleaner = DataCleaner()
        df_clean = cleaner.clean(df_raw)
    """

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run all cleaning steps in order. Returns a new DataFrame."""
        df = df.copy()
        df = self._strip_whitespace(df)
        df = self._normalise_dates(df)
        df = self._clean_amounts(df)
        df = self._uppercase_fields(df)
        df = self._fill_missing_category(df)
        df = self._assign_synthetic_ids(df)
        df = self._remove_duplicates(df)
        return df

    # ── Private steps ─────────────────────────────────────────────────────────

    def _strip_whitespace(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.apply(lambda col: col.str.strip() if col.dtype == object else col)

    def _normalise_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        df["date"] = df["date"].apply(_parse_date)
        return df

    def _clean_amounts(self, df: pd.DataFrame) -> pd.DataFrame:
        df["amount"] = df["amount"].apply(_clean_amount)
        return df

    def _uppercase_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        df["status"]   = df["status"].str.upper().str.strip()
        df["currency"] = df["currency"].str.upper().str.strip()
        return df

    def _fill_missing_category(self, df: pd.DataFrame) -> pd.DataFrame:
        df["category"] = df["category"].replace("", np.nan).fillna("Uncategorised")
        return df

    def _assign_synthetic_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = df["txn_id"].isna() | (df["txn_id"] == "")
        counter = 1
        for idx in df[mask].index:
            df.at[idx, "txn_id"] = f"SYN{counter:04d}"
            counter += 1
        return df

    def _remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in _DEDUP_COLS if c in df.columns]
        return df.drop_duplicates(subset=cols, keep="first").reset_index(drop=True)
