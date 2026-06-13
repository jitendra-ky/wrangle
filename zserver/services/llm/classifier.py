"""
LLMClassifier
=============
Single responsibility: batch-classify uncategorised transactions via the LLM.

* Splits rows where category == 'Uncategorised' into batches.
* Calls LLMClient once per batch.
* On failure: marks llm_failed=True for that batch and continues (never aborts the job).
* Returns augmented DataFrame with llm_category and llm_failed columns.

No Django imports.
"""

from __future__ import annotations

import json
import re
import textwrap

import pandas as pd

from .client import LLMClient, LLMError

_VALID_CATEGORIES = [
    "Food", "Shopping", "Travel", "Transport",
    "Utilities", "Cash Withdrawal", "Entertainment", "Other",
]

_DEFAULT_BATCH_SIZE = 20


class LLMClassifier:
    """
    Assigns categories to uncategorised transactions using the LLM.

    Parameters
    ----------
    client          : LLMClient instance (injected for testability).
    valid_categories: Allowed category labels.
    batch_size      : Max rows per LLM call.
    """

    def __init__(
        self,
        client: LLMClient,
        valid_categories: list[str] | None = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ):
        self.client           = client
        self.valid_categories = valid_categories or _VALID_CATEGORIES
        self.batch_size       = batch_size

    # ── Public interface ──────────────────────────────────────────────────────

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add llm_category and llm_failed columns.
        Rows that already have a non-Uncategorised category are left untouched.
        Returns a new DataFrame.
        """
        df = df.copy()
        df["llm_category"] = None
        df["llm_failed"]   = False

        uncat_idx = df[df["category"] == "Uncategorised"].index.tolist()
        if not uncat_idx:
            return df

        batches = [
            uncat_idx[i : i + self.batch_size]
            for i in range(0, len(uncat_idx), self.batch_size)
        ]

        for batch_idx in batches:
            df = self._process_batch(df, batch_idx)

        return df

    # ── Private ───────────────────────────────────────────────────────────────

    def _process_batch(self, df: pd.DataFrame, batch_idx: list[int]) -> pd.DataFrame:
        batch_df = df.loc[batch_idx]
        prompt   = self._build_prompt(batch_df)

        try:
            raw             = self.client.call(prompt, expect_json=True)
            raw             = re.sub(r"```(?:json)?\n?", "", raw).strip().rstrip("`")
            classifications = json.loads(raw)

            for idx in batch_idx:
                txn_id = df.at[idx, "txn_id"]
                cat    = classifications.get(txn_id, "Other")
                if cat not in self.valid_categories:
                    cat = "Other"
                df.at[idx, "category"]     = cat
                df.at[idx, "llm_category"] = cat

        except (LLMError, json.JSONDecodeError, Exception):
            for idx in batch_idx:
                df.at[idx, "llm_failed"] = True

        return df

    def _build_prompt(self, batch_df: pd.DataFrame) -> str:
        categories_str = ", ".join(self.valid_categories)
        rows_str = "\n".join(
            f"  - txn_id={row['txn_id']}, merchant='{row['merchant']}', "
            f"amount={row['amount']}, currency={row['currency']}, "
            f"notes='{row.get('notes', '')}'"
            for _, row in batch_df.iterrows()
        )
        return textwrap.dedent(f"""
            You are a financial transaction classifier.
            For each transaction below, assign EXACTLY ONE category from this list:
            [{categories_str}]

            Rules:
            - Reply with a JSON object mapping each txn_id to its category.
            - Use only the exact category names listed above.
            - If genuinely unclear, use "Other".

            Transactions:
            {rows_str}

            Example output:
            {{"TXN1000": "Shopping", "TXN1001": "Food"}}
        """)
