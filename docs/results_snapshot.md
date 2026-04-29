# Results Snapshot

> **Research-candidate full-run artifact.** This page is generated from `tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995`.
> It summarizes the durable gold modeling sample and run outputs, not the older
> bounded access-check snapshot. It is still a research-candidate artifact:
> final manuscript claims require a clean committed run and author review of the
> tables and notes.

## Discussion Q&A

### What is this project testing?

It tests whether timestamp-safe information available after the U.S. cash close helps forecast the downside tail of the next Osaka Nikkei 225 Futures day-session open.

- The object is tail risk, not average return prediction or a trading signal.
- The comparison is organized as an information ladder: Japan-only history first, then U.S. close core, then Japan proxy ETFs, then Asia proxy ETFs.
- The current page reports what the pipeline produced; it does not automatically claim that any model is best.

### What exactly is being forecast?

The primary target is the loss version of the settle-to-open Nikkei futures gap for the OSE day-session open.

- A positive realized loss means the opening gap moved against the lower-tail risk direction being evaluated.
- Roll/SQ windows and invalid reference prices are excluded from clean target evidence.
- The residual U.S.-close mark target is disabled in this run because there is no licensed timestamped intraday Nikkei mark.

### Why is timing the central issue?

The forecast origin is the U.S. close plus vendor lag, and it must occur before the OSE target open.

- Every joined predictor is audited against `feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`.
- FRED features are treated with timestamp-safe release lags; FRED historical values are not ALFRED vintage-safe.
- Leakage audit failures are zero in this run, but warnings remain visible below rather than hidden.

### What has been implemented?

The benchmark floor, advanced benchmark suite, and ML-tail suite are implemented and have completed artifacts in this run.

- Benchmark floor models include target-history baselines and GARCH/EVT-style econometric floors.
- Advanced benchmark families such as CAViaR, CARE/expectile, Taylor ALD, direct FZ-loss, and GAS now produce nonblocking empirical forecast rows; their interpretation still follows the benchmark/restricted-sample gates.
- ML-tail models include direct LightGBM quantile, location-scale LightGBM, and standardized-loss POT-GPD.
- The headline ML-tail table remains strict: it currently keeps direct quantile rows because the newer tail-model variants have shorter common coverage.

### How should broad readers interpret the metrics?

Coverage diagnostics ask whether VaR exceptions are too frequent or too rare; quantile loss scores VaR accuracy; FZ loss scores VaR-ES pairs.

- Lower quantile loss is better only within a common sample and claim boundary.
- FZ loss is only meaningful for valid VaR-ES pairs and needs enough exceptions to avoid short-sample overinterpretation.
- Restricted result-matrix rows are useful diagnostics, not replacements for the headline information-set ladder.

### What is the current bottom line?

The pipeline is now producing full-run research-candidate evidence from the durable gold layer.

- The gold sample starts at the dynamic combined clean start, not the 2016 cache lower bound.
- Benchmark floor, advanced benchmark, and ML-tail suites completed with zero recorded forecast failures; advanced rows are implemented evidence but remain nonblocking until author-reviewed against the same sample/inference gates.
- Before manuscript claims, review the headline/restricted/diagnostic boundaries, inference gates, and vintage limitations rather than selecting a winner from one metric.

### Which results can support headline claims?

| Evidence layer | Can support headline claim? | How to read it |
| --- | --- | --- |
| Benchmark common-sample table | Yes, after review | External target-history/econometric floor on a shared sample. |
| ML-tail headline ladder | Yes, after review | Strict information-set ladder; currently direct quantile survived the gate. |
| ML-tail per-model rows | No | Model-specific OOS diagnostics; samples need not match across model families. |
| Restricted result matrix | No headline claim | Matched-date comparison for model families and within-model increments. |
| DST, stress, Murphy, hedge-trigger diagnostics | Diagnostic only | Useful for interpretation and risk monitoring, not automatic model superiority. |

- Headline claims require a clean committed run, a shared common sample, zero leakage failures, and author-reviewed tables.
- Restricted rows can explain model-family behavior on matched dates, but they cannot replace the headline information ladder.
- Diagnostic rows can motivate discussion and future checks; they should not be worded as superiority or risk-management usefulness claims without their own evidence gates.

## Results And Discussion

<!-- generated: results_discussion -->

### Data and timing audit

- The gold timing map covers `2016-07-19 to 2026-04-28` and the combined clean start is `2018-06-20`.
- No forecast-sample rows before `2018-06-20` enter the modeling evidence.
- The leakage check reports status `pass_with_warnings` with zero leakage failures and `181468` warnings.
- FRED vintage safety is recorded as `False`; FRED values use conservative release timing but remain current historical observations rather than ALFRED real-time vintages.

### Benchmark floor and advanced benchmarks

- `benchmark_metrics.parquet` reports `12` common-sample rows across `6` benchmark model families and `2` tail side(s), while benchmark forecasts contain `21114` model-date rows.
- Benchmark-floor models are external target-history and econometric baselines; this section does not rank them.
- Advanced benchmark rows are implemented for `10` model families and contribute `13194` nonblocking forecast rows; these rows are claim-gated diagnostics unless a manuscript table explicitly promotes them through the same sample and inference review.

### ML-tail headline ladder

`ml_tail_metrics.parquet` defines the headline ML-tail information-set ladder for this run.
- The headline artifact contains `4` information sets, `1` tail level(s), and `2` tail side(s); the retained headline model rows are `lightgbm_direct_quantile`.
- The implemented ML-tail registry is `lightgbm_direct_quantile`, `lightgbm_location_scale`, `lightgbm_standardized_loss_pot_gpd`, but the headline ladder should be read only from `ml_tail_metrics.parquet`.
- The ladder is used to assess candidate incremental U.S.-close information under strict common-sample rules; it does not by itself establish forecast improvement.

### Restricted model-family comparison

- `ml_tail_result_matrix.parquet` contains restricted common-sample comparisons for `3` LightGBM tail-model families.
- The restricted common-N range is `154 to 660` and the joint-exception range is `16 to 112`.
- Recorded claim scopes are `restricted_model_comparison_not_headline`; these rows are restricted evidence and cannot replace the headline information-set ladder.
- The result matrix is a matched-date diagnostic layer. It should not be worded as one family being better than another.

### Coverage and inference gates

- Coverage review flags `8/8` headline rows with breach rates more than 2.5 percentage points from nominal coverage; Kupiec p-values fall below 0.05 in `8/8` rows and Christoffersen p-values fall below 0.05 in `0/8` rows where reported.
- Model-eviction artifacts record `8` retained rows and `16` non-retained rows under the headline sample policy.
- Block-bootstrap DM and HLN Tmax MCS artifacts are unconditional forecast-comparison diagnostics; any p-value should be read on average across the unconditional evaluation sample, not as condition-specific evidence.
- Loss differentials alone do not constitute an improvement claim; coverage, exception counts, sample gates, and inference status must be reviewed together.
- Tail-event and inference gates report `0` restricted rows with insufficient tail-event power and `0/36` unavailable DM/MCS inference rows.

### Supporting diagnostics

- Supporting LaTeX diagnostics are exported for `4/4` registered table families.
- `ml_tail_dst_attenuation.parquet` contains `12` DST attenuation rows; these are descriptive timing-regime forecast diagnostics. They do not establish a structural timing mechanism.
- ES severity diagnostics contain `20` finite rows with mean exceedance severity ranging from `0.00567755` to `0.0127453`; this is conditional-on-exception evidence.
- The diagnostic 75th-percentile VaR trigger rule marks `7260` model-date rows; `585` of those rows coincide with VaR exceptions out of `1977` total exceptions, and mean triggered exception severity is `0.013498`. This is a pre-open risk-monitoring diagnostic, not hedge PnL, transaction-cost, or trading-alpha evidence.
- Stress-window diagnostics contain `396` rows, and Murphy diagnostics contain `1600` ML-tail rows.
- Feature-unavailability diagnostics are empty or not available for this run.

### Not yet claimed

- Instrumented conditional predictive ability appears as a side-specific ML-tail information-ladder diagnostic across `2` tail side(s), with `6` registered row(s), of which `6` pass their HAC-Wald gates; it does not generate VaR/ES forecasts and does not replace DM/MCS.
- DST attenuation rows are descriptive forecast evidence; structural DST causal identification is not claimed.
- No hedge PnL, transaction-cost, or trading-alpha analysis is performed. The trigger table is a pre-open risk-monitoring diagnostic only.
- Left-tail and right-tail outputs are both economic tail-risk surfaces for futures positions; neither side should be promoted beyond the sample, coverage, and inference gates without author review.
- The current evidence does not create an automatic model-win statement; any manuscript claim still requires author review of sample gates, coverage, loss metrics, and inference diagnostics.


## Metadata

| Field | Value |
| --- | --- |
| Run ID | `tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995` |
| Artifact root | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995` |
| Claim level | `research_candidate` |
| Requested window | `['2016-07-19', '2026-04-29']` |
| Combined clean start | `2018-06-20` |
| Gold panel dates | `2016-07-19 to 2026-04-28` |
| Forecast sample dates | `2018-06-20 to 2026-04-28 (1660 rows)` |
| Git commit | `e12bc995da605cb292a5b78d9d6c095e604484d5` |
| Git dirty | `False` |
| FRED vintage safe | `False` |

- `combined_clean_start` is the modeling lower bound; dates before it remain audit history rather than forecast evidence.
- `git_dirty` is recorded so dirty runs can be rejected before manuscript tables are frozen.
- `fred_vintage_safe=False` is an explicit limitation: FRED data are current historical values with conservative release lag, not real-time vintage observations.

## Technical Infrastructure Note

- The runtime compatibility bridge based on `globals().update(runtime)` remains a future architecture cleanup. Its removal is separate from empirical reruns and is not part of the claim boundary for this results snapshot.

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
| Gold modeling rows | 2393 |
| Gold columns | 425 |
| Target-audit rows | 2393 |
| Clean target rows | 2197 |
| Forecast-sample rows | 1660 |
| Rows before combined clean start | 412 |
| Target-not-clean rows | 196 |
| Mapping excluded rows | 125 |

| Target audit reason | Rows |
| --- | --- |
| None | 2197 |
| roll_sq_excluded | 195 |
| missing_reference_price | 1 |

- The cache lower bound is 2016-07-19, but XLC/core predictor coverage pushes the actual forecast sample to the combined clean start.
- Target exclusion is explicit: roll/SQ windows and the single missing reference price are carried as audit evidence, not silently dropped.
- The forecast-sample reason column makes the sample boundary reproducible row by row.

## Calendar And Timing Map

| Measure | Value |
| --- | --- |
| Normal trading mappings | 2267 |
| U.S./Japan desync mappings | 126 |
| NYSE early-close mappings | 32 |
| EDT rows | 1549 |
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
| fred_credit_enriched | fred_credit_enriched | 4 | 61.898% | 61.928% |
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
| Rows audited | `186654` |
| Failures | `0` |
| Warnings | `181468` |
| Panel row count | `2393` |
| Panel signature seed | `42` |
| Panel signature | `f0981ad53852565aec7396a3be258835587df1eadb2c0b0445683029aa32a209` |

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
| manifest | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/manifest.json` | yes |
| data_vintage | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/data_vintage.json` | yes |
| modeling_panel | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/modeling_panel.parquet` | yes |
| target_audit | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/target_audit.parquet` | yes |
| calendar_map | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/calendar_map.parquet` | yes |
| feature_coverage | `data/gold/tailrisk_panel/schema_version=1/run_id=tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/feature_coverage.parquet` | yes |
| leakage_summary | `data/gold/leakage_summary/schema_version=1/run_id=tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/summary.json` | yes |
| benchmark_status | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/benchmark_status.json` | yes |
| benchmark_metrics | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/benchmark_metrics.parquet` | yes |
| benchmark_forecasts | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/forecasts/benchmark_forecasts.parquet` | yes |
| benchmark_dm_inference | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/benchmark_dm_inference.parquet` | yes |
| benchmark_mcs | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/benchmark_mcs.parquet` | yes |
| ml_tail_status | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_status.json` | yes |
| ml_tail_metrics | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_metrics.parquet` | yes |
| ml_tail_metrics_per_model | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_metrics_per_model.parquet` | yes |
| ml_tail_forecasts | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/forecasts/ml_tail_forecasts.parquet` | yes |
| ml_tail_result_matrix | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_result_matrix.parquet` | yes |
| ml_tail_result_matrix_dm | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_result_matrix_dm.parquet` | yes |
| ml_tail_result_matrix_mcs | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_result_matrix_mcs.parquet` | yes |
| ml_tail_dm_inference | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_dm_inference.parquet` | yes |
| ml_tail_mcs | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_mcs.parquet` | yes |
| ml_tail_cpa_inference | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_cpa_inference.parquet` | yes |
| ml_tail_model_eviction | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_model_eviction.parquet` | yes |
| ml_tail_dst_attenuation | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_dst_attenuation.parquet` | yes |
| ml_tail_murphy | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_murphy.parquet` | yes |
| ml_tail_feature_unavailability | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_feature_unavailability.parquet` | yes |
| benchmark_stress_windows | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/benchmark_stress_windows.parquet` | yes |
| ml_tail_stress_windows | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/metrics/ml_tail_stress_windows.parquet` | yes |
| latex_dir | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/latex/tables` | yes |
| claim_scope_table | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/latex/tables/tailrisk_claim_scope_table.tex` | yes |
| es_severity_table | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/latex/tables/tailrisk_es_severity_table.tex` | yes |
| hedge_trigger_table | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` | yes |
| dst_attenuation_table | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/latex/tables/ml_tail_dst_attenuation_table.tex` | yes |
| result_matrix_summary_table | `reports/runs/tailrisk_20160719_20260429_20260429T075652Z_commit_e12bc995/latex/tables/ml_tail_result_matrix_summary_table.tex` | yes |

- All paths above are local ignored artifacts; they are reproducible outputs, not tracked source files.
- Forecast/reporting rebuilds should read these artifacts and must not call vendor APIs.
- If this page is stale, rerun `just snapshot` after a completed `just full` or pass an explicit run id to the CLI snapshot command.
