"""
LLMNarrativeBuilder
===================
Single responsibility: produce a structured JSON summary of the pipeline results
via a single LLM call.

Falls back to a computed stub if the LLM call fails.

No Django imports.
"""

from __future__ import annotations

import json
import re
import textwrap

import pandas as pd

from .client import LLMClient, LLMError


class LLMNarrativeBuilder:
    """
    Builds a narrative summary dict from a processed DataFrame.

    Parameters
    ----------
    client : LLMClient instance (injected for testability).
    """

    def __init__(self, client: LLMClient):
        self.client = client

    # ── Public interface ──────────────────────────────────────────────────────

    def build(self, df: pd.DataFrame) -> dict:
        """
        Compute stats from *df* and ask the LLM for a narrative summary.
        Falls back to a computed stub on failure.

        Returns a dict with keys:
            total_spend_inr, total_spend_usd, top_merchants,
            anomaly_count, narrative, risk_level, category_spend
        """
        stats = self._compute_stats(df)
        try:
            prompt  = self._build_prompt(stats)
            raw     = self.client.call(prompt, expect_json=True)
            raw     = re.sub(r"```(?:json)?\n?", "", raw).strip().rstrip("`")
            summary = json.loads(raw)
            # Ensure category_spend is included (LLM won't return it)
            summary["category_spend"] = stats["category_spend"]
            return summary
        except (LLMError, json.JSONDecodeError, Exception):
            return self._compute_stub(stats)

    # ── Private ───────────────────────────────────────────────────────────────

    def _compute_stats(self, df: pd.DataFrame) -> dict:
        total_inr    = float(df[df["currency"] == "INR"]["amount"].sum())
        total_usd    = float(df[df["currency"] == "USD"]["amount"].sum())
        top_merchants = (
            df.groupby("merchant")["amount"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
            .to_dict()
        )
        anomaly_count = int(df["is_anomaly"].sum())
        category_spend = (
            df.groupby(["category", "currency"])["amount"]
            .agg(total_spend="sum", txn_count="count")
            .reset_index()
            .sort_values("total_spend", ascending=False)
            .to_dict(orient="records")
        )
        status_counts = df["status"].value_counts().to_dict()

        return dict(
            total_inr=total_inr,
            total_usd=total_usd,
            top_merchants=top_merchants,
            anomaly_count=anomaly_count,
            category_spend=category_spend,
            status_counts=status_counts,
            total_rows=len(df),
        )

    def _build_prompt(self, stats: dict) -> str:
        return textwrap.dedent(f"""
            You are a financial analyst assistant. Analyse the following transaction
            statistics and produce a JSON summary.

            Statistics:
            - Total INR spend : {stats['total_inr']:.2f}
            - Total USD spend : {stats['total_usd']:.2f}
            - Top 3 merchants : {json.dumps(stats['top_merchants'])}
            - Anomalies       : {stats['anomaly_count']}
            - Spend by category : {json.dumps({r['category']: r['total_spend'] for r in stats['category_spend']})}
            - Transaction statuses : {json.dumps(stats['status_counts'])}
            - Total rows : {stats['total_rows']}

            Return a JSON object with exactly these keys:
            {{
              "total_spend_inr": <number>,
              "total_spend_usd": <number>,
              "top_merchants": {{"MerchantName": <total_spend>, ...}},
              "anomaly_count": <integer>,
              "narrative": "<2-3 sentences describing spending patterns and risk>",
              "risk_level": "<low|medium|high>"
            }}

            For risk_level:
            - high   if anomaly_count > 5
            - medium if anomaly_count between 2 and 5
            - low    otherwise
        """)

    def _compute_stub(self, stats: dict) -> dict:
        anomaly_count = stats["anomaly_count"]
        if anomaly_count > 5:
            risk_level = "high"
        elif anomaly_count >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "total_spend_inr": round(stats["total_inr"], 2),
            "total_spend_usd": round(stats["total_usd"], 2),
            "top_merchants":   stats["top_merchants"],
            "anomaly_count":   anomaly_count,
            "narrative":       "Pipeline completed. LLM narrative unavailable.",
            "risk_level":      risk_level,
            "category_spend":  stats["category_spend"],
        }
