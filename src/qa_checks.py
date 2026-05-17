"""Deterministic QA checks on model-output extracts.

Each function takes one or two pandas DataFrames and returns a tidy
structure that the Streamlit app renders. Functions are pure — they
read inputs and return outputs, no global state and no I/O.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS: tuple[str, ...] = (
    "entity_id",
    "portfolio_segment",
    "property_type",
    "scenario",
    "quarter",
    "pd_score",
    "risk_grade",
    "expected_loss",
    "model_version",
    "run_date",
)

# Reasonable bounds for the synthetic schema. pd_score is a probability
# in [0, 1]; expected_loss is in dollars and should be non-negative.
PD_SCORE_BOUNDS = (0.0, 1.0)
EXPECTED_LOSS_BOUNDS = (0.0, float("inf"))


def missing_columns(df: pd.DataFrame) -> list[str]:
    """Return required columns that are absent from `df`."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def missing_values_by_column(df: pd.DataFrame) -> pd.DataFrame:
    """Per-column null counts and percentages."""
    counts = df.isna().sum()
    pct = (counts / max(len(df), 1) * 100).round(2)
    return (
        pd.DataFrame({"null_count": counts, "null_pct": pct})
        .sort_values("null_count", ascending=False)
    )


def duplicate_keys(df: pd.DataFrame, key_cols: Iterable[str] = ("entity_id", "scenario")) -> pd.DataFrame:
    """Rows whose (entity_id, scenario) combination is duplicated."""
    key_cols = list(key_cols)
    if not set(key_cols).issubset(df.columns):
        return df.iloc[0:0]
    dup_mask = df.duplicated(subset=key_cols, keep=False)
    return df[dup_mask].sort_values(key_cols)


def out_of_range_pd_score(df: pd.DataFrame) -> pd.DataFrame:
    """Rows whose pd_score falls outside [0, 1]."""
    if "pd_score" not in df.columns:
        return df.iloc[0:0]
    lo, hi = PD_SCORE_BOUNDS
    mask = (df["pd_score"] < lo) | (df["pd_score"] > hi)
    return df[mask]


def out_of_range_expected_loss(df: pd.DataFrame) -> pd.DataFrame:
    """Rows whose expected_loss is negative (synthetic guard)."""
    if "expected_loss" not in df.columns:
        return df.iloc[0:0]
    lo, _ = EXPECTED_LOSS_BOUNDS
    mask = df["expected_loss"].fillna(0) < lo
    return df[mask]


def column_delta(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> dict[str, list[str]]:
    """Columns added or removed between prior and current files."""
    prior_cols = set(prior_df.columns)
    current_cols = set(current_df.columns)
    return {
        "added": sorted(current_cols - prior_cols),
        "removed": sorted(prior_cols - current_cols),
    }


def dtype_delta(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    """Columns whose dtype changed between the two extracts."""
    shared = [c for c in prior_df.columns if c in current_df.columns]
    rows = []
    for c in shared:
        prior_dt = str(prior_df[c].dtype)
        cur_dt = str(current_df[c].dtype)
        if prior_dt != cur_dt:
            rows.append({"column": c, "prior_dtype": prior_dt, "current_dtype": cur_dt})
    return pd.DataFrame(rows)


def scenario_coverage_delta(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    """For each entity_id, scenarios present in prior but missing in current and vice versa."""
    if not {"entity_id", "scenario"}.issubset(prior_df.columns) or \
       not {"entity_id", "scenario"}.issubset(current_df.columns):
        return pd.DataFrame()

    prior_pairs = set(map(tuple, prior_df[["entity_id", "scenario"]].itertuples(index=False)))
    current_pairs = set(map(tuple, current_df[["entity_id", "scenario"]].itertuples(index=False)))

    dropped = prior_pairs - current_pairs
    added = current_pairs - prior_pairs

    return pd.DataFrame(
        [{"entity_id": e, "scenario": s, "change": "dropped_from_current"} for e, s in sorted(dropped)] +
        [{"entity_id": e, "scenario": s, "change": "added_in_current"} for e, s in sorted(added)]
    )


def run_all_checks(prior_df: pd.DataFrame, current_df: pd.DataFrame) -> dict[str, object]:
    """Bundle every deterministic QA result for the dashboard to render."""
    return {
        "required_columns_missing_prior":   missing_columns(prior_df),
        "required_columns_missing_current": missing_columns(current_df),
        "missing_values_prior":             missing_values_by_column(prior_df),
        "missing_values_current":           missing_values_by_column(current_df),
        "duplicate_keys_prior":             duplicate_keys(prior_df),
        "duplicate_keys_current":           duplicate_keys(current_df),
        "out_of_range_pd_prior":            out_of_range_pd_score(prior_df),
        "out_of_range_pd_current":          out_of_range_pd_score(current_df),
        "out_of_range_el_prior":            out_of_range_expected_loss(prior_df),
        "out_of_range_el_current":          out_of_range_expected_loss(current_df),
        "column_delta":                     column_delta(prior_df, current_df),
        "dtype_delta":                      dtype_delta(prior_df, current_df),
        "scenario_coverage_delta":          scenario_coverage_delta(prior_df, current_df),
    }
