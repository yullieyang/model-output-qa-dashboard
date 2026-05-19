"""Deterministic, agent-like QA components for model-output review.

Each "agent" in this module is a small, focused review component that
inspects one slice of the prior/current model-output extracts and returns
a consistent result dictionary. Despite the name, none of these agents
call an LLM, an external API, or make autonomous decisions. They are
deterministic Python functions wrapped in a dataclass, organised around
the orchestration pattern of an agentic workflow so that each review
responsibility is isolated and auditable.

Each agent returns a dictionary with the same shape:

    {
        "agent_name":            str,
        "status":                "pass" | "warning" | "fail",
        "summary":               dict,         # short, structured findings
        "findings":              list[str],    # human-readable bullets
        "human_review_required": bool,
    }

`status` follows a fixed rubric:
    - pass:    no meaningful issue detected.
    - warning: issue detected that a human reviewer should look at.
    - fail:    severe issue such as a missing required column or an
               invalid range that breaks downstream comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import pandas as pd


AgentResult = dict[str, Any]


def _empty_result(name: str) -> AgentResult:
    return {
        "agent_name": name,
        "status": "pass",
        "summary": {},
        "findings": [],
        "human_review_required": False,
    }


# ---------------------------------------------------------------------------
# 1. Schema check
# ---------------------------------------------------------------------------

@dataclass
class SchemaCheckAgent:
    """Compare prior vs current column sets and dtypes.

    Fails if any required column is missing in the current extract,
    because the downstream comparison logic would silently produce
    nothing useful in that case. Warns on added/removed columns or
    dtype drift.
    """

    required_columns: Sequence[str]
    name: str = "SchemaCheckAgent"

    def run(self, prior_df: pd.DataFrame, current_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)

        missing_prior = [c for c in self.required_columns if c not in prior_df.columns]
        missing_current = [c for c in self.required_columns if c not in current_df.columns]

        prior_cols = set(prior_df.columns)
        current_cols = set(current_df.columns)
        added = sorted(current_cols - prior_cols)
        removed = sorted(prior_cols - current_cols)

        dtype_changes: list[dict[str, str]] = []
        for c in sorted(prior_cols & current_cols):
            prior_dt = str(prior_df[c].dtype)
            cur_dt = str(current_df[c].dtype)
            if prior_dt != cur_dt:
                dtype_changes.append(
                    {"column": c, "prior_dtype": prior_dt, "current_dtype": cur_dt}
                )

        result["summary"] = {
            "required_columns_missing_prior": missing_prior,
            "required_columns_missing_current": missing_current,
            "columns_added": added,
            "columns_removed": removed,
            "dtype_changes": dtype_changes,
        }

        if missing_current or missing_prior:
            result["status"] = "fail"
            result["human_review_required"] = True
            if missing_current:
                result["findings"].append(
                    f"Required columns missing in current extract: {missing_current}"
                )
            if missing_prior:
                result["findings"].append(
                    f"Required columns missing in prior extract: {missing_prior}"
                )
        elif added or removed or dtype_changes:
            result["status"] = "warning"
            result["human_review_required"] = True
            if added:
                result["findings"].append(f"New columns appeared in current: {added}")
            if removed:
                result["findings"].append(f"Columns removed in current: {removed}")
            if dtype_changes:
                result["findings"].append(
                    f"Dtype changes on {len(dtype_changes)} shared column(s)."
                )
        else:
            result["findings"].append("Schema matches between prior and current.")

        return result


# ---------------------------------------------------------------------------
# 2. Missing values
# ---------------------------------------------------------------------------

@dataclass
class MissingValueAgent:
    """Review null counts overall and in important columns."""

    important_columns: Sequence[str]
    name: str = "MissingValueAgent"

    def run(self, prior_df: pd.DataFrame, current_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)

        prior_nulls = prior_df.isna().sum().to_dict() if len(prior_df) else {}
        current_nulls = current_df.isna().sum().to_dict() if len(current_df) else {}

        important_nulls_current = {
            c: int(current_nulls.get(c, 0))
            for c in self.important_columns
            if c in current_df.columns
        }
        important_nulls_prior = {
            c: int(prior_nulls.get(c, 0))
            for c in self.important_columns
            if c in prior_df.columns
        }

        new_null_cols = sorted(
            c for c in current_df.columns
            if int(current_nulls.get(c, 0)) > 0
            and int(prior_nulls.get(c, 0)) == 0
        )

        total_current_nulls = int(sum(current_nulls.values()))
        total_prior_nulls = int(sum(prior_nulls.values()))

        result["summary"] = {
            "total_nulls_prior": total_prior_nulls,
            "total_nulls_current": total_current_nulls,
            "null_count_delta": total_current_nulls - total_prior_nulls,
            "important_column_nulls_prior": important_nulls_prior,
            "important_column_nulls_current": important_nulls_current,
            "columns_with_new_nulls": new_null_cols,
        }

        important_hits = {c: n for c, n in important_nulls_current.items() if n > 0}

        if important_hits:
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append(
                f"Important columns with nulls in current: {important_hits}"
            )
        if new_null_cols:
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append(
                f"Columns that gained nulls vs prior: {new_null_cols}"
            )
        if total_current_nulls > total_prior_nulls and not result["findings"]:
            result["findings"].append(
                f"Total null count increased by {total_current_nulls - total_prior_nulls}."
            )
        if not result["findings"]:
            result["findings"].append("No notable changes in missing values.")

        return result


# ---------------------------------------------------------------------------
# 3. Duplicate keys
# ---------------------------------------------------------------------------

@dataclass
class DuplicateKeyAgent:
    """Check that the composite key is unique in each extract."""

    key_columns: Sequence[str]
    name: str = "DuplicateKeyAgent"

    def _dups(self, df: pd.DataFrame) -> int:
        keys = [c for c in self.key_columns if c in df.columns]
        if not keys or len(keys) != len(self.key_columns) or df.empty:
            return 0
        return int(df.duplicated(subset=keys, keep=False).sum())

    def run(self, prior_df: pd.DataFrame, current_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)

        prior_dups = self._dups(prior_df)
        current_dups = self._dups(current_df)

        result["summary"] = {
            "key_columns": list(self.key_columns),
            "duplicate_row_count_prior": prior_dups,
            "duplicate_row_count_current": current_dups,
            "duplicate_count_delta": current_dups - prior_dups,
        }

        if current_dups > 0:
            result["status"] = "fail"
            result["human_review_required"] = True
            result["findings"].append(
                f"{current_dups} duplicate row(s) on key {list(self.key_columns)} in current."
            )
        elif prior_dups > 0:
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append(
                f"{prior_dups} duplicate row(s) on key {list(self.key_columns)} in prior."
            )
        else:
            result["findings"].append("No duplicates on the composite key.")

        return result


# ---------------------------------------------------------------------------
# 4. Scenario coverage
# ---------------------------------------------------------------------------

@dataclass
class ScenarioCoverageAgent:
    """Compare scenario presence and counts between prior and current."""

    scenario_column: str = "scenario"
    name: str = "ScenarioCoverageAgent"

    def run(self, prior_df: pd.DataFrame, current_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)
        col = self.scenario_column

        if col not in prior_df.columns or col not in current_df.columns:
            result["status"] = "fail"
            result["human_review_required"] = True
            result["findings"].append(
                f"Scenario column '{col}' missing in one or both extracts."
            )
            result["summary"] = {"scenario_column": col, "available": False}
            return result

        prior_counts = prior_df[col].value_counts(dropna=False).to_dict()
        current_counts = current_df[col].value_counts(dropna=False).to_dict()

        only_in_prior = sorted(set(prior_counts) - set(current_counts), key=str)
        only_in_current = sorted(set(current_counts) - set(prior_counts), key=str)
        shared = sorted(set(prior_counts) & set(current_counts), key=str)

        count_changes = {
            s: {
                "prior_count": int(prior_counts.get(s, 0)),
                "current_count": int(current_counts.get(s, 0)),
                "delta": int(current_counts.get(s, 0)) - int(prior_counts.get(s, 0)),
            }
            for s in shared
        }

        result["summary"] = {
            "scenarios_in_prior_only": only_in_prior,
            "scenarios_in_current_only": only_in_current,
            "scenario_counts_prior": {str(k): int(v) for k, v in prior_counts.items()},
            "scenario_counts_current": {str(k): int(v) for k, v in current_counts.items()},
            "shared_scenario_count_changes": count_changes,
        }

        if only_in_prior or only_in_current:
            result["status"] = "warning"
            result["human_review_required"] = True
            if only_in_prior:
                result["findings"].append(
                    f"Scenarios dropped from current: {only_in_prior}"
                )
            if only_in_current:
                result["findings"].append(
                    f"Scenarios newly appearing in current: {only_in_current}"
                )
        else:
            result["findings"].append("Scenario coverage matches between prior and current.")

        return result


# ---------------------------------------------------------------------------
# 5. Output drift
# ---------------------------------------------------------------------------

@dataclass
class OutputDriftAgent:
    """Review the magnitude of pd_score and expected_loss movements.

    Operates on the row-level comparison panel produced by
    `src.compare_outputs.compare` (joined on entity_id + scenario).
    """

    pd_threshold: float
    expected_loss_threshold: float  # absolute fractional change (e.g. 0.20 == 20%)
    name: str = "OutputDriftAgent"

    def run(self, comparison_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)

        if comparison_df is None or comparison_df.empty:
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append(
                "Comparison panel is empty — no overlapping (entity_id, scenario) rows."
            )
            return result

        df = comparison_df

        pd_breaches = 0
        el_breaches = 0
        avg_abs_pd_change = float("nan")
        avg_abs_el_change = float("nan")
        top_pd = []
        top_el = []

        if "pd_score_abs_change" in df.columns:
            pd_breaches = int((df["pd_score_abs_change"] > self.pd_threshold).sum())
            avg_abs_pd_change = float(df["pd_score_abs_change"].mean())
            top_pd = (
                df.sort_values("pd_score_abs_change", ascending=False, na_position="last")
                .head(5)
                .loc[:, [c for c in ["entity_id", "scenario", "pd_score_prior",
                                     "pd_score_current", "pd_score_change"]
                         if c in df.columns]]
                .to_dict(orient="records")
            )

        if "expected_loss_pct_change" in df.columns:
            abs_pct = df["expected_loss_pct_change"].abs()
            el_breaches = int((abs_pct > self.expected_loss_threshold).sum())
            if "expected_loss_change" in df.columns:
                avg_abs_el_change = float(df["expected_loss_change"].abs().mean())
            top_el = (
                df.assign(_abs_pct=abs_pct)
                .sort_values("_abs_pct", ascending=False, na_position="last")
                .head(5)
                .loc[:, [c for c in ["entity_id", "scenario", "expected_loss_prior",
                                     "expected_loss_current", "expected_loss_change",
                                     "expected_loss_pct_change"]
                         if c in df.columns]]
                .to_dict(orient="records")
            )

        result["summary"] = {
            "row_count": int(len(df)),
            "pd_threshold": self.pd_threshold,
            "expected_loss_threshold": self.expected_loss_threshold,
            "pd_breach_count": pd_breaches,
            "expected_loss_breach_count": el_breaches,
            "avg_abs_pd_change": avg_abs_pd_change,
            "avg_abs_expected_loss_change": avg_abs_el_change,
            "top_pd_moves": top_pd,
            "top_expected_loss_moves": top_el,
        }

        if pd_breaches or el_breaches:
            result["status"] = "warning"
            result["human_review_required"] = True
            if pd_breaches:
                result["findings"].append(
                    f"{pd_breaches} row(s) exceeded the pd_score change threshold "
                    f"of {self.pd_threshold}."
                )
            if el_breaches:
                result["findings"].append(
                    f"{el_breaches} row(s) exceeded the expected_loss change threshold "
                    f"of {self.expected_loss_threshold * 100:.1f}%."
                )
        else:
            result["findings"].append("No rows exceeded the drift thresholds.")

        return result


# ---------------------------------------------------------------------------
# 6. Risk grade migration
# ---------------------------------------------------------------------------

@dataclass
class RiskGradeMigrationAgent:
    """Review risk-grade changes on the joined comparison panel."""

    grade_order: Sequence[str] = ("A", "B", "C", "D", "E")
    name: str = "RiskGradeMigrationAgent"

    def run(self, comparison_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)

        if comparison_df is None or comparison_df.empty:
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append("Comparison panel is empty — no risk-grade migrations to review.")
            return result

        if not {"risk_grade_prior", "risk_grade_current"}.issubset(comparison_df.columns):
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append("Risk grade columns not available on the comparison panel.")
            return result

        changed_mask = comparison_df["risk_grade_prior"] != comparison_df["risk_grade_current"]
        changed = comparison_df[changed_mask]
        n_changed = int(len(changed))
        share_changed = n_changed / max(len(comparison_df), 1)

        migration_table = (
            changed.groupby(["risk_grade_prior", "risk_grade_current"], dropna=False)
            .size()
            .rename("count")
            .reset_index()
            .to_dict(orient="records")
        )

        order_index = {g: i for i, g in enumerate(self.grade_order)}
        largest = []
        if migration_table:
            for r in changed.itertuples(index=False):
                prior_g = getattr(r, "risk_grade_prior")
                cur_g = getattr(r, "risk_grade_current")
                if prior_g in order_index and cur_g in order_index:
                    delta = abs(order_index[cur_g] - order_index[prior_g])
                    largest.append({
                        "entity_id": getattr(r, "entity_id", None),
                        "scenario": getattr(r, "scenario", None),
                        "risk_grade_prior": prior_g,
                        "risk_grade_current": cur_g,
                        "notch_delta": int(delta),
                    })
            largest.sort(key=lambda x: x["notch_delta"], reverse=True)
            largest = largest[:5]

        result["summary"] = {
            "rows_compared": int(len(comparison_df)),
            "rows_with_grade_change": n_changed,
            "share_with_grade_change": share_changed,
            "migration_table": migration_table,
            "largest_migrations": largest,
        }

        if n_changed > 0:
            result["status"] = "warning"
            result["human_review_required"] = True
            result["findings"].append(
                f"{n_changed} row(s) changed risk grade ({share_changed:.1%} of compared rows)."
            )
        else:
            result["findings"].append("No risk-grade migrations on overlapping rows.")

        return result


# ---------------------------------------------------------------------------
# 7. Range checks
# ---------------------------------------------------------------------------

@dataclass
class RangeCheckAgent:
    """Check that current outputs sit inside expected ranges."""

    valid_scenarios: Sequence[str] | None = None
    valid_risk_grades: Sequence[str] = ("A", "B", "C", "D", "E")
    name: str = "RangeCheckAgent"

    def run(self, current_df: pd.DataFrame) -> AgentResult:
        result = _empty_result(self.name)

        if current_df is None or current_df.empty:
            result["status"] = "fail"
            result["human_review_required"] = True
            result["findings"].append("Current extract is empty.")
            return result

        pd_out = 0
        el_neg = 0
        bad_grades = 0
        bad_scenarios = 0

        if "pd_score" in current_df.columns:
            pd_out = int(((current_df["pd_score"] < 0) | (current_df["pd_score"] > 1)).sum())

        if "expected_loss" in current_df.columns:
            el_neg = int((current_df["expected_loss"].fillna(0) < 0).sum())

        if "risk_grade" in current_df.columns:
            valid = set(self.valid_risk_grades)
            bad_grades = int(
                (~current_df["risk_grade"].isin(valid) | current_df["risk_grade"].isna()).sum()
            )

        if self.valid_scenarios is not None and "scenario" in current_df.columns:
            valid_s = set(self.valid_scenarios)
            bad_scenarios = int((~current_df["scenario"].isin(valid_s)).sum())

        result["summary"] = {
            "pd_score_out_of_range_count": pd_out,
            "expected_loss_negative_count": el_neg,
            "invalid_risk_grade_count": bad_grades,
            "invalid_scenario_count": bad_scenarios,
            "valid_risk_grades": list(self.valid_risk_grades),
            "valid_scenarios": list(self.valid_scenarios) if self.valid_scenarios else None,
        }

        if pd_out or el_neg:
            result["status"] = "fail"
            result["human_review_required"] = True
        elif bad_grades or bad_scenarios:
            result["status"] = "warning"
            result["human_review_required"] = True

        if pd_out:
            result["findings"].append(
                f"{pd_out} row(s) with pd_score outside [0, 1]."
            )
        if el_neg:
            result["findings"].append(f"{el_neg} row(s) with negative expected_loss.")
        if bad_grades:
            result["findings"].append(
                f"{bad_grades} row(s) with risk_grade outside {list(self.valid_risk_grades)} or null."
            )
        if bad_scenarios:
            result["findings"].append(
                f"{bad_scenarios} row(s) with scenario outside the configured list."
            )
        if not result["findings"]:
            result["findings"].append("All checked fields fall within expected ranges.")

        return result


# ---------------------------------------------------------------------------
# 8. Human review summary
# ---------------------------------------------------------------------------

@dataclass
class HumanReviewAgent:
    """Compose a human-reviewer checklist from prior agent findings.

    This agent does not approve or reject the model outputs. It summarises
    what a human reviewer should look at, given what the other agents
    flagged. Its own status is always `pass` — the gate is the human, not
    this function.
    """

    name: str = "HumanReviewAgent"

    _BASE_CHECKLIST: tuple[str, ...] = field(
        default=(
            "Confirm the source inputs to the model run match the documented data cut.",
            "Confirm scenario coverage changes are intentional.",
            "Confirm new and dropped entities are documented (onboarding, exits, sales).",
            "Confirm large output movements have a documented driver (data, scenario, methodology).",
            "Confirm risk-grade migrations have been reviewed by a credit reviewer.",
            "Record reviewer name, date, and any open items.",
        ),
        repr=False,
    )

    def run(self, agent_results: Iterable[AgentResult]) -> AgentResult:
        result = _empty_result(self.name)
        agent_results = list(agent_results)

        priority_items: list[str] = []
        extra_checklist: list[str] = []

        for r in agent_results:
            if r["status"] == "fail":
                for f in r["findings"]:
                    priority_items.append(f"[FAIL · {r['agent_name']}] {f}")
            elif r["status"] == "warning":
                for f in r["findings"]:
                    priority_items.append(f"[WARN · {r['agent_name']}] {f}")

            name = r["agent_name"]
            if name == "SchemaCheckAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Investigate schema changes (added/removed columns or dtype drift) "
                    "and confirm whether downstream consumers are affected."
                )
            elif name == "MissingValueAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Inspect rows with new or important-column nulls before sign-off."
                )
            elif name == "DuplicateKeyAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Resolve duplicate composite-key rows at the source extract."
                )
            elif name == "ScenarioCoverageAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Confirm scenario additions/retirements with the scenario owner."
                )
            elif name == "OutputDriftAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Walk through the top pd_score and expected_loss movers; confirm drivers."
                )
            elif name == "RiskGradeMigrationAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Walk through the migration table with the credit reviewer."
                )
            elif name == "RangeCheckAgent" and r["status"] != "pass":
                extra_checklist.append(
                    "Fix out-of-range or invalid-category values at the source extract."
                )

        checklist = list(self._BASE_CHECKLIST) + extra_checklist

        result["summary"] = {
            "agent_count": len(agent_results),
            "fail_count": sum(1 for r in agent_results if r["status"] == "fail"),
            "warning_count": sum(1 for r in agent_results if r["status"] == "warning"),
            "pass_count": sum(1 for r in agent_results if r["status"] == "pass"),
            "priority_items": priority_items,
            "checklist": checklist,
        }
        result["findings"] = priority_items or [
            "No fail or warning findings raised by upstream agents."
        ]
        # The human is the gate — this agent never asserts pass/fail itself.
        result["human_review_required"] = True
        return result
