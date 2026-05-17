# model-output-qa-dashboard

## Tagline

A Streamlit dashboard that compares a prior and a current model-output
extract and helps an analyst run quarterly model-release QA on top of it.

## Project overview

This is a portfolio-style prototype that demonstrates how a recurring
quarterly model-output review can be packaged into a small, deterministic,
reviewable Streamlit dashboard. Given two CSVs — the prior release and
the current release — the app runs a fixed set of QA checks (missing
values, duplicate keys, schema differences, out-of-range values, scenario
coverage), joins the two extracts on `(entity_id, scenario)`, computes
row-level deltas on the numeric columns, and lets an analyst flag rows
whose `pd_score`, `expected_loss`, or `risk_grade` changed beyond a
user-defined threshold. The app produces a downloadable Markdown review
report with a human-reviewer checklist.

The dashboard does not interpret the data. It surfaces facts a reviewer
needs to act on, and the reviewer makes every call.

This project uses synthetic model output data inspired by recurring
financial/economic model review workflows. It is separate from the
[`r-macro-trade-commodity-forecast`](https://github.com/yullieyang/r-macro-trade-commodity-forecast)
repository (which is built on FRED macro / trade / commodity data), but
follows the same portfolio theme of reproducible, reviewable analytical
workflows.

## Why this matters

Quarterly model releases are dense events. Between two releases the
underlying data is refreshed, segmentations shift, scenarios may be
added or retired, and the model code itself may have been updated. A
reviewer needs to triage a large number of small changes and pull the
few that need a real conversation with the modeler or with the credit
team out of the noise. A small, deterministic dashboard that runs the
same checks the same way every quarter — and writes them down — is the
right scaffolding for that work. It does not replace the conversation;
it makes the conversation more efficient.

## What this project demonstrates

- Building a reproducible Python data-QA workflow around an explicit
  schema.
- Translating recurring review questions ("did anything new show up?",
  "did anything fall off?", "what moved most?") into deterministic
  pandas operations.
- Designing a Streamlit UI that lets a reviewer adjust thresholds and
  filters without changing the underlying logic.
- Generating a downloadable Markdown report with a human-reviewer
  checklist, so the review is captured as an artifact and not just an
  ephemeral browser session.
- Writing a synthetic data generator that injects realistic edge cases
  (large pd moves, scenario coverage changes, out-of-range values).

## Repository structure

```
model-output-qa-dashboard/
├── README.md
├── .gitignore
├── requirements.txt
├── app.py                              # Streamlit entry point
├── data/
│   ├── prior_model_outputs.csv         # Synthetic — generated locally
│   └── current_model_outputs.csv       # Synthetic — generated locally
├── docs/
│   ├── agentic_qa_workflow.md          # Agent-like workflow design
│   └── human_review_gate.md            # Human review responsibilities
├── src/
│   ├── generate_sample_data.py         # Synthetic data generator
│   ├── qa_checks.py                    # Deterministic QA functions
│   ├── compare_outputs.py              # Row-level join + deltas + flagging
│   ├── report_utils.py                 # Markdown review report builder
│   ├── qa_agents.py                    # Agent-like QA components
│   └── agent_orchestrator.py           # Orchestrator + markdown summary
└── outputs/
    └── agent_review_summary.md         # Sample summary from bundled data
```

## Workflow

1. **Inputs.** The reviewer uploads two CSVs — the prior model run and
   the current run — through the sidebar. If nothing is uploaded, the
   app falls back to the bundled sample data under `data/`.
2. **Deterministic QA.** The "Deterministic QA" tab runs schema checks,
   missing-value reports, duplicate-key detection, out-of-range checks,
   and scenario-coverage comparisons. Nothing is interpreted; everything
   is counted.
3. **Row-level comparison.** The "Record comparison" tab joins the two
   files on `(entity_id, scenario)`, computes `pd_score_change`,
   `expected_loss_change`, `expected_loss_pct_change`, and a boolean
   `risk_grade_change`. Sidebar filters narrow the view.
4. **Flagging.** Two sidebar sliders set the `pd_score` absolute-change
   threshold and the `expected_loss` percent-change threshold. Any row
   that exceeds either threshold, or whose `risk_grade` changed, is
   flagged.
5. **Charts.** The "Charts" tab renders a small set of standard visuals
   (Δ pd_score distribution, Δ expected_loss by scenario, risk-grade
   migrations, flagged records by property type, row-count comparison).
6. **Review report + downloads.** The "Review report" tab renders the
   full Markdown review and exposes three downloads: the flagged-records
   CSV, a QA summary CSV, and the Markdown report itself.

## Agent-Like QA Workflow

This project includes a deterministic **agent-like QA workflow** where
modular review components perform specific checks such as schema
validation, missing-value review, duplicate key detection, scenario
coverage review, output drift detection, risk grade migration review,
range checks, and human-reviewer summary generation.

The workflow does **not** use an LLM API and does **not** make
autonomous decisions. It borrows the orchestration pattern from
agentic systems — separate components with single responsibilities and
a uniform result shape, run in a fixed order, and aggregated into a
single summary — while keeping the actual QA checks deterministic,
auditable, and reproducible.

### Agents

| Agent | Responsibility |
|-------|----------------|
| `SchemaCheckAgent` | Required columns, added/removed columns, dtype drift. |
| `MissingValueAgent` | Null counts, changes vs prior, nulls in important columns. |
| `DuplicateKeyAgent` | Duplicate composite-key rows in prior and current. |
| `ScenarioCoverageAgent` | Scenarios in prior only / current only, count changes. |
| `RangeCheckAgent` | `pd_score` in [0,1], non-negative `expected_loss`, valid grades. |
| `OutputDriftAgent` | Rows exceeding pd_score / expected_loss thresholds, top movers. |
| `RiskGradeMigrationAgent` | Count of grade changes, migration table, largest notch deltas. |
| `HumanReviewAgent` | Composes the human-reviewer checklist and priority findings. |

Each agent returns a dictionary with `agent_name`, `status`
(`pass` / `warning` / `fail`), `summary`, `findings`, and
`human_review_required`.

### How to run the agent-like workflow

The workflow is reachable two ways:

- **Streamlit tab.** Open the dashboard and click the
  "Agent-Like QA Workflow" tab. It shows the overall status, an agent
  status table, priority findings, expandable per-agent detail, the
  human-reviewer checklist, and a download button for
  `agent_review_summary.md`.
- **Programmatically.** Call `run_agentic_qa_workflow(...)` from
  `src/agent_orchestrator.py`. It returns a dict with `agent_results`,
  `overall_status`, `priority_findings`, and `checklist`. Render to
  Markdown with `format_agent_summary_markdown(...)`.

A sample summary generated from the bundled synthetic data is checked
in at [`outputs/agent_review_summary.md`](outputs/agent_review_summary.md).

### Documentation

- [`docs/agentic_qa_workflow.md`](docs/agentic_qa_workflow.md) — design
  of the agent-like layer, agent list, orchestration flow, and what
  the workflow does and does not do.
- [`docs/human_review_gate.md`](docs/human_review_gate.md) — what the
  human reviewer is responsible for, how to interpret
  pass / warning / fail, and the sign-off checklist.

### What the agent-like workflow does not do

- It does **not** call an LLM, Claude, OpenAI, or any AI / cloud
  service.
- It does **not** make autonomous decisions or approve a model run.
- It does **not** validate model methodology or economic
  reasonableness.
- It is **not** production-ready. It is a portfolio prototype using
  synthetic data.

### Workflow summary

This dashboard includes a deterministic agent-like QA workflow where
modular review components perform specific checks such as schema
validation, missing-value review, duplicate key detection, scenario
coverage review, output drift detection, risk grade migration review,
range checks, and human review summary generation.

The workflow does not use an LLM API and does not make autonomous
decisions. It borrows the orchestration pattern from agentic systems
while keeping the actual QA checks deterministic, auditable, and
reproducible.

## Data / inputs

Inputs are **synthetic and fictional**. They are generated locally by
`src/generate_sample_data.py` with a fixed random seed, so the dashboard
is fully reproducible from a clean clone. No real portfolio data,
proprietary methodology, or non-public source is involved.

Expected schema (10 columns):

| Column              | Type    | Notes |
|---------------------|---------|-------|
| `entity_id`         | str     | Synthetic `ENT_xxx` identifier |
| `portfolio_segment` | str     | `large_balance` / `mid_market` / `small_balance` |
| `property_type`     | str     | `multifamily` / `office` / `retail` / `industrial` / `hospitality` |
| `scenario`          | str     | `baseline` / `interest_rate_stress` / `commodity_price_stress` / `downside_macro` |
| `quarter`           | str     | e.g. `2026Q1` |
| `pd_score`          | float   | Probability of default in [0, 1] |
| `risk_grade`        | str     | A / B / C / D / E (bucketed from `pd_score`) |
| `expected_loss`     | float   | Dollar expected loss |
| `model_version`     | str     | Free-form version string |
| `run_date`          | date    | ISO date string |

## Methods

The dashboard logic is deterministic and intentionally simple. There is
**no LLM API call** anywhere in the dashboard, no external model call,
and no API key required.

- **QA checks (`src/qa_checks.py`).** Counts, set differences, and range
  checks. Each function is pure with respect to disk.
- **Comparison (`src/compare_outputs.py`).** Inner-merge on
  `(entity_id, scenario)`. Deltas are computed as
  `current - prior` for numeric columns and as an inequality check for
  `risk_grade`.
- **Flagging.** Threshold-based. A row is flagged if any of:
  `|Δpd_score| > pd_threshold`, `|Δexpected_loss| / prior >
  expected_loss_pct_threshold`, or `risk_grade` differs. Thresholds are
  user-set in the sidebar; the dashboard does not pretend to know what
  the right threshold is.

AI coding tools may support scaffolding, documentation review, and
consistency checks, but the workflow logic, assumptions, validation
criteria, and final outputs remain human-reviewed. The runtime
dashboard itself does not call any external AI service.

## Outputs

- The on-screen dashboard with QA, comparison, charts, and review tabs.
- `flagged_records.csv` — every row exceeding any threshold.
- `qa_summary.csv` — one-row-per-check tally of the deterministic
  findings.
- `markdown_review_report.md` — full review report with a human-reviewer
  checklist and a reviewer sign-off block, ready to be saved alongside
  the model release artifacts.

## How to run

```bash
pip install -r requirements.txt
python src/generate_sample_data.py   # produces sample CSVs in data/
streamlit run app.py
```

The Streamlit app opens at `http://localhost:8501` by default. With no
uploads, the dashboard reads the bundled sample CSVs.

## Reviewability and documentation

- All logic lives in small, single-responsibility modules under `src/`.
  Each function has a docstring; functions are pure.
- The synthetic data generator is checked in, so the bundled CSVs are
  fully reproducible from `python src/generate_sample_data.py`.
- The Markdown report has a human-reviewer checklist and an explicit
  reviewer sign-off block, so the review is captured as an artifact
  that can live in version control alongside the model release.
- The codebase is small enough to review in a single sitting — under
  900 lines including the synthetic data generator and the dashboard
  itself.

## Responsible use

- The dashboard surfaces facts; it does not draw conclusions. A row
  being flagged means a threshold was crossed, not that the model is
  wrong. A row being unflagged means no threshold was crossed, not that
  the model is right.
- No external AI or model service is called. The dashboard runs entirely
  in-process.
- Do not paste real portfolio data into a copy of this dashboard that is
  hosted on a third-party service without first confirming that the
  hosting context is appropriate for the data classification.
- The Markdown review report explicitly includes a "Reviewer sign-off"
  block; a model release should not be approved on the basis of an
  unsigned report.

## Portfolio Context

This project translates recurring patterns from analytical work — model
output review, data QA, change detection, and human-in-the-loop
validation — into a public, synthetic portfolio prototype. It uses
synthetic model output data, not proprietary or internal data, and does
not replicate any internal system. The goal is to demonstrate
reproducible, reviewable workflow design for quarterly model-release QA.

## What this project does not do

- It does **not** validate model methodology, fit, or economic
  reasonableness.
- It does **not** make any business decision or recommendation.
- It does **not** replace analyst, credit, or modeler judgment.
- It does **not** call any external LLM, AI, or cloud service.
- It does **not** require any API key or external credential.
- It does **not** use FRED data or any data from the
  [`r-macro-trade-commodity-forecast`](https://github.com/yullieyang/r-macro-trade-commodity-forecast)
  repository.
- It does **not** ship a deployment pipeline; running it on a hosted
  Streamlit instance is out of scope.

## Limitations

- The QA logic is intentionally narrow. A real release-QA workflow would
  add reasonableness checks, segment-level reconciliations against an
  expected-value source, and a model-methodology review that this
  dashboard cannot perform.
- The flagging rules are simple thresholds. They do not weight by
  exposure, account for autocorrelation in the panel, or learn from
  reviewer feedback.
- The dashboard reads CSVs only. Parquet / database / API inputs would
  need a thin adapter on top of `pd.read_csv()`.
- There is no audit log of who flagged what or who signed off; the
  Markdown report relies on the reviewer's discipline to fill in the
  sign-off block.
- The synthetic data generator uses a fixed seed; running it again
  produces the same data. That is intentional for review, but means the
  bundled sample doesn't exercise edge cases beyond the ones injected.

## Future improvements

- Add a per-segment reconciliation table that compares aggregate
  expected loss against a documented expected-value reference per
  segment.
- Add a small `pytest` suite that asserts the deterministic QA functions
  on hand-constructed fixtures.
- Add a SQLite-backed run log so each review is stored with the
  reviewer's name, date, and decisions.
- Wire up a `pre-commit` hook that runs the deterministic QA against a
  known-good fixture before every commit to a model-release branch.
- Replace the simple Markdown report with a Quarto-rendered briefing
  template that includes the chart panel.

## Skills demonstrated

- Designing a deterministic, schema-aware QA workflow in Python /
  pandas.
- Building a small, modular Streamlit app with sensible sidebar
  controls and clean tab structure.
- Generating realistic synthetic data with edge cases that exercise
  every QA path.
- Translating recurring review questions into reviewable code
  artifacts (the Markdown report and the CSV downloads).
- Documentation discipline — limitations, "what this does not do", and
  reproducibility instructions all kept current in the README.

## Project summary

A Streamlit dashboard for quarterly model-output review. The app loads
two CSVs — the prior release and the current release — and walks a
reviewer through a standard quarterly checklist: missing values,
duplicate keys, schema differences, scenario coverage, and row-level
deltas on `pd_score`, `expected_loss`, and `risk_grade`. The reviewer
sets the flagging thresholds, filters by segment / property type /
scenario, and downloads a Markdown report with a human-reviewer
sign-off block. Everything is deterministic; there is no LLM call
anywhere in the runtime.

### Design rationale

- **The workflow is the deliverable, not the math.** The value of a
  recurring QA dashboard is in turning the same questions ("what's
  new, what's gone, what moved most") into the same checks every
  quarter, plus a Markdown artifact the reviewer signs off on. The
  dashboard makes the recurring review reproducible.
- **Flagging is honest.** Thresholds are user-set sliders. A flagged
  record is a record that crossed a threshold the reviewer chose, not
  a record the dashboard claims is wrong. The README and the report
  explicitly say so.
- **No external dependencies at runtime.** No LLM, no API key, no
  cloud service. That is a useful property in policy-adjacent or
  financial review contexts where shipping data through a third-party
  model is not always appropriate.

### Honest limitations

- The QA logic is narrow by design. A real release QA workflow also
  needs reasonableness checks, segment reconciliations, and a
  methodology review the dashboard cannot do.
- The flagging rules are simple thresholds. They do not weight by
  exposure or account for known recent model changes.
- There is no audit log. The Markdown report has a sign-off block,
  but the dashboard relies on the reviewer's discipline to fill it
  in.

## GitHub description

> Streamlit dashboard for model output QA, data cut review, and
> human-in-the-loop validation.

(106 chars.)
