"""Render the markdown review report that a human reviewer can download.

The report is a draft summary of the QA findings; a reviewer fills in the
sign-off section at the bottom. No model output is interpreted, only
counted, summarized, and listed. There is no LLM call anywhere.
"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd


def _fmt_count(n: int) -> str:
    return f"{n:,}"


def _largest_changes_section(flagged_df: pd.DataFrame, n: int = 10) -> str:
    """Top-n absolute pd_score moves, rendered as a Markdown table."""
    cols = ["entity_id", "scenario", "portfolio_segment", "property_type",
            "pd_score_prior", "pd_score_current", "pd_score_change",
            "risk_grade_prior", "risk_grade_current"]
    available = [c for c in cols if c in flagged_df.columns]
    if not available or "pd_score_abs_change" not in flagged_df.columns:
        return "_(no row-level deltas available)_\n"

    top = (
        flagged_df.sort_values("pd_score_abs_change", ascending=False, na_position="last")
        .head(n)[available]
        .reset_index(drop=True)
    )
    return top.to_markdown(index=False, floatfmt=".4f")


def build_review_report(
    overview: dict,
    qa: dict,
    flagged_df: pd.DataFrame,
    n_flagged: int,
    pd_threshold: float,
    el_threshold: float,
) -> str:
    """Render the full review report as a Markdown string."""
    buf = StringIO()

    buf.write("# Model Output QA Review Report\n\n")
    buf.write(f"_Generated {date.today().isoformat()}. Draft for human review._\n\n")
    buf.write("> **Reminder.** This report is the output of deterministic QA checks. "
              "It is not a model validation, a business decision, or a policy view. "
              "A human reviewer must verify each finding before any action.\n\n")

    # --- Overview --------------------------------------------------------
    buf.write("## Overview\n\n")
    buf.write(f"- Prior row count: **{_fmt_count(overview['prior_row_count'])}**\n")
    buf.write(f"- Current row count: **{_fmt_count(overview['current_row_count'])}**\n")
    buf.write(f"- Row count delta: **{overview['row_count_delta']:+d}**\n")
    buf.write(f"- New entity IDs: **{len(overview['new_entity_ids'])}**\n")
    buf.write(f"- Dropped entity IDs: **{len(overview['dropped_entity_ids'])}**\n")
    buf.write(f"- Flagged records (current run): **{_fmt_count(n_flagged)}**\n")
    if pd.notna(overview.get('avg_pd_score_change')):
        buf.write(f"- Average pd_score change: **{overview['avg_pd_score_change']:+.4f}**\n")
    if pd.notna(overview.get('avg_el_change')):
        buf.write(f"- Average expected_loss change: **{overview['avg_el_change']:+,.2f}**\n")
    buf.write("\n")

    # --- Thresholds ------------------------------------------------------
    buf.write("## Flagging thresholds\n\n")
    buf.write(f"- `pd_score` absolute change > **{pd_threshold:.3f}**\n")
    buf.write(f"- `expected_loss` percent change > **{el_threshold * 100:.1f}%**\n")
    buf.write(f"- Any `risk_grade` change\n\n")

    # --- QA findings -----------------------------------------------------
    buf.write("## Deterministic QA findings\n\n")
    miss_prior = qa.get("required_columns_missing_prior", [])
    miss_cur = qa.get("required_columns_missing_current", [])
    buf.write(f"- Required columns missing in prior: "
              f"{', '.join(miss_prior) if miss_prior else '_none_'}\n")
    buf.write(f"- Required columns missing in current: "
              f"{', '.join(miss_cur) if miss_cur else '_none_'}\n")

    cd = qa.get("column_delta", {"added": [], "removed": []})
    buf.write(f"- Columns added: {', '.join(cd.get('added', [])) or '_none_'}\n")
    buf.write(f"- Columns removed: {', '.join(cd.get('removed', [])) or '_none_'}\n")

    dt = qa.get("dtype_delta", pd.DataFrame())
    if isinstance(dt, pd.DataFrame) and not dt.empty:
        buf.write("- Dtype changes:\n\n")
        buf.write(dt.to_markdown(index=False))
        buf.write("\n\n")
    else:
        buf.write("- Dtype changes: _none_\n")

    dk_prior = qa.get("duplicate_keys_prior", pd.DataFrame())
    dk_cur = qa.get("duplicate_keys_current", pd.DataFrame())
    buf.write(f"- Duplicate (entity_id, scenario) rows in prior: **{len(dk_prior)}**\n")
    buf.write(f"- Duplicate (entity_id, scenario) rows in current: **{len(dk_cur)}**\n")

    oop_pd_p = qa.get("out_of_range_pd_prior", pd.DataFrame())
    oop_pd_c = qa.get("out_of_range_pd_current", pd.DataFrame())
    buf.write(f"- Out-of-range pd_score rows in prior: **{len(oop_pd_p)}**\n")
    buf.write(f"- Out-of-range pd_score rows in current: **{len(oop_pd_c)}**\n\n")

    sc = qa.get("scenario_coverage_delta", pd.DataFrame())
    if isinstance(sc, pd.DataFrame) and not sc.empty:
        buf.write("## Scenario coverage changes\n\n")
        buf.write(sc.head(20).to_markdown(index=False))
        if len(sc) > 20:
            buf.write(f"\n\n_…and {len(sc) - 20} more rows in the downloadable CSV._\n")
        buf.write("\n\n")

    # --- Largest changes -------------------------------------------------
    buf.write("## Largest pd_score changes (top 10)\n\n")
    buf.write(_largest_changes_section(flagged_df, n=10))
    buf.write("\n\n")

    # --- Human reviewer checklist ----------------------------------------
    buf.write("## Human reviewer checklist\n\n")
    buf.write("Before approving the current model run for release, the reviewer must confirm:\n\n")
    buf.write("- [ ] Source inputs to the model run match the documented data cut.\n")
    buf.write("- [ ] Every flagged record has a documented driver "
              "(scenario change, methodology update, data revision).\n")
    buf.write("- [ ] Scenario coverage changes are intentional.\n")
    buf.write("- [ ] New entities entered the panel through the documented onboarding workflow.\n")
    buf.write("- [ ] Dropped entities are accounted for (paid off, sold, expired, etc.).\n")
    buf.write("- [ ] Out-of-range values are corrected at the source, not papered over.\n")
    buf.write("- [ ] Risk-grade migrations have been reviewed by a credit reviewer.\n")
    buf.write("- [ ] The reviewer has documented their name, date, and any open items below.\n\n")

    buf.write("### Reviewer sign-off\n\n")
    buf.write("- Reviewer name: _________________________\n")
    buf.write("- Sign-off date: _________________________\n")
    buf.write("- Open items / follow-ups:\n\n")
    buf.write("  - \n  - \n  - \n\n")

    # --- Limitations ----------------------------------------------------
    buf.write("## Limitations of this report\n\n")
    buf.write("- The QA checks are deterministic and intentionally simple. "
              "They do not validate model methodology, do not assess economic "
              "reasonableness, and do not draw conclusions from the data.\n")
    buf.write("- Flagging thresholds are user-defined; a record being flagged "
              "(or not flagged) is not an opinion of correctness.\n")
    buf.write("- No external AI or LLM service is called.\n")

    return buf.getvalue()
