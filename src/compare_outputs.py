"""Row-level comparison of prior and current model-output extracts.

The comparison joins on (entity_id, scenario) and computes per-row deltas
on the numeric columns plus a categorical change indicator on risk_grade.
Flagging is threshold-driven; thresholds are passed in by the caller (the
Streamlit app exposes them as sidebar sliders).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


JOIN_KEYS = ("entity_id", "scenario")


@dataclass
class Thresholds:
    """User-defined thresholds for flagging."""
    pd_score_abs: float = 0.02        # flag if |Δpd_score| > 0.02
    expected_loss_abs_pct: float = 0.20  # flag if |Δexpected_loss| / prior > 20%


def overview_metrics(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> dict[str, object]:
    """Top-line counts and average changes shown at the top of the dashboard."""
    prior_entities = set(prior_df["entity_id"]) if "entity_id" in prior_df.columns else set()
    current_entities = set(current_df["entity_id"]) if "entity_id" in current_df.columns else set()

    merged = _merge(prior_df, current_df)
    pd_change_mean = merged["pd_score_change"].mean() if len(merged) else float("nan")
    el_change_mean = merged["expected_loss_change"].mean() if len(merged) else float("nan")

    return {
        "prior_row_count":      len(prior_df),
        "current_row_count":    len(current_df),
        "row_count_delta":      len(current_df) - len(prior_df),
        "new_entity_ids":       sorted(current_entities - prior_entities),
        "dropped_entity_ids":   sorted(prior_entities - current_entities),
        "avg_pd_score_change":  pd_change_mean,
        "avg_el_change":        el_change_mean,
    }


def _merge(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    """Inner-merge on (entity_id, scenario) and add delta columns.

    Returns an empty DataFrame if either side is missing the join keys.
    """
    keys = list(JOIN_KEYS)
    if not set(keys).issubset(prior_df.columns) or not set(keys).issubset(current_df.columns):
        return pd.DataFrame()

    # Carry forward useful descriptors from the current side.
    keep_cols_current = keys + [
        c for c in ["portfolio_segment", "property_type", "quarter", "pd_score",
                    "risk_grade", "expected_loss", "model_version", "run_date"]
        if c in current_df.columns
    ]
    keep_cols_prior = keys + [
        c for c in ["pd_score", "risk_grade", "expected_loss", "model_version"]
        if c in prior_df.columns
    ]

    merged = current_df[keep_cols_current].merge(
        prior_df[keep_cols_prior],
        on=keys,
        how="inner",
        suffixes=("_current", "_prior"),
    )

    if "pd_score_current" in merged and "pd_score_prior" in merged:
        merged["pd_score_change"] = merged["pd_score_current"] - merged["pd_score_prior"]
        merged["pd_score_abs_change"] = merged["pd_score_change"].abs()

    if "expected_loss_current" in merged and "expected_loss_prior" in merged:
        merged["expected_loss_change"] = (
            merged["expected_loss_current"] - merged["expected_loss_prior"]
        )
        merged["expected_loss_pct_change"] = (
            merged["expected_loss_change"] / merged["expected_loss_prior"].replace(0, pd.NA)
        )

    if "risk_grade_current" in merged and "risk_grade_prior" in merged:
        merged["risk_grade_change"] = (
            merged["risk_grade_current"] != merged["risk_grade_prior"]
        )

    return merged


def compare(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    """Public entry point — returns the joined panel with deltas."""
    return _merge(prior_df, current_df)


def apply_flags(merged: pd.DataFrame, thresholds: Thresholds) -> pd.DataFrame:
    """Add boolean flag columns and a summary `is_flagged` column."""
    out = merged.copy()
    if "pd_score_abs_change" in out.columns:
        out["flag_pd_score"] = out["pd_score_abs_change"] > thresholds.pd_score_abs
    if "expected_loss_pct_change" in out.columns:
        out["flag_expected_loss"] = (
            out["expected_loss_pct_change"].abs() > thresholds.expected_loss_abs_pct
        )
    if "risk_grade_change" in out.columns:
        out["flag_risk_grade"] = out["risk_grade_change"]

    flag_cols = [c for c in out.columns if c.startswith("flag_")]
    if flag_cols:
        out["is_flagged"] = out[flag_cols].any(axis=1)
    return out


def filter_records(
    merged_flagged: pd.DataFrame,
    portfolio_segments: Iterable[str] | None = None,
    property_types: Iterable[str] | None = None,
    scenarios: Iterable[str] | None = None,
    only_flagged: bool = False,
) -> pd.DataFrame:
    """Apply sidebar filters to the flagged panel."""
    out = merged_flagged
    if portfolio_segments and "portfolio_segment" in out.columns:
        out = out[out["portfolio_segment"].isin(portfolio_segments)]
    if property_types and "property_type" in out.columns:
        out = out[out["property_type"].isin(property_types)]
    if scenarios and "scenario" in out.columns:
        out = out[out["scenario"].isin(scenarios)]
    if only_flagged and "is_flagged" in out.columns:
        out = out[out["is_flagged"]]
    return out
