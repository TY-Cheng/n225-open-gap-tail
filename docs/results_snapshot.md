---
hide:
  - navigation
---

# Results Snapshot

> **Research-candidate full-run artifact.** This page is generated from `tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf`.
> It summarizes the durable gold modeling sample and run outputs, not the older
> bounded access-check snapshot. It is still a research-candidate artifact:
> final manuscript claims require a clean committed run and author review of the
> tables and notes.

## Discussion Q&A

### What is this project testing?

It tests whether timestamp-safe information available by the U.S. close cutoff helps forecast left-tail and right-tail risk for the next Osaka Nikkei 225 Futures day-session open.

- The object is tail risk, not average return prediction or an execution rule.
- The comparison is organized as an information ladder: Japan-only history first, then U.S. close core, then Japan proxy ETFs, then Asia proxy ETFs.
- The current page reports what the pipeline produced; it does not automatically make a model-selection claim.

### What exactly is being forecast?

The primary target is the loss version of the settle-to-open Nikkei futures gap for the OSE day-session open.

- Left and right tails are transformed into positive loss units and evaluated separately.
- Roll/SQ windows and invalid reference prices are excluded from clean target evidence.
- The residual U.S.-close mark target is disabled in this run because there is no licensed timestamped intraday Nikkei mark.

### Which Nikkei 225 Futures contract is used when many expiries trade?

The target source is the OSE Nikkei 225 Futures large contract, not mini or micro contracts.

- The J-Quants futures rows are first filtered to rows marked as the central contract month.
- The target audit then requires the day-session open and the previous reference settlement or close to come from the same contract where possible.
- Observations are removed from the clean target evidence when they cross a contract roll, last-trading-day boundary, SQ window, invalid reference price, or missing target field.
- Rule-based quarterly contract metadata exists for audit and diagnostics, but the empirical target is governed by audited J-Quants central-contract flags and same-contract target construction.

### Can returns from different expiries be pooled in one model?

Pooling is done at the observation level, not by stitching raw prices into a naive continuous futures price.

- The target audit first keeps the J-Quants row marked as the central contract month for each trading date.
- It then builds a history by `contract_code` and, for each central-contract row, searches backward inside the same `contract_code` to find the prior reference row.
- The settle-to-open gap is `log(current day-session open) - log(prior settlement)` from that same contract. The close-to-open gap is computed the same way with the same contract's prior day-session close.
- The audit carries `reference_contract_code`, `same_contract_only`, roll/SQ flags, and missing reasons so cross-contract references are visible rather than silently treated as returns.
- A row enters the clean target sample only when the reference is same-contract, the row is outside the roll/SQ window, and required prices are present.
- The model pool is then the time-ordered set of these clean gap observations across successive central quarterly contracts. Benchmarks and ML models fit one active-contract risk process on that pooled clean sample; ML lag and rolling-history features are updated only from clean rows.
- This is defensible for forecasting the active large-contract Nikkei 225 futures tail-risk surface. It does not claim that maturity-specific basis, liquidity, or time-to-expiry effects are fully modeled.

### Why is timing the central issue?

The forecast origin is the U.S. close plus vendor lag, and it must occur before the OSE target open. "U.S. close information" means information available by this cutoff; it does not mean all U.S. after-close or overnight news.

- Every joined predictor is audited against `feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`.
- FRED features are treated with timestamp-safe release lags; FRED historical values are not ALFRED vintage-safe.
- Leakage audit failures are zero in this run, but warnings remain visible below rather than hidden.

### Why does the clean sample start in 2018?

The requested data window begins earlier, but the clean forecast sample starts only when all required target and predictor blocks satisfy the registered coverage and timing gates.

- Earlier rows remain useful for target-history audit, raw-cache checks, and training history, but they are not forecast evidence under the current clean-sample contract.
- The clean start is driven by combined J-Quants required-field coverage, Massive daily entitlement coverage, required FRED coverage, and canonical FX timing coverage.
- Post-2018 rows satisfy the current clean-sample gates for the required headline blocks; isolated feature-level gaps are still audited, and enriched or optional blocks can have shorter histories unless promoted by a future specification.

### What has been implemented?

The benchmark floor, advanced benchmark suite, and ML-tail suite are implemented and have completed artifacts in this run.

- Benchmark floor models include target-history baselines and GARCH/EVT-style econometric floors.
- Advanced benchmark families such as CAViaR, CARE/expectile, Taylor ALD, direct FZ-loss, and GAS now produce nonblocking empirical forecast rows; their interpretation still follows the benchmark/restricted-sample gates.
- ML-tail models include direct LightGBM quantile, location-scale LightGBM, and standardized-loss POT-GPD.
- The headline ML-tail table remains strict: it currently keeps direct quantile rows because the newer tail-model variants have shorter common coverage.

### Why use LightGBM as the ML learner?

LightGBM is used as a fixed, tabular, nonlinear learner for the nested information-set experiment, not as an algorithmic novelty claim.

- It handles mixed market predictors, nonlinearities, and interactions without turning the paper into a broad model tournament.
- Hyperparameters are held fixed across information sets and refit dates to limit data-dependent tuning.
- The econometric benchmark suite remains the main non-ML comparison layer; LightGBM is the ML information-extraction layer.

### Why are POT-GPD and location-scale not in the headline ML table?

They are implemented, but they do not replace the headline direct-quantile ladder.

- The headline ladder uses the strict shared information-set sample and currently retains direct LightGBM quantile rows.
- Location-scale and standardized-loss POT-GPD rows are restricted or diagnostic evidence when their common-sample and tail-event gates are shorter.
- EVT should therefore be described as a tail-calibration and robustness layer in this run, not as the central headline empirical result.

### How should broad readers interpret the metrics?

Coverage diagnostics ask whether VaR exceptions are too frequent or too rare; quantile loss scores VaR accuracy; FZ loss scores VaR-ES pairs.

- Lower quantile loss is better only within a common sample and claim boundary.
- FZ loss is only meaningful for valid VaR-ES pairs and needs enough exceptions to avoid short-sample overinterpretation.
- Restricted result-matrix rows are useful diagnostics, not replacements for the headline information-set ladder.

### Why can benchmarks have better breach rates while ML has lower loss?

This pattern is supported by the current artifacts as a cautious interpretation, not as a model-selection claim.

- Benchmark floor breach rates are closer to the nominal 5% VaR level, so they are better calibrated on coverage.
- Some LightGBM information sets have lower quantile or FZ loss because their VaR levels are less conservative on average.
- Lower loss can therefore partly reflect a sharper or more aggressive VaR forecast, which is why coverage, loss, exception counts, and inference gates must be read together.

### Where does LightGBM help relative to benchmarks?

The current evidence supports a candidate information-extraction role, especially in the left-tail ladder after adding U.S. close core variables.

- It does not support a blanket statement that LightGBM is better calibrated than the benchmark floor.
- The reported tables evaluate average loss and breach behavior, not median conditional forecast quality.
- A median-effect claim would need an explicit median loss or paired distribution diagnostic; it is not a current headline result.

### What differs between left-tail and right-tail results?

The two risk surfaces are intentionally separated.

- Left-tail quantile loss changes most when U.S. close core variables are first added to Japan-only history.
- Right-tail changes are smaller at the U.S. core step and appear more dependent on later proxy blocks in the current ladder.
- The paper should therefore avoid treating upside and downside opening-gap risk as one symmetric mechanism.

### Which U.S. close core variables may be contributing?

The core block aggregates U.S. equity, sector, volatility, FX, rates, credit-risk, and late-session SPY features available by the cutoff.

- Plausible contributors include broad index ETFs, sector dispersion, VIX/Cboe volatility measures, Treasury-rate changes, USD/JPY controls, credit-risk proxies, and SPY late-session pressure.
- The current tables support block-level interpretation more than feature-level attribution.
- Any feature-level story should be presented as descriptive diagnostics unless supported by a dedicated attribution design.

### Do Japan proxy or Asia proxy ETFs add more?

In the current headline ladder, the largest change generally appears when U.S. close core variables are added.

- After U.S. close core, Japan proxy ETFs add more visible marginal loss reduction than the Asia proxy block.
- The Asia proxy block adds little incremental improvement in the current headline quantile-loss ladder and can slightly worsen the left-tail row.
- These proxy-block patterns are descriptive and should not be written as structural regional price-discovery claims.

### What is the main referee risk in the current evidence?

The most likely challenge is not whether the pipeline ran, but whether the claims are kept inside the evidence gates.

- ML headline breach rates are too high relative to the nominal VaR level, even where loss metrics improve.
- EVT and location-scale models are implemented but not headline-retained.
- "U.S. close information" must be defined as information available by the cutoff, not all after-close news.
- FRED is conservatively lagged but not ALFRED vintage-safe, and feature-level explanations remain descriptive.
- Final manuscript claims require a clean committed run and author review of tables, sample gates, and inference diagnostics.

### What is the current bottom line?

The pipeline is now producing full-run research-candidate evidence from the durable gold layer.

- The gold sample starts at the dynamic combined clean start, not the 2016 cache lower bound.
- Benchmark floor, advanced benchmark, and ML-tail suites completed with zero recorded forecast failures; advanced rows are implemented evidence but remain nonblocking until author-reviewed against the same sample/inference gates.
- Before manuscript claims, review the headline/restricted/diagnostic boundaries, inference gates, and vintage limitations rather than selecting a model from one metric.

### Which results can support headline claims?

| Evidence layer | Can support headline claim? | How to read it |
| --- | --- | --- |
| Benchmark common-sample table | Yes, after review | External target-history/econometric floor on a shared sample. |
| ML-tail headline ladder | Yes, after review | Strict information-set ladder; currently direct quantile survived the gate. |
| ML-tail per-model rows | No | Model-specific OOS diagnostics; samples need not match across model families. |
| Restricted result matrix | No headline claim | Matched-date comparison for model families and within-model increments. |
| DST, stress, Murphy, hedge-trigger diagnostics | Diagnostic only | Useful for interpretation and risk monitoring, not automatic model-selection evidence. |

- Headline claims require a clean committed run, a shared common sample, zero leakage failures, and author-reviewed tables.
- Restricted rows can explain model-family behavior on matched dates, but they cannot replace the headline information ladder.
- Diagnostic rows can motivate discussion and future checks; they should not be worded as model-selection or risk-management usefulness claims without their own evidence gates.


## Results And Discussion

<!-- generated: results_discussion -->

### Data and timing audit

- The gold timing map covers `2016-07-19 to 2026-04-30` and the combined clean start is `2018-06-20`.
- No forecast-sample rows before `2018-06-20` enter the modeling evidence.
- The leakage check reports status `pass_with_warnings` with zero leakage failures and `181544` warnings.
- FRED vintage safety is recorded as `False`; FRED values use conservative release timing but remain current historical observations rather than ALFRED real-time vintages.

### Benchmark floor and advanced benchmarks

- `benchmark_metrics.parquet` reports `12` common-sample rows across `6` benchmark model families and `2` tail side(s), while benchmark forecasts contain `21114` model-date rows.
- Benchmark-floor models are external target-history and econometric baselines; this section does not rank them.
- Advanced benchmark rows are implemented for `10` model families and contribute `13194` nonblocking forecast rows; these rows are claim-gated diagnostics unless a manuscript table explicitly promotes them through the same sample and inference review.
- Benchmark-floor breach rates have a median of `0.0606061`, within 2.5 percentage points of the nominal level, indicating reasonable coverage calibration relative to the ML-tail models whose breach rates are reported in the headline ladder section.

### Left/right ML-tail headline ladder

- `ml_tail_metrics.parquet` defines the headline ML-tail information-set ladder for this run.
- The headline artifact contains `4` information sets, `1` tail level(s), and `2` tail side(s); the retained headline model rows are `lightgbm_direct_quantile`.
- The implemented ML-tail registry is `lightgbm_direct_quantile`, `lightgbm_location_scale`, `lightgbm_standardized_loss_pot_gpd`, but the headline ladder should be read only from `ml_tail_metrics.parquet`.
- The ladder reports downside-risk and upside-risk surfaces separately. The registered artifacts show different left/right patterns, and the generator does not assume that the two sides share the same economic mechanism.
- Coverage warning: all `8` headline rows exhibit VaR breach rates (`0.0909091` to `0.125758`) that exceed the nominal level by more than 2.5 percentage points. Quantile-loss and FZ-loss differences across the information ladder must be interpreted in this context; lower loss scores may partly reflect more aggressive VaR levels rather than better conditional tail calibration.
- On `left_tail`, the largest quantile-loss change occurs at the first information-set augmentation (adding U.S. close core); subsequent additions of Japan proxy and Asia proxy ETFs contribute diminishing incremental loss changes. This saturation pattern is descriptive and does not automatically reduce the value of the broader information set.
- The ladder is used to assess candidate incremental U.S.-close information under strict common-sample rules; it does not by itself establish forecast improvement.

### Restricted model-family comparison

- `ml_tail_result_matrix.parquet` contains restricted common-sample comparisons for `3` LightGBM tail-model families.
- The restricted common-N range is `154 to 660` and the joint-exception range is `16 to 112`.
- Recorded claim scopes are `restricted_model_comparison_not_headline`; these rows are restricted evidence and cannot replace the headline information-set ladder.
- The tail-model family comparison is severely sample-limited: the largest restricted common-N is `154` rows. No model-family ranking claim is supportable from this restricted sample; extended OOS coverage is needed before tail-model family ranking becomes meaningful.
- Result-matrix inference is recorded separately from the headline suite-level DM/MCS: restricted DM records include `68` gate-pass rows and `34` unavailable rows; restricted MCS records include `0` gate-pass rows and `72` unavailable rows. These entries are restricted common-sample diagnostics, not headline model-family rankings.
- The result matrix is a matched-date diagnostic layer. It should not be worded as one family being better than another.

### Coverage and inference gates

- Coverage review flags `8/8` headline rows with breach rates more than 2.5 percentage points from nominal coverage; Kupiec p-values fall below 0.05 in `8/8` rows and Christoffersen p-values fall below 0.05 in `0/8` rows where reported.
- Model-eviction artifacts record `8` retained rows and `16` non-retained rows under the headline sample policy.
- Block-bootstrap DM and HLN Tmax MCS artifacts are unconditional forecast-comparison diagnostics; any p-value should be read on average across the unconditional evaluation sample, not as condition-specific evidence.
- Loss differentials alone do not constitute an improvement claim; coverage, exception counts, sample gates, and inference status must be reviewed together.
- Result-matrix tail-event power flags and suite-level inference gates report `0` restricted rows with insufficient tail-event power and `0/36` unavailable DM/MCS inference rows.

### CPA as conditional loss-difference diagnostics

- The ML-tail information-ladder CPA artifact is a conditional loss-difference diagnostic across `2` tail side(s), with `18` registered row(s), `18` HAC-Wald gate pass(es), and loss families `var_es_fz_loss`, `var_quantile_loss`.
- The registered cross-model CPA artifact is a conditional loss-difference diagnostic with `288` row(s), `288` HAC-Wald gate pass(es), and loss families `var_es_fz_loss`, `var_quantile_loss`.
- Quantile-loss CPA and FZ-loss CPA are downstream inference over existing loss differentials; CPA does not generate VaR/ES forecasts and does not replace DM/MCS.

### Supporting diagnostics

- Supporting LaTeX diagnostic table files are present for `4/4` registered diagnostic families.
- `ml_tail_dst_attenuation.parquet` contains `12` DST attenuation rows; these are descriptive timing-regime forecast diagnostics. They do not establish a structural timing mechanism.
- ES severity diagnostics contain `44` finite rows with mean exceedance severity ranging from `0.00406489` to `0.016966`; this is conditional-on-exception evidence.
- The diagnostic 75th-percentile VaR trigger rule marks `7320` model-date rows; `592` of those rows coincide with VaR exceptions out of `1977` total exceptions, and mean triggered exception severity is `0.0133733`. This is a pre-open risk-monitoring diagnostic, not hedge PnL, transaction-cost, or trading-alpha evidence.
- Stress-window diagnostics contain `396` rows, and Murphy diagnostics contain `1600` ML-tail rows.
- Feature-unavailability diagnostics are empty or not available for this run.
- Figure manifest references:
  - Figure: coverage_breach_rates_left_tail (Source: metrics/benchmark_metrics.parquet, metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: coverage_diagnostic_not_headline_claim; File: latex/figures/coverage_breach_rates_left_tail.png).
  - Figure: coverage_breach_rates_right_tail (Source: metrics/benchmark_metrics.parquet, metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: coverage_diagnostic_not_headline_claim; File: latex/figures/coverage_breach_rates_right_tail.png).
  - Figure: benchmark_murphy_left_tail (Source: metrics/benchmark_murphy.parquet; Claim scope: murphy_diagnostic_benchmark_floor_common_grid; File: latex/figures/benchmark_murphy_left_tail.png).
  - Figure: benchmark_murphy_right_tail (Source: metrics/benchmark_murphy.parquet; Claim scope: murphy_diagnostic_benchmark_floor_common_grid; File: latex/figures/benchmark_murphy_right_tail.png).
  - Figure: ml_tail_murphy_left_tail (Source: metrics/ml_tail_murphy.parquet; Claim scope: murphy_diagnostic_ml_tail_headline_ladder_common_grid; File: latex/figures/ml_tail_murphy_left_tail.png).
  - Figure: ml_tail_murphy_right_tail (Source: metrics/ml_tail_murphy.parquet; Claim scope: murphy_diagnostic_ml_tail_headline_ladder_common_grid; File: latex/figures/ml_tail_murphy_right_tail.png).
  - Figure: dst_attenuation_left_tail (Source: metrics/ml_tail_dst_attenuation.parquet; Claim scope: descriptive_dst_attenuation_not_structural_causal_identification; File: latex/figures/dst_attenuation_left_tail.png).
  - Figure: dst_attenuation_right_tail (Source: metrics/ml_tail_dst_attenuation.parquet; Claim scope: descriptive_dst_attenuation_not_structural_causal_identification; File: latex/figures/dst_attenuation_right_tail.png).
  - Figure: es_severity_left_tail (Source: metrics/benchmark_metrics.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: es_severity_diagnostic_not_model_selection_claim; File: latex/figures/es_severity_left_tail.png).
  - Figure: es_severity_right_tail (Source: metrics/benchmark_metrics.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: es_severity_diagnostic_not_model_selection_claim; File: latex/figures/es_severity_right_tail.png).
  - Figure: trigger_diagnostics_left_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: trigger_diagnostic_not_pnl_cost_or_alpha; File: latex/figures/trigger_diagnostics_left_tail.png).
  - Figure: trigger_diagnostics_right_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: trigger_diagnostic_not_pnl_cost_or_alpha; File: latex/figures/trigger_diagnostics_right_tail.png).

### Not yet claimed

- DST attenuation rows are descriptive forecast evidence; structural DST causal identification is not claimed.
- No hedge PnL, transaction-cost, or trading-alpha analysis is performed. The trigger table is a pre-open risk-monitoring diagnostic only.
- Left-tail and right-tail outputs are both economic tail-risk surfaces for futures positions; neither side should be promoted beyond the sample, coverage, and inference gates without author review.
- The current evidence does not create an automatic model-selection statement; any manuscript claim still requires author review of sample gates, coverage, loss metrics, and inference diagnostics.


## Run Metadata

| Field | Value |
| --- | --- |
| Run ID | `tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf` |
| Artifact root | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf` |
| Claim level | `research_candidate` |
| Requested window | `['2016-07-19', '2026-05-01']` |
| Combined clean start | `2018-06-20` |
| Gold panel dates | `2016-07-19 to 2026-04-30` |
| Forecast sample dates | `2018-06-20 to 2026-04-28 (1660 rows)` |
| Git commit | `d4b10baffaf7cd62adcff3784cd13ea61a48bed3` |
| Git dirty | `True` |
| FRED vintage safe | `False` |

- `combined_clean_start` is the modeling lower bound; dates before it remain audit history rather than forecast evidence.
- `git_dirty` is recorded so dirty runs can be rejected before manuscript tables are frozen.
- `fred_vintage_safe=False` is an explicit limitation: FRED data are current historical values with conservative release lag, not real-time vintage observations.

## Technical Infrastructure Note

- Runtime imports are explicit at the module boundary; no dynamic runtime namespace bridge is required to generate this snapshot. This infrastructure note is separate from empirical claim boundaries.

## Evidence Map

```mermaid
flowchart LR
  A["Vendor and calendar inputs"] --> B["Bronze / silver caches"]
  B --> C["Gold panel and timing map"]
  C --> D["Leakage and sample gates"]
  D --> E["Benchmark floor and advanced benchmarks"]
  D --> F["ML-tail information ladder"]
  E --> G["Metrics, DM/MCS, Murphy diagnostics"]
  F --> G
  F --> H["CPA conditional loss-difference diagnostics"]
  G --> I["Tables and figures"]
  H --> I
  I --> J["Generated results snapshot"]
```

- The left branch binds vendor and calendar inputs into a timestamp-audited gold panel.
- The middle branch compares benchmark floors, advanced econometric benchmarks, and ML-tail forecasts on registered loss units.
- The right branch separates headline ladders, restricted model-family comparisons, unconditional DM/MCS inference, CPA diagnostics, and supporting figures.

## Pipeline Structure

| Step | Layer | Purpose |
| --- | --- | --- |
| 1 | Vendor and calendar sources | Pull or read J-Quants, Massive, FRED, CBOE, and exchange-calendar inputs. |
| 2 | Bronze and silver cache | Preserve typed vendor/cache rows, then normalize timestamp-safe research features. |
| 3 | Gold modeling panel | Join targets, calendar map, feature coverage, and leakage-bound signatures. |
| 4 | Leakage and coverage gates | Enforce timestamp ordering and sample eligibility before evaluation. |
| 5 | Benchmark floor and ML-tail registry | Run target-history/econometric floors and LightGBM tail-model families. |
| 6 | Metrics, inference, diagnostics | Build loss matrices, DM/MCS/Murphy diagnostics, stress windows, and result matrix artifacts. |
| 7 | Results snapshot | Summarize run-specific evidence and claim boundaries for reader review. |

- Data-access and cache artifacts live under `data/bronze` and `data/silver`.
- Durable modeling evidence lives under `data/gold`; forecast/evaluation/reporting read from gold and reports.
- Run-specific forecasts, metrics, diagnostics, and LaTeX tables live under `reports/runs/<run_id>`.

## Gold Panel Construction

| Measure | Value |
| --- | --- |
| Gold modeling rows | 2394 |
| Gold columns | 425 |
| Target-audit rows | 2394 |
| Clean target rows | 2198 |
| Forecast-sample rows | 1660 |
| Rows before combined clean start | 412 |
| Target-not-clean rows | 196 |
| Mapping excluded rows | 126 |

| Target audit reason | Rows |
| --- | --- |
| None | 2198 |
| roll_sq_excluded | 195 |
| missing_reference_price | 1 |

- The cache lower bound is 2016-07-19, but XLC/core predictor coverage pushes the actual forecast sample to the combined clean start.
- Target exclusion is explicit: roll/SQ windows and the single missing reference price are carried as audit evidence, not silently dropped.
- The forecast-sample reason column makes the sample boundary reproducible row by row.

## Calendar And Timing Map

| Measure | Value |
| --- | --- |
| Normal trading mappings | 2267 |
| U.S./Japan desync mappings | 127 |
| NYSE early-close mappings | 32 |
| EDT rows | 1550 |
| EST rows | 844 |

- The map covers EST/EDT, early closes, U.S./Japan holiday desynchronization, and normal trading alignments.
- Desync rows are not treated as normal forecast rows.
- The timing map is part of the leakage-bound gold artifact, not ad hoc evaluation logic.

## Feature Coverage

| Source family | Block | Features | Mean missing | Max missing |
| --- | --- | --- | --- | --- |
| asia_proxy | asia_proxy | 6 | 0.000% | 0.000% |
| cboe_volatility | fred_core | 2 | 0.000% | 0.000% |
| fred_core | fred_core | 9 | 0.000% | 0.000% |
| fred_credit_enriched | fred_credit_enriched | 4 | 61.928% | 61.928% |
| fx_core | fx_core | 2 | 0.000% | 0.000% |
| japan_proxy | japan_proxy | 4 | 0.000% | 0.000% |
| massive_daily | us_core | 44 | 0.001% | 0.060% |
| massive_optional | massive_optional | 2 | 0.000% | 0.000% |
| spy_minute | us_late_session | 5 | 0.000% | 0.000% |
| unknown | unknown | 2 | 0.000% | 0.000% |

- U.S. core, proxy ETFs, SPY late-session features, CBOE VIX, FRED rates, and FRED H.10 FX are separated by source family and block.
- Credit-spread FRED features are enriched/optional and visibly late-starting, so they do not move the core clean start.
- Feature coverage should be read together with the leakage summary; high coverage alone is not enough without timestamp validity.

## Leakage Audit

| Field | Value |
| --- | --- |
| Status | `pass_with_warnings` |
| Rows audited | `186732` |
| Failures | `0` |
| Warnings | `181544` |
| Panel row count | `2394` |
| Panel signature seed | `42` |
| Panel signature | `c84e4bc7170e275a2f718cde8b4671e65baafd11f8fbde030c92a4f26c3ffcb5` |

- Zero failures means no audited row violated the hard timestamp invariant.
- Warnings are retained because they identify conservative-lag or missing-feature situations that may matter for interpretation.
- The panel signature is deterministic and binds the leakage check to the current gold panel/config.

## Benchmark Suite

Status: `completed`; forecast rows: `21114`; metric rows: `12`; failures: `0`.

| Benchmark layer | Status | Forecast rows | Diagnostic rows | Failures | How to read it |
| --- | --- | --- | --- | --- | --- |
| floor | `completed` | `7920` | `12` | `0` | Implemented benchmark evidence for target-history and econometric floor models. |
| advanced | `completed_nonblocking` | `13194` | `786` | `0` | Implemented nonblocking advanced benchmark forecasts; review with common-sample gates. |

| Model | Information set | Tail side | Rows | VaR breach rate | Exceptions | Mean quantile loss | Mean FZ loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ewma_vol_scaled | target_history_only | left_tail | 660 | 5.303% | 35 | 0.00139284 | -3.65391 |
| ewma_vol_scaled | target_history_only | right_tail | 660 | 4.545% | 30 | 0.00131597 | -3.69643 |
| garch_t | target_history_only | left_tail | 660 | 6.364% | 42 | 0.00135148 | -3.70351 |
| garch_t | target_history_only | right_tail | 660 | 3.939% | 26 | 0.00122288 | -3.78658 |
| gjr_garch_evt | target_history_only | left_tail | 660 | 5.606% | 37 | 0.00133621 | -3.73138 |
| gjr_garch_evt | target_history_only | right_tail | 660 | 5.303% | 35 | 0.00118016 | -3.80061 |
| gjr_garch_t | target_history_only | left_tail | 660 | 6.515% | 43 | 0.00134109 | -3.70805 |
| gjr_garch_t | target_history_only | right_tail | 660 | 3.788% | 25 | 0.00117451 | -3.81439 |
| historical_quantile | target_history_only | left_tail | 660 | 6.061% | 40 | 0.00147857 | -3.51331 |
| historical_quantile | target_history_only | right_tail | 660 | 6.364% | 42 | 0.00146455 | -3.43788 |
| rolling_quantile | target_history_only | left_tail | 660 | 6.061% | 40 | 0.00147852 | -3.50579 |
| rolling_quantile | target_history_only | right_tail | 660 | 6.667% | 44 | 0.00147175 | -3.43306 |

- Benchmark floor rows set the target-history/econometric floor that ML models should be interpreted against.
- Advanced benchmark families are nonblocking; rows with valid forecasts are empirical evidence subject to the same sample and inference gates, while unavailable rows remain diagnostics.
- The table is not a leaderboard by itself; coverage, exception counts, quantile loss, and FZ loss must be read together.
- Common-sample rows are reported directly so readers can see the effective evidence size.

## ML-Tail Headline Ladder

Status: `completed_lightgbm_ml_tail_models`; implemented models: `lightgbm_direct_quantile`, `lightgbm_location_scale`, `lightgbm_standardized_loss_pot_gpd`; forecast rows: `7744`; failures: `0`.

| Model | Information set | Tail side | Rows | VaR breach rate | Exceptions | Mean quantile loss | Mean FZ loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm_direct_quantile | japan_only | left_tail | 660 | 9.545% | 63 | 0.00147071 | -3.3637 |
| lightgbm_direct_quantile | japan_only_plus_us_close_core | left_tail | 660 | 11.515% | 76 | 0.00120487 | -3.43912 |
| lightgbm_direct_quantile | japan_only_plus_us_close_core_plus_japan_proxy | left_tail | 660 | 12.576% | 83 | 0.00115289 | -3.62124 |
| lightgbm_direct_quantile | japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy | left_tail | 660 | 12.424% | 82 | 0.00115654 | -3.58631 |
| lightgbm_direct_quantile | japan_only | right_tail | 660 | 9.091% | 60 | 0.00134569 | -3.50952 |
| lightgbm_direct_quantile | japan_only_plus_us_close_core | right_tail | 660 | 11.061% | 73 | 0.00134147 | -3.16245 |
| lightgbm_direct_quantile | japan_only_plus_us_close_core_plus_japan_proxy | right_tail | 660 | 11.667% | 77 | 0.00128302 | -3.36953 |
| lightgbm_direct_quantile | japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy | right_tail | 660 | 11.667% | 77 | 0.00127586 | -3.39674 |

- This headline table remains strict and currently reports direct LightGBM quantile across the information ladder.
- Location-scale and POT-GPD are implemented, but their shorter common coverage keeps them out of the headline ladder.
- Differences across information blocks are candidate forecast evidence only after the common-sample, coverage, and inference diagnostics are reviewed.
- Coverage review: `8/8` headline rows differ from the expected breach rate by more than 2.5 percentage points, so quantile/FZ loss differences alone must not be read as forecast improvement.

### ML-tail artifact relationship

| Artifact | Rows | Role | Claim boundary |
| --- | --- | --- | --- |
| `ml_tail_metrics.parquet` | 8 | Headline ML-tail information-set ladder | Eligible for headline discussion after author review. |
| `ml_tail_metrics_per_model.parquet` | 24 | Per-model diagnostics on each model's own valid OOS rows | Not a cross-model comparison and not a replacement headline table. |
| `ml_tail_result_matrix.parquet` | 144 | Restricted common-sample VaR-only and VaR-ES comparisons | Restricted evidence; direct quantile rows here are comparison anchors. |

- `ml_tail_metrics.parquet` is the headline ladder artifact. In this run it contains direct-quantile rows that survived the strict common-sample gate.
- `ml_tail_metrics_per_model.parquet` reports each implemented ML-tail model on its own valid OOS rows; it is useful for debugging coverage but is not a cross-model comparison table.
- `ml_tail_result_matrix.parquet` creates restricted common samples for VaR-only and VaR-ES comparisons across model families and within-model information-set increments.

## Result Matrix Layer

| Family | Axis | Loss | Rows | Common N | Date range | Joint exceptions |
| --- | --- | --- | --- | --- | --- | --- |
| information_set_ladder | information_set_increment | var_coverage | 24 | 154 to 660 | 2023-03-24 to 2026-04-28 | 16 to 112 |
| information_set_ladder | information_set_increment | var_es_fz_loss | 24 | 154 to 660 | 2023-03-24 to 2026-04-28 | 16 to 112 |
| information_set_ladder | information_set_increment | var_quantile_loss | 24 | 154 to 660 | 2023-03-24 to 2026-04-28 | 16 to 112 |
| tail_model_family | model_family | var_coverage | 24 | 154 to 154 | 2025-08-01 to 2026-04-28 | 17 to 23 |
| tail_model_family | model_family | var_es_fz_loss | 24 | 154 to 154 | 2025-08-01 to 2026-04-28 | 17 to 23 |
| tail_model_family | model_family | var_quantile_loss | 24 | 154 to 154 | 2025-08-01 to 2026-04-28 | 17 to 23 |

- The result matrix is the right place to compare direct quantile, location-scale, and POT-GPD on their restricted common dates.
- It separates VaR-only losses from VaR-ES joint scoring, so VaR-only claims are not confused with ES claims.
- Restricted direct-quantile performance is only a comparison anchor for the tail-model family; it does not replace the headline direct-quantile evidence.
- DM and MCS records are emitted only where registered row-count and exception-count gates pass; otherwise the result matrix remains descriptive.

## Paper-Facing Table And Figure Gallery

### Table Manifest

| Table | Source artifacts | Claim scope | Tail side | File |
| --- | --- | --- | --- | --- |
| benchmark_metrics | `metrics/benchmark_metrics.parquet` | `benchmark_common_sample_metric_table` | `None` | `latex/tables/benchmark_metrics_table.tex` |
| benchmark_left_tail_risk | `metrics/benchmark_metrics.parquet` | `left_tail_benchmark_risk_table` | `left_tail` | `latex/tables/benchmark_left_tail_risk_table.tex` |
| benchmark_right_tail_risk | `metrics/benchmark_metrics.parquet` | `right_tail_benchmark_risk_table` | `right_tail` | `latex/tables/benchmark_right_tail_risk_table.tex` |
| ml_tail_metrics | `metrics/ml_tail_metrics.parquet` | `ml_tail_headline_ladder_table` | `None` | `latex/tables/ml_tail_metrics_table.tex` |
| ml_tail_left_tail_risk | `metrics/ml_tail_metrics.parquet` | `left_tail_ml_tail_headline_risk_table` | `left_tail` | `latex/tables/ml_tail_left_tail_risk_table.tex` |
| ml_tail_right_tail_risk | `metrics/ml_tail_metrics.parquet` | `right_tail_ml_tail_headline_risk_table` | `right_tail` | `latex/tables/ml_tail_right_tail_risk_table.tex` |
| tailrisk_es_severity | `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet` | `es_severity_diagnostic_table` | `None` | `latex/tables/tailrisk_es_severity_table.tex` |
| tailrisk_trigger_diagnostics | `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet` | `trigger_diagnostic_table` | `None` | `latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` |
| tailrisk_claim_scope | `manifest.json`, `config/research_config.json` | `claim_boundary_reference_table` | `None` | `latex/tables/tailrisk_claim_scope_table.tex` |
| ml_tail_result_matrix | `metrics/ml_tail_result_matrix.parquet` | `restricted_model_comparison_table` | `None` | `latex/tables/ml_tail_result_matrix_table.tex` |
| ml_tail_result_matrix_summary | `metrics/ml_tail_result_matrix.parquet`, `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet` | `restricted_result_matrix_summary_table` | `None` | `latex/tables/ml_tail_result_matrix_summary_table.tex` |
| ml_tail_dst_attenuation | `metrics/ml_tail_dst_attenuation.parquet` | `descriptive_dst_attenuation_table` | `None` | `latex/tables/ml_tail_dst_attenuation_table.tex` |

- The table manifest records the generated LaTeX table files, their source artifacts, and their claim scopes.
- Tables are paper-facing exports; the Markdown tables above are snapshot summaries for browser review.

### Figure 1. Coverage Breach-Rate Diagnostics

- Key readings: bars report realized VaR exception rates against the nominal line.
- Read this first: exception-rate deviations set the boundary for any loss-based interpretation.

![coverage_breach_rates_left_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/coverage_breach_rates_left_tail.png)

_Figure: `coverage_breach_rates_left_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `coverage_diagnostic_not_headline_claim`. Tail side: `left_tail`. Run file: `latex/figures/coverage_breach_rates_left_tail.png`._

![coverage_breach_rates_right_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/coverage_breach_rates_right_tail.png)

_Figure: `coverage_breach_rates_right_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `coverage_diagnostic_not_headline_claim`. Tail side: `right_tail`. Run file: `latex/figures/coverage_breach_rates_right_tail.png`._

### Figure 2. Benchmark Murphy Diagnostics

- Key readings: curves report benchmark elementary-score diagnostics on a common grid.
- The plot is a scoring-family diagnostic, not a pairwise ranking statement.

![benchmark_murphy_left_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/benchmark_murphy_left_tail.png)

_Figure: `benchmark_murphy_left_tail`. Source: `metrics/benchmark_murphy.parquet`. Claim scope: `murphy_diagnostic_benchmark_floor_common_grid`. Tail side: `left_tail`. Run file: `latex/figures/benchmark_murphy_left_tail.png`._

![benchmark_murphy_right_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/benchmark_murphy_right_tail.png)

_Figure: `benchmark_murphy_right_tail`. Source: `metrics/benchmark_murphy.parquet`. Claim scope: `murphy_diagnostic_benchmark_floor_common_grid`. Tail side: `right_tail`. Run file: `latex/figures/benchmark_murphy_right_tail.png`._

### Figure 3. ML-Tail Murphy Diagnostics

- Key readings: curves report the ML-tail headline information ladder on a common grid.
- Interpret curve separation together with the headline coverage warning and unconditional inference gates.

![ml_tail_murphy_left_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/ml_tail_murphy_left_tail.png)

_Figure: `ml_tail_murphy_left_tail`. Source: `metrics/ml_tail_murphy.parquet`. Claim scope: `murphy_diagnostic_ml_tail_headline_ladder_common_grid`. Tail side: `left_tail`. Run file: `latex/figures/ml_tail_murphy_left_tail.png`._

![ml_tail_murphy_right_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/ml_tail_murphy_right_tail.png)

_Figure: `ml_tail_murphy_right_tail`. Source: `metrics/ml_tail_murphy.parquet`. Claim scope: `murphy_diagnostic_ml_tail_headline_ladder_common_grid`. Tail side: `right_tail`. Run file: `latex/figures/ml_tail_murphy_right_tail.png`._

### Figure 4. DST Attenuation Diagnostics

- Key readings: bars summarize timing-regime forecast diagnostics.
- Treat this as descriptive timing evidence; left/right patterns should not be assigned a shared structural mechanism.

![dst_attenuation_left_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/dst_attenuation_left_tail.png)

_Figure: `dst_attenuation_left_tail`. Source: `metrics/ml_tail_dst_attenuation.parquet`. Claim scope: `descriptive_dst_attenuation_not_structural_causal_identification`. Tail side: `left_tail`. Run file: `latex/figures/dst_attenuation_left_tail.png`._

![dst_attenuation_right_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/dst_attenuation_right_tail.png)

_Figure: `dst_attenuation_right_tail`. Source: `metrics/ml_tail_dst_attenuation.parquet`. Claim scope: `descriptive_dst_attenuation_not_structural_causal_identification`. Tail side: `right_tail`. Run file: `latex/figures/dst_attenuation_right_tail.png`._

### Figure 5. ES Severity Diagnostics

- Key readings: bars report conditional-on-exception severity diagnostics.
- Severity is reported for risk interpretation but is not a standalone model-selection claim.

![es_severity_left_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/es_severity_left_tail.png)

_Figure: `es_severity_left_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `es_severity_diagnostic_not_model_selection_claim`. Tail side: `left_tail`. Run file: `latex/figures/es_severity_left_tail.png`._

![es_severity_right_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/es_severity_right_tail.png)

_Figure: `es_severity_right_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `es_severity_diagnostic_not_model_selection_claim`. Tail side: `right_tail`. Run file: `latex/figures/es_severity_right_tail.png`._

### Figure 6. Trigger Diagnostics

- Key readings: bars report pre-open risk-trigger diagnostics by model family.
- The trigger output is a monitoring diagnostic, not an execution-performance result.

![trigger_diagnostics_left_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/trigger_diagnostics_left_tail.png)

_Figure: `trigger_diagnostics_left_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `trigger_diagnostic_not_pnl_cost_or_alpha`. Tail side: `left_tail`. Run file: `latex/figures/trigger_diagnostics_left_tail.png`._

![trigger_diagnostics_right_tail](figures/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/trigger_diagnostics_right_tail.png)

_Figure: `trigger_diagnostics_right_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `trigger_diagnostic_not_pnl_cost_or_alpha`. Tail side: `right_tail`. Run file: `latex/figures/trigger_diagnostics_right_tail.png`._

## Stress And Diagnostic Windows

| Suite | Rows | Window labels |
| --- | --- | --- |
| benchmark | 132 | `loss_top_decile` |
| ml_tail | 264 | `loss_top_decile`, `vix_top_decile` |

- Stress windows identify high-loss or high-volatility subsamples for two-sided risk diagnostics.
- These rows use reproducible full-sample classifiers in this first pass, so they should be described as diagnostics rather than a live stress classifier.
- They are useful for finding whether model behavior changes in difficult regimes before writing manuscript discussion.

## Artifact Index

| Artifact | Path | Exists |
| --- | --- | --- |
| manifest | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/manifest.json` | yes |
| data_vintage | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/data_vintage.json` | yes |
| modeling_panel | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/modeling_panel.parquet` | yes |
| target_audit | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/target_audit.parquet` | yes |
| calendar_map | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/calendar_map.parquet` | yes |
| feature_coverage | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/feature_coverage.parquet` | yes |
| leakage_summary | `data/gold/leakage_summary/schema_version=1/run_id=tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/summary.json` | yes |
| benchmark_status | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/benchmark_status.json` | yes |
| benchmark_metrics | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/benchmark_metrics.parquet` | yes |
| benchmark_forecasts | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/forecasts/benchmark_forecasts.parquet` | yes |
| benchmark_dm_inference | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/benchmark_dm_inference.parquet` | yes |
| benchmark_mcs | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/benchmark_mcs.parquet` | yes |
| ml_tail_status | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_status.json` | yes |
| ml_tail_metrics | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_metrics.parquet` | yes |
| ml_tail_metrics_per_model | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_metrics_per_model.parquet` | yes |
| ml_tail_forecasts | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/forecasts/ml_tail_forecasts.parquet` | yes |
| ml_tail_result_matrix | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_result_matrix.parquet` | yes |
| ml_tail_result_matrix_dm | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_result_matrix_dm.parquet` | yes |
| ml_tail_result_matrix_mcs | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_result_matrix_mcs.parquet` | yes |
| ml_tail_dm_inference | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_dm_inference.parquet` | yes |
| ml_tail_mcs | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_mcs.parquet` | yes |
| ml_tail_cpa_inference | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_cpa_inference.parquet` | yes |
| cross_model_cpa_inference | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/cross_model_cpa_inference.parquet` | yes |
| ml_tail_model_eviction | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_model_eviction.parquet` | yes |
| ml_tail_dst_attenuation | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_dst_attenuation.parquet` | yes |
| ml_tail_murphy | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_murphy.parquet` | yes |
| ml_tail_feature_unavailability | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_feature_unavailability.parquet` | yes |
| benchmark_stress_windows | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/benchmark_stress_windows.parquet` | yes |
| ml_tail_stress_windows | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/metrics/ml_tail_stress_windows.parquet` | yes |
| figure_manifest | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/figure_manifest.json` | yes |
| table_manifest | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/table_manifest.json` | yes |
| latex_dir | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/tables` | yes |
| claim_scope_table | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/tables/tailrisk_claim_scope_table.tex` | yes |
| es_severity_table | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/tables/tailrisk_es_severity_table.tex` | yes |
| hedge_trigger_table | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` | yes |
| dst_attenuation_table | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/tables/ml_tail_dst_attenuation_table.tex` | yes |
| result_matrix_summary_table | `reports/runs/tailrisk_20160719_20260501_20260501T032942Z_commit_d4b10baf/latex/tables/ml_tail_result_matrix_summary_table.tex` | yes |

- All paths above are local ignored artifacts; they are reproducible outputs, not tracked source files.
- Forecast/reporting rebuilds should read these artifacts and must not call vendor APIs.
- If this page is stale, rerun `just snapshot` after a completed `just full` or pass an explicit run id to the CLI snapshot command.
