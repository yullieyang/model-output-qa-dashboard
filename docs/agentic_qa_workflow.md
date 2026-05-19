# Agent-Like QA Workflow

## Project purpose

`model-output-qa-dashboard` is a portfolio-style prototype for the
quarterly review of a model-output extract. The base dashboard runs a
fixed set of deterministic QA checks (schema, missing values, duplicate
keys, scenario coverage, row-level deltas) on two CSVs — the prior
release and the current release — and produces a Markdown review report
with a human-reviewer sign-off block.

This document describes a second layer on top of that base: a modular,
agent-like QA workflow that organises each review responsibility into a
small, single-purpose Python component.

## What "agent-like" means in this project

"Agent-like" here refers to the **orchestration pattern**, not to the
underlying technology. Each step of the review is encapsulated in a
small Python class with one responsibility and a uniform result shape.
An orchestrator runs the agents in a defined order and aggregates the
results into an overall status and a human-reviewer checklist.

What the agents do **not** do:

- They do not call an LLM, Claude, OpenAI, or any external AI API.
- They do not make autonomous decisions.
- They do not approve, reject, or validate the model run.
- They do not learn from prior runs or adjust their own behaviour.

What they **do** do:

- Encapsulate a single deterministic check (schema, nulls, duplicates,
  scenario coverage, range, output drift, risk-grade migration).
- Return a uniform result dictionary with `status`, `summary`,
  `findings`, and `human_review_required`.
- Plug into an orchestrator that produces a structured, downloadable
  Markdown summary.

The project borrows the orchestration pattern from agentic systems
because the pattern itself is useful — separate responsibilities, a
consistent interface, a fixed run order, and an aggregated summary at
the end. The actual review work, however, is implemented with
deterministic Python checks for auditability and reproducibility.

## Why no LLM API

This project is positioned around recurring model-output QA — the kind
of review that happens once a quarter, has compliance attention, and
needs to be reproducible from a clean clone. Two reasons to keep it
deterministic:

1. **Auditability.** A reviewer should be able to read the code,
   re-run it on the same inputs, and get bit-identical findings.
   Sampled or LLM-generated outputs cannot offer that guarantee.
2. **Data handling.** Even a synthetic prototype should not normalise
   the habit of sending portfolio-shaped data through a third-party
   service. The runtime here calls nothing external.

## Why deterministic QA is the safer pattern here

- Each finding can be traced to a specific line of pandas, and a
  reviewer can confirm the logic in seconds.
- Re-running on the same inputs produces identical outputs.
- Threshold-driven flags are user-set, not learned, so the reviewer
  controls what counts as a meaningful change.
- The workflow does not silently change behaviour between releases.

## Agents and their responsibilities

| Agent | Responsibility | Inputs |
|-------|----------------|--------|
| `SchemaCheckAgent` | Required columns present, columns added/removed, dtype drift. | `prior_df`, `current_df`, `required_columns` |
| `MissingValueAgent` | Null counts, change vs prior, nulls in important columns, new null columns. | `prior_df`, `current_df`, `important_columns` |
| `DuplicateKeyAgent` | Duplicate composite-key rows in prior and current. | `prior_df`, `current_df`, `key_columns` |
| `ScenarioCoverageAgent` | Scenarios in prior only / current only / both, count changes. | `prior_df`, `current_df`, `scenario_column` |
| `RangeCheckAgent` | `pd_score` in [0,1], `expected_loss >= 0`, valid risk grades, valid scenarios. | `current_df` |
| `OutputDriftAgent` | Rows exceeding pd_score / expected_loss thresholds, top movers, averages. | `comparison_df`, thresholds |
| `RiskGradeMigrationAgent` | Count of grade changes, migration table, largest notch deltas. | `comparison_df` |
| `HumanReviewAgent` | Composes the human-reviewer checklist and priority findings. | All prior agent results |

Each agent returns a dictionary with the same shape:

```python
{
    "agent_name":            "SchemaCheckAgent",
    "status":                "pass" | "warning" | "fail",
    "summary":               { ... structured findings ... },
    "findings":              [ "human-readable bullet", ... ],
    "human_review_required": True | False,
}
```

### Status rubric

- `pass` — no meaningful issue detected.
- `warning` — issue detected that a human reviewer should look at.
- `fail` — severe issue such as a missing required column, a duplicate
  composite key in the current extract, or an invalid range that breaks
  downstream comparison.

## Orchestration flow

`src/agent_orchestrator.py` exposes `run_agentic_qa_workflow(...)`. It
runs the agents in this fixed order:

1. `SchemaCheckAgent` — fail fast if the schema is broken.
2. `MissingValueAgent` — surface missingness before drift comparison.
3. `DuplicateKeyAgent` — duplicates would distort downstream joins.
4. `ScenarioCoverageAgent` — confirm scenario set is intact.
5. `RangeCheckAgent` — out-of-range values invalidate later metrics.
6. `OutputDriftAgent` — measure movement in pd_score and expected_loss.
7. `RiskGradeMigrationAgent` — summarise grade migrations.
8. `HumanReviewAgent` — compose the human-reviewer checklist.

The orchestrator returns:

- `agent_results` — list of per-agent result dicts in run order.
- `overall_status` — `fail` if any agent fails, else `warning` if any
  agent warns, else `pass`. `HumanReviewAgent` is excluded from this
  rollup because the gate is the human reviewer, not this function.
- `priority_findings` — flattened list of fail/warning findings from
  upstream agents.
- `checklist` — base checklist plus any agent-specific items added
  because an upstream agent flagged its area.

`format_agent_summary_markdown(...)` renders the result as a Markdown
report with the overall status, an agent status table, priority
findings, per-agent detail, the human-reviewer checklist, and a
sign-off block.

## How a human should review the output

1. Read the overall status. A `fail` means a downstream review cannot
   trust the comparison panel until the failing agent's finding is
   resolved at the source.
2. Read the priority findings list — these are the bullets a reviewer
   should be able to defend to the modeler or the credit team.
3. Walk the per-agent detail in the order the agents ran. The detail
   block has the structured `summary` dict with the raw counts.
4. Work the human-reviewer checklist top to bottom. Any item that
   cannot be confirmed becomes an open item in the sign-off block.
5. Save the Markdown report next to the model-release artifacts. The
   review is the artifact, not the dashboard session.

## What this workflow does not do

- It does **not** validate model methodology, fit, or economic
  reasonableness.
- It does **not** approve or reject a model release.
- It does **not** make any business decision.
- It does **not** replace credit, modeller, or analyst judgment.
- It does **not** call an LLM, Claude, OpenAI, or any external AI
  service.
- It does **not** require any API key or external credential.
- It is **not** production-ready. It is a portfolio prototype.

## Limitations

- The agents are narrow by design. A real release-QA workflow would
  add segment-level reconciliations, exposure-weighted drift metrics,
  and a model-methodology review that this prototype cannot perform.
- Status thresholds are simple. Pass/warning/fail boundaries are coded
  in the agents themselves; tuning them is a code change, not a
  config change.
- There is no persistent run log. The Markdown report is the audit
  artifact, and it depends on the reviewer's discipline to be saved.
- Synthetic data only. Running the workflow against a real extract
  requires the reviewer to confirm the schema matches `REQUIRED_COLUMNS`
  and that the bundled sample's threshold defaults are appropriate.

## Future improvements

- A `pytest` suite that asserts each agent's status logic on
  hand-constructed fixtures.
- A second orchestrator that runs the agents in parallel for very
  large extracts (the current run is sequential and synchronous).
- A configurable, YAML-driven thresholds file so tuning is not a code
  change.
- A SQLite-backed run log that captures `overall_status`, the priority
  findings, and the reviewer's name and sign-off date.
- A segment-level reconciliation agent that compares aggregate
  expected loss against a documented reference per segment.
