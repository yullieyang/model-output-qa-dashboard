"""Generate synthetic prior and current model-output CSVs for QA review.

The output data is fictional. It is shaped like the kind of quarterly
model-output extract a credit-risk or scenario-analysis workflow might
produce, but the entity identifiers, scores, and grades are all generated
locally with a fixed random seed. No real portfolio data is involved.

Usage:
    python src/generate_sample_data.py

Writes:
    data/prior_model_outputs.csv
    data/current_model_outputs.csv

The two files are designed so that running the dashboard against them
exercises every QA path: new entities, dropped entities, large
pd_score moves, risk-grade migrations, scenario coverage changes, and a
few injected nulls / out-of-range values.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

SCENARIOS = ["baseline", "interest_rate_stress", "commodity_price_stress", "downside_macro"]
PROPERTY_TYPES = ["multifamily", "office", "retail", "industrial", "hospitality"]
PORTFOLIO_SEGMENTS = ["large_balance", "mid_market", "small_balance"]
RISK_GRADES = ["A", "B", "C", "D", "E"]

# Stress-scenario multipliers applied on top of the baseline pd_score for
# each entity. Calibrated so stress > baseline on average but not so far
# apart that flagging is trivial.
SCENARIO_PD_MULTIPLIER = {
    "baseline": 1.00,
    "interest_rate_stress": 1.35,
    "commodity_price_stress": 1.20,
    "downside_macro": 1.65,
}


def _risk_grade_for(pd_score: float) -> str:
    """Bucket pd_score into a 5-letter risk grade."""
    if pd_score < 0.010:
        return "A"
    if pd_score < 0.025:
        return "B"
    if pd_score < 0.060:
        return "C"
    if pd_score < 0.120:
        return "D"
    return "E"


def _build_baseline_panel(entity_ids: list[str], rng: random.Random) -> list[dict]:
    """Build the prior-period long panel: one row per (entity, scenario)."""
    rows: list[dict] = []
    for entity_id in entity_ids:
        property_type = rng.choice(PROPERTY_TYPES)
        portfolio_segment = rng.choice(PORTFOLIO_SEGMENTS)
        # Baseline PD distributed roughly log-normal in [0.002, 0.18]
        base_pd = round(min(max(rng.lognormvariate(-3.6, 0.7), 0.002), 0.18), 4)
        # Exposure drives loss; mid-market and large-balance tend higher
        exposure_base = {
            "small_balance": rng.uniform(0.5e6, 5e6),
            "mid_market": rng.uniform(5e6, 25e6),
            "large_balance": rng.uniform(25e6, 100e6),
        }[portfolio_segment]
        loss_given_default = rng.uniform(0.30, 0.55)

        for scenario in SCENARIOS:
            pd_score = round(min(base_pd * SCENARIO_PD_MULTIPLIER[scenario], 0.95), 4)
            expected_loss = round(pd_score * loss_given_default * exposure_base, 2)
            rows.append({
                "entity_id": entity_id,
                "portfolio_segment": portfolio_segment,
                "property_type": property_type,
                "scenario": scenario,
                "quarter": "2026Q1",
                "pd_score": pd_score,
                "risk_grade": _risk_grade_for(pd_score),
                "expected_loss": expected_loss,
                "model_version": "v3.2.0",
                "run_date": "2026-02-15",
            })
    return rows


def _perturb_for_current(prior_rows: list[dict], rng: random.Random) -> list[dict]:
    """Build the current-period panel from the prior with realistic drift.

    Drift behaviors injected:
    - 90% of entities: small PD perturbation in +/- 10%
    - 5% of entities: large PD move (>30%) to trigger flagging
    - 5% of entities: risk-grade migration
    - 3% of rows: scenario dropped (missing scenario coverage)
    - A handful of rows get nulls in expected_loss to exercise the
      missing-values check
    - One row gets an out-of-range pd_score (>1.0) to exercise the
      range check
    """
    rows: list[dict] = []
    # Group prior rows by entity so we can apply per-entity drift.
    by_entity: dict[str, list[dict]] = {}
    for r in prior_rows:
        by_entity.setdefault(r["entity_id"], []).append(r)

    for entity_id, entity_rows in by_entity.items():
        # Decide drift behavior for this entity.
        roll = rng.random()
        if roll < 0.05:
            drift_factor = rng.uniform(1.35, 1.80)   # large up-move
        elif roll < 0.10:
            drift_factor = rng.uniform(0.55, 0.75)   # large down-move
        else:
            drift_factor = rng.uniform(0.92, 1.10)   # routine drift

        for r in entity_rows:
            # 3% chance to drop this (entity, scenario) row in current
            if rng.random() < 0.03:
                continue

            new_pd = round(min(max(r["pd_score"] * drift_factor, 0.0005), 0.95), 4)
            new_el = round(
                new_pd / max(r["pd_score"], 0.0001) * r["expected_loss"], 2
            )

            rows.append({
                **r,
                "scenario": r["scenario"],
                "quarter": "2026Q2",
                "pd_score": new_pd,
                "risk_grade": _risk_grade_for(new_pd),
                "expected_loss": new_el,
                "model_version": "v3.3.0",
                "run_date": "2026-05-15",
            })

    # Inject a few null expected_loss values
    for _ in range(3):
        idx = rng.randrange(len(rows))
        rows[idx]["expected_loss"] = None

    # Inject one out-of-range pd_score
    if rows:
        idx = rng.randrange(len(rows))
        rows[idx]["pd_score"] = 1.25  # > 1.0 — should be flagged

    return rows


def main() -> None:
    rng = random.Random(20260517)
    n_prior_entities = 48

    prior_entity_ids = [f"ENT_{i:03d}" for i in range(1, n_prior_entities + 1)]

    prior_rows = _build_baseline_panel(prior_entity_ids, rng)

    # For the current panel, drop the last 3 entities (simulating exits)
    # and add 5 new ones.
    kept = prior_rows[: -3 * len(SCENARIOS)]
    current_rows = _perturb_for_current(kept, rng)

    new_entity_ids = [f"ENT_{i:03d}" for i in range(100, 105)]
    current_rows.extend(_build_baseline_panel(new_entity_ids, rng))
    # Bump quarter / version on the new entities too.
    for r in current_rows[-len(new_entity_ids) * len(SCENARIOS):]:
        r["quarter"] = "2026Q2"
        r["model_version"] = "v3.3.0"
        r["run_date"] = "2026-05-15"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(prior_rows).to_csv(DATA_DIR / "prior_model_outputs.csv", index=False)
    pd.DataFrame(current_rows).to_csv(DATA_DIR / "current_model_outputs.csv", index=False)

    print(f"Wrote {len(prior_rows)} prior rows to data/prior_model_outputs.csv")
    print(f"Wrote {len(current_rows)} current rows to data/current_model_outputs.csv")


if __name__ == "__main__":
    main()
