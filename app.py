"""Streamlit dashboard: model-output QA between a prior and a current data cut.

Run locally:
    streamlit run app.py

The app loads two CSVs (uploaded or the bundled sample data), runs the
deterministic QA checks in `src/qa_checks.py`, computes row-level deltas
in `src/compare_outputs.py`, and renders the result. No external API is
called; everything runs in-process.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.compare_outputs import (
    Thresholds, apply_flags, compare, filter_records, overview_metrics,
)
from src.qa_checks import REQUIRED_COLUMNS, run_all_checks
from src.report_utils import build_review_report
from src.agent_orchestrator import (
    format_agent_summary_markdown, run_agentic_qa_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_PRIOR = PROJECT_ROOT / "data" / "prior_model_outputs.csv"
SAMPLE_CURRENT = PROJECT_ROOT / "data" / "current_model_outputs.csv"


# --- Page setup --------------------------------------------------------------

st.set_page_config(
    page_title="Model Output QA Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("Model Output QA Dashboard")
st.caption(
    "Portfolio-style prototype for quarterly model-output review. Synthetic data. "
    "No external AI service is called. Outputs are drafts for human review."
)


# --- Data loading ------------------------------------------------------------

def _load_csv(uploaded, fallback_path: Path) -> pd.DataFrame:
    """Read an uploaded file if present, otherwise fall back to bundled sample."""
    if uploaded is not None:
        return pd.read_csv(uploaded)
    if fallback_path.exists():
        return pd.read_csv(fallback_path)
    return pd.DataFrame()


with st.sidebar:
    st.header("Inputs")
    st.markdown(
        "Upload your prior and current CSVs, or leave both empty to use the "
        "bundled sample data under `data/`."
    )
    prior_upload = st.file_uploader("Prior model output (CSV)", type=["csv"], key="prior_upload")
    current_upload = st.file_uploader("Current model output (CSV)", type=["csv"], key="current_upload")

prior_df = _load_csv(prior_upload, SAMPLE_PRIOR)
current_df = _load_csv(current_upload, SAMPLE_CURRENT)

if prior_df.empty or current_df.empty:
    st.warning(
        "No data available. Run `python src/generate_sample_data.py` to create the "
        "bundled sample CSVs, or upload your own."
    )
    st.stop()


# --- Thresholds + filters in the sidebar -------------------------------------

with st.sidebar:
    st.header("Flagging thresholds")
    pd_threshold = st.slider(
        "pd_score absolute change threshold",
        min_value=0.001, max_value=0.20, value=0.020, step=0.001, format="%.3f",
    )
    el_threshold_pct = st.slider(
        "expected_loss percent change threshold (%)",
        min_value=1, max_value=200, value=20, step=1,
    )
    el_threshold = el_threshold_pct / 100.0

    st.header("Filters")
    segments_avail = sorted(current_df["portfolio_segment"].dropna().unique()) if "portfolio_segment" in current_df.columns else []
    types_avail = sorted(current_df["property_type"].dropna().unique()) if "property_type" in current_df.columns else []
    scenarios_avail = sorted(current_df["scenario"].dropna().unique()) if "scenario" in current_df.columns else []

    pick_segments = st.multiselect("Portfolio segment", segments_avail, default=segments_avail)
    pick_types = st.multiselect("Property type", types_avail, default=types_avail)
    pick_scenarios = st.multiselect("Scenario", scenarios_avail, default=scenarios_avail)
    only_flagged = st.checkbox("Show only flagged records", value=False)


# --- Compute -----------------------------------------------------------------

thresholds = Thresholds(pd_score_abs=pd_threshold, expected_loss_abs_pct=el_threshold)
overview = overview_metrics(prior_df, current_df)
qa = run_all_checks(prior_df, current_df)
merged = compare(prior_df, current_df)
flagged = apply_flags(merged, thresholds) if not merged.empty else merged
filtered = filter_records(
    flagged,
    portfolio_segments=pick_segments,
    property_types=pick_types,
    scenarios=pick_scenarios,
    only_flagged=only_flagged,
) if not flagged.empty else flagged

n_flagged_total = int(flagged["is_flagged"].sum()) if "is_flagged" in flagged.columns else 0


# --- Top-line metrics --------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Prior rows", f"{overview['prior_row_count']:,}")
c2.metric("Current rows", f"{overview['current_row_count']:,}", delta=f"{overview['row_count_delta']:+d}")
c3.metric("New entities", len(overview["new_entity_ids"]))
c4.metric("Dropped entities", len(overview["dropped_entity_ids"]))

c5, c6, c7 = st.columns(3)
c5.metric("Flagged records", f"{n_flagged_total:,}")
if pd.notna(overview.get("avg_pd_score_change")):
    c6.metric("Avg Δ pd_score", f"{overview['avg_pd_score_change']:+.4f}")
if pd.notna(overview.get("avg_el_change")):
    c7.metric("Avg Δ expected_loss", f"{overview['avg_el_change']:+,.0f}")

st.divider()


# --- Tabbed views ------------------------------------------------------------

tab_qa, tab_compare, tab_charts, tab_report, tab_agents = st.tabs(
    ["Deterministic QA", "Record comparison", "Charts", "Review report",
     "Agent-Like QA Workflow"]
)


with tab_qa:
    st.subheader("Required-column check")
    miss_prior = qa["required_columns_missing_prior"]
    miss_current = qa["required_columns_missing_current"]
    if miss_prior or miss_current:
        st.error(f"Missing in prior: {miss_prior or 'none'}  |  Missing in current: {miss_current or 'none'}")
    else:
        st.success("All required columns present in both files.")

    st.subheader("Missing values by column")
    ca, cb = st.columns(2)
    ca.markdown("**Prior**"); ca.dataframe(qa["missing_values_prior"], use_container_width=True)
    cb.markdown("**Current**"); cb.dataframe(qa["missing_values_current"], use_container_width=True)

    st.subheader("Duplicate (entity_id, scenario) rows")
    ca, cb = st.columns(2)
    ca.markdown(f"**Prior — {len(qa['duplicate_keys_prior'])} duplicate rows**")
    ca.dataframe(qa["duplicate_keys_prior"], use_container_width=True)
    cb.markdown(f"**Current — {len(qa['duplicate_keys_current'])} duplicate rows**")
    cb.dataframe(qa["duplicate_keys_current"], use_container_width=True)

    st.subheader("Out-of-range values")
    ca, cb = st.columns(2)
    ca.markdown(f"**pd_score outside [0,1] (current): {len(qa['out_of_range_pd_current'])} rows**")
    ca.dataframe(qa["out_of_range_pd_current"], use_container_width=True)
    cb.markdown(f"**expected_loss < 0 (current): {len(qa['out_of_range_el_current'])} rows**")
    cb.dataframe(qa["out_of_range_el_current"], use_container_width=True)

    st.subheader("Schema changes")
    cd = qa["column_delta"]
    st.write(f"**Columns added:** {cd['added'] or 'none'}")
    st.write(f"**Columns removed:** {cd['removed'] or 'none'}")
    if isinstance(qa["dtype_delta"], pd.DataFrame) and not qa["dtype_delta"].empty:
        st.dataframe(qa["dtype_delta"], use_container_width=True)
    else:
        st.write("**Dtype changes:** none")

    st.subheader("Scenario coverage changes")
    sc = qa["scenario_coverage_delta"]
    if isinstance(sc, pd.DataFrame) and not sc.empty:
        st.dataframe(sc, use_container_width=True)
    else:
        st.write("No scenario-coverage changes detected.")


with tab_compare:
    st.subheader("Row-level comparison (joined on entity_id + scenario)")
    if filtered.empty:
        st.info("No rows to display after filtering. Try widening the filter selections.")
    else:
        show_cols = [c for c in [
            "entity_id", "scenario", "portfolio_segment", "property_type",
            "pd_score_prior", "pd_score_current", "pd_score_change",
            "expected_loss_prior", "expected_loss_current",
            "expected_loss_change", "expected_loss_pct_change",
            "risk_grade_prior", "risk_grade_current", "risk_grade_change",
            "is_flagged",
        ] if c in filtered.columns]
        st.dataframe(filtered[show_cols].reset_index(drop=True), use_container_width=True, height=480)


with tab_charts:
    if filtered.empty:
        st.info("No data to chart.")
    else:
        st.subheader("Distribution of pd_score change")
        st.bar_chart(filtered["pd_score_change"].dropna())

        if "expected_loss_change" in filtered.columns and "scenario" in filtered.columns:
            st.subheader("Average Δ expected_loss by scenario")
            chart_df = filtered.groupby("scenario")["expected_loss_change"].mean()
            st.bar_chart(chart_df)

        if "risk_grade_change" in filtered.columns:
            st.subheader("Risk-grade migrations: prior → current")
            mig = filtered.loc[filtered["risk_grade_change"]].groupby(
                ["risk_grade_prior", "risk_grade_current"], dropna=False
            ).size().rename("count").reset_index()
            st.dataframe(mig, use_container_width=True)

        if "property_type" in filtered.columns and "is_flagged" in filtered.columns:
            st.subheader("Flagged records by property type")
            by_pt = filtered.groupby("property_type")["is_flagged"].sum()
            st.bar_chart(by_pt)

        st.subheader("Row counts: prior vs current")
        st.bar_chart(pd.Series({
            "prior": overview["prior_row_count"],
            "current": overview["current_row_count"],
        }))


with tab_report:
    st.subheader("Review report (Markdown)")
    report_md = build_review_report(
        overview=overview, qa=qa, flagged_df=flagged,
        n_flagged=n_flagged_total,
        pd_threshold=pd_threshold, el_threshold=el_threshold,
    )
    st.markdown(report_md)

    st.divider()
    st.subheader("Downloads")

    if "is_flagged" in flagged.columns and flagged["is_flagged"].any():
        flagged_csv = flagged[flagged["is_flagged"]].to_csv(index=False).encode("utf-8")
        st.download_button("Download flagged_records.csv", flagged_csv,
                           file_name="flagged_records.csv", mime="text/csv")

    qa_summary_rows = [
        {"check": "required_columns_missing_prior",   "result": str(qa["required_columns_missing_prior"])},
        {"check": "required_columns_missing_current", "result": str(qa["required_columns_missing_current"])},
        {"check": "duplicate_keys_prior_count",       "result": len(qa["duplicate_keys_prior"])},
        {"check": "duplicate_keys_current_count",     "result": len(qa["duplicate_keys_current"])},
        {"check": "out_of_range_pd_current_count",    "result": len(qa["out_of_range_pd_current"])},
        {"check": "out_of_range_el_current_count",    "result": len(qa["out_of_range_el_current"])},
        {"check": "scenario_coverage_changes",        "result": len(qa["scenario_coverage_delta"])},
        {"check": "columns_added",                    "result": str(qa["column_delta"]["added"])},
        {"check": "columns_removed",                  "result": str(qa["column_delta"]["removed"])},
        {"check": "flagged_records_total",            "result": n_flagged_total},
    ]
    qa_summary_csv = pd.DataFrame(qa_summary_rows).to_csv(index=False).encode("utf-8")
    st.download_button("Download qa_summary.csv", qa_summary_csv,
                       file_name="qa_summary.csv", mime="text/csv")

    st.download_button("Download markdown_review_report.md", report_md.encode("utf-8"),
                       file_name="markdown_review_report.md", mime="text/markdown")


# --- Agent-like QA workflow tab ---------------------------------------------

with tab_agents:
    st.subheader("Agent-Like QA Workflow")
    st.info(
        "This is a deterministic agent-like QA workflow. It does not use an LLM "
        "API and does not make autonomous decisions. Each agent runs a specific "
        "review check; the final review remains human-owned."
    )

    scenarios_list = (
        sorted(current_df["scenario"].dropna().unique())
        if "scenario" in current_df.columns else None
    )

    workflow = run_agentic_qa_workflow(
        prior_df=prior_df,
        current_df=current_df,
        comparison_df=merged,
        required_columns=REQUIRED_COLUMNS,
        important_columns=("pd_score", "expected_loss", "risk_grade", "scenario"),
        key_columns=("entity_id", "scenario"),
        pd_threshold=pd_threshold,
        expected_loss_threshold=el_threshold,
        valid_scenarios=scenarios_list,
    )

    overall = workflow["overall_status"]
    if overall == "fail":
        st.error(f"Overall agent QA status: FAIL")
    elif overall == "warning":
        st.warning(f"Overall agent QA status: WARNING")
    else:
        st.success(f"Overall agent QA status: PASS")
    st.caption(
        "Rule: `fail` if any agent fails; otherwise `warning` if any agent warns; "
        "otherwise `pass`. HumanReviewAgent is excluded from the rollup."
    )

    st.markdown("### Agent status")
    status_rows = [
        {
            "agent": r["agent_name"],
            "status": r["status"],
            "human_review_required": r["human_review_required"],
            "findings": len(r["findings"]),
        }
        for r in workflow["agent_results"]
    ]
    st.dataframe(pd.DataFrame(status_rows), use_container_width=True)

    st.markdown("### Priority findings")
    if workflow["priority_findings"]:
        for item in workflow["priority_findings"]:
            st.markdown(f"- {item}")
    else:
        st.write("_No fail or warning findings raised._")

    st.markdown("### Per-agent detail")
    for r in workflow["agent_results"]:
        with st.expander(f"{r['agent_name']} — {r['status'].upper()}"):
            if r["findings"]:
                for f in r["findings"]:
                    st.markdown(f"- {f}")
            else:
                st.write("_(no findings)_")
            if r["summary"]:
                st.json(r["summary"], expanded=False)

    st.markdown("### Human reviewer checklist")
    st.caption(
        "The workflow supports review. It does not approve, reject, or validate "
        "model methodology."
    )
    for item in workflow["checklist"]:
        st.checkbox(item, key=f"agent_checklist_{hash(item) & 0xFFFFFFFF}")

    st.markdown("### Download")
    agent_md = format_agent_summary_markdown(
        workflow["agent_results"],
        workflow["overall_status"],
        workflow["priority_findings"],
        workflow["checklist"],
    )
    st.download_button(
        "Download agent_review_summary.md",
        agent_md.encode("utf-8"),
        file_name="agent_review_summary.md",
        mime="text/markdown",
    )
