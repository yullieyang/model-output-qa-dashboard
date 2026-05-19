# Human Review Gate

## Why human review is required

The agent-like QA workflow in this project is deterministic and narrow.
It counts, compares, and surfaces facts about the prior and current
model-output extracts. It does **not** decide whether the model run is
correct, whether the movements are reasonable, or whether the release
should ship. Those decisions sit with a human reviewer — the modeller,
a credit reviewer, or a model-review owner — and the workflow exists
to support that judgment, not to replace it.

The dashboard and the Markdown summary are the inputs to the review.
The reviewer is the gate.

## What reviewers should verify

Before signing off on the current model run, the reviewer should
confirm:

- The **source inputs** to the run match the documented data cut for
  the quarter.
- The **schema** of the current extract matches the documented schema.
  Added or removed columns have an owner and a documented reason.
- **New entities** in the current extract entered through the
  documented onboarding workflow.
- **Dropped entities** are accounted for (paid off, sold, exited).
- **Scenario coverage** changes (added or retired scenarios) are
  intentional and signed off by the scenario owner.
- **Large output movements** (pd_score or expected_loss above
  threshold) have a documented driver: a data revision, a scenario
  change, or a methodology update.
- **Risk-grade migrations** have been walked through with a credit
  reviewer.
- **Out-of-range values** are corrected at the source, not papered
  over.
- The reviewer's **name and sign-off date** are filled in on the
  Markdown report, along with any open items.

## How to interpret pass / warning / fail

Each agent returns one of three statuses:

- **pass** — the agent found no meaningful issue in its scope. This is
  not an opinion that the model is correct; it is an opinion that the
  agent's specific check has nothing to flag.
- **warning** — the agent found something a reviewer should look at.
  A warning is **not** a defect; it is a request for attention.
  Examples: a new column appeared, the null count increased, a
  scenario was retired, rows exceeded the drift threshold.
- **fail** — the agent found something severe enough that the
  downstream comparison cannot be trusted until it is fixed at the
  source. Examples: a required column is missing, the current extract
  has duplicate composite keys, pd_score values fall outside [0, 1].

A `fail` does **not** mean the model is broken. It means the extract
cannot be reviewed in its current shape and needs to be re-run, or the
schema fixed, before review can continue.

## How to review flagged records

The `OutputDriftAgent` reports the row counts that exceeded the
pd_score and expected_loss thresholds, plus the top 5 movers in each.
A reviewer should:

1. Pull the top movers from the `summary.top_pd_moves` and
   `summary.top_expected_loss_moves` lists.
2. For each, identify the entity, the scenario, and the prior/current
   values.
3. Ask: is there a documented driver? A scenario re-calibration, an
   exposure refresh, a methodology change, a data correction?
4. If yes — note the driver as a justification in the open-items
   section of the Markdown report.
5. If no — escalate to the modeller before sign-off.

Threshold-based flagging is a **triage tool**, not a defect detector.
A record exceeding the threshold means the reviewer should look at it;
it does not mean the record is wrong.

## How to review scenario coverage changes

The `ScenarioCoverageAgent` reports:

- Scenarios present in prior but absent in current (retired).
- Scenarios present in current but absent in prior (added).
- Per-scenario row count changes for the shared scenarios.

A reviewer should:

1. Confirm any retired scenario was intentionally removed, with a
   documented decision and an effective date.
2. Confirm any added scenario was intentionally introduced, with the
   scenario owner identified.
3. For row count drops on a shared scenario, confirm the drop matches
   entity exits or onboarding changes — it should not be silent.

## How to review large output drifts

The `OutputDriftAgent` lists the rows that exceeded the user-set
thresholds for `pd_score_change` and `expected_loss_pct_change`. These
thresholds are configurable in the Streamlit sidebar; a reviewer who
believes the defaults are too loose or too tight should adjust them
and re-run before sign-off.

For each row above threshold, the reviewer should:

- Confirm whether the entity changed segment, exposure, or property
  type between releases.
- Confirm whether the scenario itself was re-calibrated.
- Confirm whether the model version changed (the `model_version`
  column on the row will indicate this).
- Document the driver in the open-items section.

## What this workflow cannot determine

- Whether the model is **economically reasonable**.
- Whether a stress scenario is **calibrated correctly**.
- Whether expected-loss aggregates **reconcile** with a separately
  computed reference.
- Whether the **methodology** changes since the prior release are
  appropriate.
- Whether a flagged record represents a **real issue** vs an expected
  movement.

These are the questions a human reviewer answers. The workflow's job
is to make sure the reviewer is asking the right questions on the
right records.

## Sign-off checklist

The Markdown report from `agent_orchestrator.format_agent_summary_markdown`
includes a sign-off block. The reviewer should fill in:

- [ ] Reviewer name
- [ ] Sign-off date
- [ ] Any open items / follow-ups (one bullet per item)
- [ ] Confirmation that every `fail` finding has been resolved at the
      source extract.
- [ ] Confirmation that every `warning` finding has either been
      explained or noted as an open item.
- [ ] Confirmation that the source inputs match the documented data
      cut.
- [ ] Confirmation that the scenario set is the intended set for the
      quarter.
- [ ] Confirmation that risk-grade migrations have been reviewed by a
      credit reviewer.

The signed Markdown report should be saved alongside the model-release
artifacts. An unsigned report is not a release approval.

## Reminder

The workflow supports review. It does not approve, reject, or
validate model methodology. A `pass` rollup is **not** a model
sign-off; only the human reviewer is.
