"""Orchestrate the deterministic QA agents in a fixed order.

The orchestrator runs each agent from `src.qa_agents` against the
prior/current/comparison frames, aggregates the results into an overall
status, and renders a Markdown summary that the dashboard or a reviewer
can save next to the model release artifacts.

There is no LLM, no autonomous decision-making, and no external API
call anywhere in this module. The "agent" terminology refers only to
the orchestration pattern — each step is a deterministic function with
a single, named review responsibility.
"""

from __future__ import annotations

from datetime import date
from io import StringIO
from typing import Any, Sequence

import pandas as pd

from src.qa_agents import (
    AgentResult,
    DuplicateKeyAgent,
    HumanReviewAgent,
    MissingValueAgent,
    OutputDriftAgent,
    RangeCheckAgent,
    RiskGradeMigrationAgent,
    ScenarioCoverageAgent,
    SchemaCheckAgent,
)


WorkflowResult = dict[str, Any]


def _overall_status(agent_results: Sequence[AgentResult]) -> str:
    """Fold per-agent statuses into a single overall status."""
    statuses = {r["status"] for r in agent_results if r["agent_name"] != "HumanReviewAgent"}
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "pass"


def run_agentic_qa_workflow(
    prior_df: pd.DataFrame,
    current_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    required_columns: Sequence[str],
    important_columns: Sequence[str],
    key_columns: Sequence[str],
    pd_threshold: float,
    expected_loss_threshold: float,
    valid_scenarios: Sequence[str] | None = None,
    valid_risk_grades: Sequence[str] = ("A", "B", "C", "D", "E"),
) -> WorkflowResult:
    """Run all agents in order and return a structured workflow result.

    Returns a dict with:
        - agent_results: list of per-agent result dicts (in run order)
        - overall_status: "pass" | "warning" | "fail"
        - priority_findings: flattened list of warning/fail findings
        - checklist: human-reviewer checklist
    """
    schema = SchemaCheckAgent(required_columns=required_columns).run(prior_df, current_df)
    missing = MissingValueAgent(important_columns=important_columns).run(prior_df, current_df)
    dup = DuplicateKeyAgent(key_columns=key_columns).run(prior_df, current_df)
    scenario = ScenarioCoverageAgent().run(prior_df, current_df)
    range_check = RangeCheckAgent(
        valid_scenarios=valid_scenarios,
        valid_risk_grades=valid_risk_grades,
    ).run(current_df)
    drift = OutputDriftAgent(
        pd_threshold=pd_threshold,
        expected_loss_threshold=expected_loss_threshold,
    ).run(comparison_df)
    migration = RiskGradeMigrationAgent(grade_order=valid_risk_grades).run(comparison_df)

    upstream_results = [schema, missing, dup, scenario, range_check, drift, migration]
    human = HumanReviewAgent().run(upstream_results)
    all_results = upstream_results + [human]

    overall = _overall_status(all_results)
    priority = list(human["summary"].get("priority_items", []))
    checklist = list(human["summary"].get("checklist", []))

    return {
        "agent_results": all_results,
        "overall_status": overall,
        "priority_findings": priority,
        "checklist": checklist,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

_STATUS_BADGE = {
    "pass": "PASS",
    "warning": "WARNING",
    "fail": "FAIL",
}


def _render_summary_block(summary: dict[str, Any]) -> str:
    """Render an agent's `summary` dict as a small Markdown block."""
    if not summary:
        return "_(no structured summary)_\n"
    lines: list[str] = []
    for k, v in summary.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            lines.append(f"- **{k}** ({len(v)} item(s)):")
            try:
                table_md = pd.DataFrame(v).to_markdown(index=False)
            except Exception:
                table_md = "  - " + "\n  - ".join(str(item) for item in v)
            lines.append("")
            lines.append(table_md)
            lines.append("")
        elif isinstance(v, dict) and v:
            preview = "; ".join(f"{kk}={vv}" for kk, vv in list(v.items())[:6])
            if len(v) > 6:
                preview += "; …"
            lines.append(f"- **{k}**: {preview}")
        else:
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines) + "\n"


def format_agent_summary_markdown(
    agent_results: Sequence[AgentResult],
    overall_status: str,
    priority_findings: Sequence[str],
    checklist: Sequence[str],
) -> str:
    """Render the agent-like QA workflow as a Markdown report."""
    buf = StringIO()
    buf.write("# Agent-Like QA Workflow — Review Summary\n\n")
    buf.write(f"_Generated {date.today().isoformat()}. Draft for human review._\n\n")
    buf.write(
        "> This summary is produced by a deterministic agent-like QA workflow. "
        "It does not use an LLM API, does not make autonomous decisions, and does "
        "not approve or reject the model run. Final review remains human-owned.\n\n"
    )

    buf.write(f"## Overall status: **{_STATUS_BADGE.get(overall_status, overall_status.upper())}**\n\n")
    buf.write("Status rule: `fail` if any agent fails, otherwise `warning` if any agent "
              "warns, otherwise `pass`. The `HumanReviewAgent` is excluded from this "
              "rollup because the gate is the human reviewer.\n\n")

    # --- Agent status table -------------------------------------------------
    buf.write("## Agent status\n\n")
    table_rows = [
        {
            "agent": r["agent_name"],
            "status": _STATUS_BADGE.get(r["status"], r["status"]),
            "human_review_required": r["human_review_required"],
            "finding_count": len(r["findings"]),
        }
        for r in agent_results
    ]
    buf.write(pd.DataFrame(table_rows).to_markdown(index=False))
    buf.write("\n\n")

    # --- Priority findings --------------------------------------------------
    buf.write("## Priority findings\n\n")
    if priority_findings:
        for item in priority_findings:
            buf.write(f"- {item}\n")
    else:
        buf.write("_No fail or warning findings raised._\n")
    buf.write("\n")

    # --- Per-agent detail ---------------------------------------------------
    buf.write("## Detailed findings by agent\n\n")
    for r in agent_results:
        buf.write(f"### {r['agent_name']} — {_STATUS_BADGE.get(r['status'], r['status'])}\n\n")
        if r["findings"]:
            for f in r["findings"]:
                buf.write(f"- {f}\n")
        else:
            buf.write("- _(no findings)_\n")
        buf.write("\n")
        buf.write(_render_summary_block(r["summary"]))
        buf.write("\n")

    # --- Human reviewer checklist ------------------------------------------
    buf.write("## Human reviewer checklist\n\n")
    if checklist:
        for item in checklist:
            buf.write(f"- [ ] {item}\n")
    else:
        buf.write("_No checklist items generated._\n")
    buf.write("\n")
    buf.write("### Reviewer sign-off\n\n")
    buf.write("- Reviewer name: _________________________\n")
    buf.write("- Sign-off date: _________________________\n")
    buf.write("- Open items / follow-ups:\n\n")
    buf.write("  - \n  - \n  - \n\n")

    # --- Limitations --------------------------------------------------------
    buf.write("## Limitations\n\n")
    buf.write("- The agent-like workflow is deterministic and intentionally narrow. "
              "It does not validate model methodology, assess economic reasonableness, "
              "or draw conclusions from the data.\n")
    buf.write("- Thresholds are user-defined; whether a record is flagged is not an "
              "opinion of correctness.\n")
    buf.write("- No LLM, AI, or cloud service is called by this workflow.\n")
    buf.write("- This output is a draft for review; it is not a release approval.\n")

    return buf.getvalue()
