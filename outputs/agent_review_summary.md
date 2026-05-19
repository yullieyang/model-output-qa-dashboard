# Agent-Like QA Workflow — Review Summary

_Generated 2026-05-19. Draft for human review._

> This summary is produced by a deterministic agent-like QA workflow. It does not use an LLM API, does not make autonomous decisions, and does not approve or reject the model run. Final review remains human-owned.

## Overall status: **FAIL**

Status rule: `fail` if any agent fails, otherwise `warning` if any agent warns, otherwise `pass`. The `HumanReviewAgent` is excluded from this rollup because the gate is the human reviewer.

## Agent status

| agent                   | status   | human_review_required   |   finding_count |
|:------------------------|:---------|:------------------------|----------------:|
| SchemaCheckAgent        | PASS     | False                   |               1 |
| MissingValueAgent       | WARNING  | True                    |               2 |
| DuplicateKeyAgent       | PASS     | False                   |               1 |
| ScenarioCoverageAgent   | PASS     | False                   |               1 |
| RangeCheckAgent         | FAIL     | True                    |               1 |
| OutputDriftAgent        | WARNING  | True                    |               2 |
| RiskGradeMigrationAgent | WARNING  | True                    |               1 |
| HumanReviewAgent        | PASS     | True                    |               6 |

## Priority findings

- [WARN · MissingValueAgent] Important columns with nulls in current: {'expected_loss': 3}
- [WARN · MissingValueAgent] Columns that gained nulls vs prior: ['expected_loss']
- [FAIL · RangeCheckAgent] 1 row(s) with pd_score outside [0, 1].
- [WARN · OutputDriftAgent] 14 row(s) exceeded the pd_score change threshold of 0.02.
- [WARN · OutputDriftAgent] 22 row(s) exceeded the expected_loss change threshold of 20.0%.
- [WARN · RiskGradeMigrationAgent] 23 row(s) changed risk grade (13.2% of compared rows).

## Detailed findings by agent

### SchemaCheckAgent — PASS

- Schema matches between prior and current.

- **required_columns_missing_prior**: []
- **required_columns_missing_current**: []
- **columns_added**: []
- **columns_removed**: []
- **dtype_changes**: []

### MissingValueAgent — WARNING

- Important columns with nulls in current: {'expected_loss': 3}
- Columns that gained nulls vs prior: ['expected_loss']

- **total_nulls_prior**: 0
- **total_nulls_current**: 3
- **null_count_delta**: 3
- **important_column_nulls_prior**: pd_score=0; expected_loss=0; risk_grade=0; scenario=0
- **important_column_nulls_current**: pd_score=0; expected_loss=3; risk_grade=0; scenario=0
- **columns_with_new_nulls**: ['expected_loss']

### DuplicateKeyAgent — PASS

- No duplicates on the composite key.

- **key_columns**: ['entity_id', 'scenario']
- **duplicate_row_count_prior**: 0
- **duplicate_row_count_current**: 0
- **duplicate_count_delta**: 0

### ScenarioCoverageAgent — PASS

- Scenario coverage matches between prior and current.

- **scenarios_in_prior_only**: []
- **scenarios_in_current_only**: []
- **scenario_counts_prior**: baseline=48; interest_rate_stress=48; commodity_price_stress=48; downside_macro=48
- **scenario_counts_current**: interest_rate_stress=49; downside_macro=49; baseline=48; commodity_price_stress=48
- **shared_scenario_count_changes**: baseline={'prior_count': 48, 'current_count': 48, 'delta': 0}; commodity_price_stress={'prior_count': 48, 'current_count': 48, 'delta': 0}; downside_macro={'prior_count': 48, 'current_count': 49, 'delta': 1}; interest_rate_stress={'prior_count': 48, 'current_count': 49, 'delta': 1}

### RangeCheckAgent — FAIL

- 1 row(s) with pd_score outside [0, 1].

- **pd_score_out_of_range_count**: 1
- **expected_loss_negative_count**: 0
- **invalid_risk_grade_count**: 0
- **invalid_scenario_count**: 0
- **valid_risk_grades**: ['A', 'B', 'C', 'D', 'E']
- **valid_scenarios**: ['baseline', 'commodity_price_stress', 'downside_macro', 'interest_rate_stress']

### OutputDriftAgent — WARNING

- 14 row(s) exceeded the pd_score change threshold of 0.02.
- 22 row(s) exceeded the expected_loss change threshold of 20.0%.

- **row_count**: 174
- **pd_threshold**: 0.02
- **expected_loss_threshold**: 0.2
- **pd_breach_count**: 14
- **expected_loss_breach_count**: 22
- **avg_abs_pd_change**: 0.011879885057471267
- **avg_abs_expected_loss_change**: 66085.14257309941
- **top_pd_moves** (5 item(s)):

| entity_id   | scenario             |   pd_score_prior |   pd_score_current |   pd_score_change |
|:------------|:---------------------|-----------------:|-------------------:|------------------:|
| ENT_016     | downside_macro       |           0.0929 |             1.25   |            1.1571 |
| ENT_042     | downside_macro       |           0.0688 |             0.1197 |            0.0509 |
| ENT_019     | downside_macro       |           0.0927 |             0.139  |            0.0463 |
| ENT_042     | interest_rate_stress |           0.0563 |             0.0979 |            0.0416 |
| ENT_019     | interest_rate_stress |           0.0759 |             0.1138 |            0.0379 |

- **top_expected_loss_moves** (5 item(s)):

| entity_id   | scenario               |   expected_loss_prior |   expected_loss_current |   expected_loss_change |   expected_loss_pct_change |
|:------------|:-----------------------|----------------------:|------------------------:|-----------------------:|---------------------------:|
| ENT_042     | commodity_price_stress |              377140   |                656223   |               279083   |                   0.74     |
| ENT_042     | downside_macro         |              518944   |                902872   |               383928   |                   0.739826 |
| ENT_042     | interest_rate_stress   |              424659   |                738439   |               313780   |                   0.738899 |
| ENT_042     | baseline               |              314534   |                546853   |               232318   |                   0.738609 |
| ENT_037     | downside_macro         |               20807.7 |                 33764.9 |                12957.2 |                   0.622711 |


### RiskGradeMigrationAgent — WARNING

- 23 row(s) changed risk grade (13.2% of compared rows).

- **rows_compared**: 174
- **rows_with_grade_change**: 23
- **share_with_grade_change**: 0.13218390804597702
- **migration_table** (7 item(s)):

| risk_grade_prior   | risk_grade_current   |   count |
|:-------------------|:---------------------|--------:|
| A                  | B                    |       1 |
| B                  | C                    |       3 |
| C                  | B                    |       4 |
| C                  | D                    |      11 |
| D                  | C                    |       2 |
| D                  | E                    |       1 |
| E                  | D                    |       1 |

- **largest_migrations** (5 item(s)):

| entity_id   | scenario               | risk_grade_prior   | risk_grade_current   |   notch_delta |
|:------------|:-----------------------|:-------------------|:---------------------|--------------:|
| ENT_003     | interest_rate_stress   | C                  | D                    |             1 |
| ENT_003     | downside_macro         | C                  | D                    |             1 |
| ENT_004     | interest_rate_stress   | C                  | D                    |             1 |
| ENT_007     | commodity_price_stress | E                  | D                    |             1 |
| ENT_009     | interest_rate_stress   | C                  | D                    |             1 |


### HumanReviewAgent — PASS

- [WARN · MissingValueAgent] Important columns with nulls in current: {'expected_loss': 3}
- [WARN · MissingValueAgent] Columns that gained nulls vs prior: ['expected_loss']
- [FAIL · RangeCheckAgent] 1 row(s) with pd_score outside [0, 1].
- [WARN · OutputDriftAgent] 14 row(s) exceeded the pd_score change threshold of 0.02.
- [WARN · OutputDriftAgent] 22 row(s) exceeded the expected_loss change threshold of 20.0%.
- [WARN · RiskGradeMigrationAgent] 23 row(s) changed risk grade (13.2% of compared rows).

- **agent_count**: 7
- **fail_count**: 1
- **warning_count**: 3
- **pass_count**: 3
- **priority_items**: ["[WARN · MissingValueAgent] Important columns with nulls in current: {'expected_loss': 3}", "[WARN · MissingValueAgent] Columns that gained nulls vs prior: ['expected_loss']", '[FAIL · RangeCheckAgent] 1 row(s) with pd_score outside [0, 1].', '[WARN · OutputDriftAgent] 14 row(s) exceeded the pd_score change threshold of 0.02.', '[WARN · OutputDriftAgent] 22 row(s) exceeded the expected_loss change threshold of 20.0%.', '[WARN · RiskGradeMigrationAgent] 23 row(s) changed risk grade (13.2% of compared rows).']
- **checklist**: ['Confirm the source inputs to the model run match the documented data cut.', 'Confirm scenario coverage changes are intentional.', 'Confirm new and dropped entities are documented (onboarding, exits, sales).', 'Confirm large output movements have a documented driver (data, scenario, methodology).', 'Confirm risk-grade migrations have been reviewed by a credit reviewer.', 'Record reviewer name, date, and any open items.', 'Inspect rows with new or important-column nulls before sign-off.', 'Fix out-of-range or invalid-category values at the source extract.', 'Walk through the top pd_score and expected_loss movers; confirm drivers.', 'Walk through the migration table with the credit reviewer.']

## Human reviewer checklist

- [ ] Confirm the source inputs to the model run match the documented data cut.
- [ ] Confirm scenario coverage changes are intentional.
- [ ] Confirm new and dropped entities are documented (onboarding, exits, sales).
- [ ] Confirm large output movements have a documented driver (data, scenario, methodology).
- [ ] Confirm risk-grade migrations have been reviewed by a credit reviewer.
- [ ] Record reviewer name, date, and any open items.
- [ ] Inspect rows with new or important-column nulls before sign-off.
- [ ] Fix out-of-range or invalid-category values at the source extract.
- [ ] Walk through the top pd_score and expected_loss movers; confirm drivers.
- [ ] Walk through the migration table with the credit reviewer.

### Reviewer sign-off

- Reviewer name: _________________________
- Sign-off date: _________________________
- Open items / follow-ups:

  - 
  - 
  - 

## Limitations

- The agent-like workflow is deterministic and intentionally narrow. It does not validate model methodology, assess economic reasonableness, or draw conclusions from the data.
- Thresholds are user-defined; whether a record is flagged is not an opinion of correctness.
- No LLM, AI, or cloud service is called by this workflow.
- This output is a draft for review; it is not a release approval.
