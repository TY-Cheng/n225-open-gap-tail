---
hide:
  - navigation
---

# Results And Discussion Snapshot

> **Research-candidate full-run artifact.** This page is generated from `tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa`.
> It summarizes the durable gold modeling sample and run outputs, not the older
> bounded access-check snapshot. It is still a research-candidate artifact:
> final manuscript claims require a clean committed run and author review of the
> tables and notes.

## Results And Discussion Overview

This page is the merged results-and-artifact map for the locked run. It keeps
enough data and method context to make each result auditable, then organizes the
tables and figures in the order they support the Results and Discussion section.
Full data-source detail lives in [Data](data.md), and the paper-level research
design lives in [Paper Plan](paper_plan.md).

### Evidence Map

```mermaid
flowchart LR
  A["Vendor and calendar inputs"] --> B["Bronze / silver caches"]
  B --> C["Gold panel and timing map"]
  C --> D["Leakage and sample gates"]
  D --> E["Baseline benchmarks and advanced econometric benchmarks"]
  D --> F["Primary ML nested information sets"]
  E --> G["Metrics, DM/MCS, Murphy diagnostics"]
  F --> G
  F --> H["CPA conditional loss-difference diagnostics"]
  G --> I["Tables and figures"]
  H --> I
  I --> J["Generated results snapshot"]
```

- The left branch binds vendor and calendar inputs into a timestamp-audited gold panel.
- The middle branch compares baseline benchmarks, advanced econometric benchmarks, and ML-tail forecasts on registered loss units.
- The right branch separates primary ML nested information sets, diagnostic model-family comparisons, unconditional DM/MCS inference, CPA diagnostics, and supporting figures.

## Results Context: Data, Target, And Timing

### Run Metadata

| Field | Value |
| --- | --- |
| Run ID | `tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa` |
| Artifact root | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa` |
| Claim level | `research_candidate` |
| Requested window | `['2016-07-19', '2026-05-08']` |
| Combined clean start | `2018-06-20` |
| Gold panel dates | `2016-07-19 to 2026-05-08` |
| Forecast sample dates | `2018-06-20 to 2026-05-08 (1712 rows)` |
| Git commit | `f420c4fadc2c2c5412871310a9c63953bd89e697` |
| Git dirty | `True` |
| FRED vintage safe | `False` |

- `combined_clean_start` is the modeling lower bound; dates before it remain audit history rather than forecast evidence.
- `git_dirty` is recorded so dirty runs can be rejected before manuscript tables are frozen.
- `fred_vintage_safe=False` is an explicit limitation: FRED data are current historical values with conservative release lag, not real-time vintage observations.

### Target Distribution And Tail Diagnostics

- These diagnostics are computed from the raw clean settlement-to-open target `gap_t`; left loss is `-gap_t`, and right loss is `gap_t`.
- The purpose is to show why the dependent variable is a tail-risk object before comparing VaR/ES forecasts.
- Positive tail-shape estimates, heavy empirical tails, and upward mean-excess patterns are empirical support for using heavy-tail approximations such as POT-GPD; they are not a finite-sample proof of Frechet max-domain attraction.
- Raw target diagnostics motivate VaR/ES and EVT modeling. They do not validate LightGBM+EVT forecasts; forecast validity must be read from standardized residual-loss EVT diagnostics and out-of-sample VaR/ES backtests.

#### Target Summary

| Measure | Value |
| --- | --- |
| Clean forecast observations | `1712` |
| Date range | `2018-06-20 to 2026-05-08` |
| Mean gap | 0.000562 log (+0.06%) |
| Standard deviation | 0.011038 log (+1.11%) |
| Skewness | -0.0660673 |
| Excess kurtosis | 11.2256 |
| 1% quantile | -0.031102 log (-3.06%) |
| 5% quantile | -0.015645 log (-1.55%) |
| Median | 0.001012 log (+0.10%) |
| 95% quantile | 0.015305 log (+1.54%) |
| 99% quantile | 0.027493 log (+2.79%) |
| Max drawdown gap | -0.087513 log (-8.38%) on `2020-03-13` |
| Max upside gap | 0.096937 log (+10.18%) on `2025-04-10` |
| Jarque-Bera p-value | 0 |
| Jarque-Bera statistic | 9016.83 |

#### Raw-Tail EVT Diagnostics

| Tail | Threshold probability | Threshold | Exceedances | Mean excess | GPD xi | GPD scale | Hill xi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| left_tail_loss | 0.900 | 0.0160618 | 78 | 0.0103847 | 0.152593 | 0.00878757 | 0.432871 |
| left_tail_loss | 0.925 | 0.0195607 | 58 | 0.00995799 | 0.293971 | 0.00712569 | 0.346247 |
| left_tail_loss | 0.950 | 0.0223549 | 39 | 0.0113879 | 0.237098 | 0.00874323 | 0.354783 |
| left_tail_loss | 0.975 | 0.029331 | 20 | 0.0127713 | 0.261132 | 0.0095416 | 0.31884 |
| left_tail_loss | 0.990 | 0.0373472 | 8 | 0.0175314 | 0.211214 | 0.0140966 | 0.342351 |
| right_tail_loss | 0.900 | 0.0149284 | 91 | 0.00910348 | 0.400284 | 0.00566715 | 0.385744 |
| right_tail_loss | 0.925 | 0.0169257 | 69 | 0.00974974 | 0.522434 | 0.00526951 | 0.369121 |
| right_tail_loss | 0.950 | 0.0189177 | 46 | 0.0121576 | 0.322832 | 0.00846784 | 0.414297 |
| right_tail_loss | 0.975 | 0.0260456 | 23 | 0.0146089 | 0.236968 | 0.0113013 | 0.383413 |
| right_tail_loss | 0.990 | 0.0370088 | 10 | 0.0171211 | 0.231959 | 0.013441 | 0.352692 |
| absolute_gap | 0.900 | 0.0155233 | 169 | 0.00965334 | 0.293977 | 0.00689961 | 0.401503 |
| absolute_gap | 0.925 | 0.0175078 | 127 | 0.0105772 | 0.261802 | 0.00786988 | 0.397782 |
| absolute_gap | 0.950 | 0.020701 | 85 | 0.0118328 | 0.25315 | 0.00892439 | 0.381347 |
| absolute_gap | 0.975 | 0.0270259 | 43 | 0.0143999 | 0.167275 | 0.0120367 | 0.372398 |
| absolute_gap | 0.990 | 0.0372773 | 17 | 0.0182071 | 0.0771593 | 0.0168379 | 0.353301 |

- The GPD threshold table is computed on raw left loss, raw right loss, and the absolute gap; it should not be read as a forecast-model diagnostic.
- The Hill and GPD shape estimates are deliberately reported over multiple thresholds because tail-index estimates are sensitive in samples of this length.

#### Target Distribution Figures

| Figure | Tail side | Source | Claim scope | Docs file |
| --- | --- | --- | --- | --- |
| `target_tail_motivation` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_tail_motivation.png` |
| `target_gap_histogram_density` | `target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_gap_histogram_density.png` |
| `target_loss_qq_left_tail` | `left_tail` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_loss_qq_left_tail.png` |
| `target_loss_qq_right_tail` | `right_tail` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_loss_qq_right_tail.png` |
| `target_log_survival` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_log_survival.png` |
| `target_mean_excess` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_mean_excess.png` |
| `target_hill_plot` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_hill_plot.png` |

### Gold Panel Construction

| Measure | Value |
| --- | --- |
| Gold modeling rows | 2393 |
| Gold columns | 1428 |
| Target-audit rows | 2393 |
| Clean target rows | 2196 |
| Forecast-sample rows | 1712 |
| Rows before combined clean start | 420 |
| Target-not-clean rows | 197 |
| Mapping excluded rows | 64 |

| Target audit reason | Rows |
| --- | --- |
| None | 2196 |
| roll_sq_excluded | 195 |
| missing_reference_price | 1 |
| missing_previous_jpx_session | 1 |

- The cache lower bound is 2016-07-19, but XLC/core predictor coverage pushes the actual forecast sample to the combined clean start.
- Target exclusion is explicit: roll/SQ windows and the single missing reference price are carried as audit evidence, not silently dropped.
- The forecast-sample reason column makes the sample boundary reproducible row by row.

### Calendar And Timing Map

| Measure | Value |
| --- | --- |
| Normal trading mappings | 2323 |
| U.S./Japan desync mappings | 1 |
| NYSE early-close mappings | 32 |
| EDT rows | 1553 |
| EST rows | 840 |

- The map covers EST/EDT, early closes, U.S./Japan holiday desynchronization, and normal trading alignments.
- Desync rows are not treated as normal forecast rows.
- The timing map is part of the leakage-bound gold artifact, not ad hoc evaluation logic.

### Feature Coverage

| Source family | Block | Features | Mean missing | Max missing |
| --- | --- | --- | --- | --- |
| Asia proxy | Asia proxy | 10 | 0.000% | 0.000% |
| cboe_volatility | fred_core | 2 | 0.000% | 0.000% |
| cross_market_derived | Asia proxy | 1 | 0.000% | 0.000% |
| cross_market_derived | fred_core | 2 | 0.000% | 0.000% |
| cross_market_derived | JP proxy | 2 | 0.000% | 0.000% |
| cross_market_derived | US core | 2 | 0.000% | 0.000% |
| event_calendar | calendar_controls | 7 | 0.000% | 0.000% |
| fred_core | fred_core | 9 | 0.000% | 0.000% |
| FRED credit enriched | FRED credit enriched | 4 | 62.179% | 62.208% |
| fx_core | fx_core | 4 | 0.000% | 0.000% |
| JP history | JP only | 37 | 0.005% | 0.058% |
| JP proxy | JP proxy | 8 | 0.000% | 0.000% |
| J-Quants N225 options | JP only | 30 | 1.552% | 14.486% |
| massive_daily | US core | 40 | 0.001% | 0.058% |
| massive_minute | Asia proxy | 60 | 0.000% | 0.000% |
| massive_minute | JP proxy | 24 | 0.346% | 4.147% |
| massive_minute | US late session | 84 | 0.000% | 0.000% |
| massive_optional | massive_optional | 2 | 0.000% | 0.000% |

- U.S. core, proxy ETFs, minute late-session features, CBOE VIX, FRED rates, FRED H.10 FX, and any audit-gated options-risk fields are separated by source family and block.
- Credit-spread FRED features are enriched/optional and visibly late-starting, so they do not move the core clean start.
- Feature coverage should be read together with the leakage summary; high coverage alone is not enough without timestamp validity.

### Leakage Audit

| Field | Value |
| --- | --- |
| Status | `pass_with_warnings` |
| Rows audited | `780118` |
| Failures | `0` |
| Warnings | `609237` |
| Panel row count | `2393` |
| Panel signature seed | `42` |
| Panel signature | `f1ca88ded1c0cf25817205318cce38b3c2bfe6e84c220cfb9b1d16d9dfa4d5cc` |

- Zero failures means no audited row violated the hard timestamp invariant.
- Warnings are retained because they identify conservative-lag or missing-feature situations that may matter for interpretation.
- The panel signature is deterministic and binds the leakage check to the current gold panel/config.

## Results Context: Model Configuration And Evaluation

### Pipeline Structure

| Step | Layer | Purpose |
| --- | --- | --- |
| 1 | Vendor and calendar sources | Pull or read J-Quants, Massive, FRED, CBOE, and exchange-calendar inputs. |
| 2 | Bronze and silver cache | Preserve typed vendor/cache rows, then normalize point-in-time research features. |
| 3 | Gold modeling panel | Join targets, calendar map, feature coverage, and leakage-bound signatures. |
| 4 | Leakage and coverage gates | Enforce timestamp ordering and sample eligibility before evaluation. |
| 5 | Baseline benchmarks and ML-tail registry | Run target-history/econometric baseline benchmarks and LightGBM tail-model families. |
| 6 | Metrics, inference, diagnostics | Build loss matrices, DM/MCS/Murphy diagnostics, stress windows, and result matrix artifacts. |
| 7 | Results snapshot | Summarize run-specific evidence and claim boundaries for reader review. |

- Data-access and cache artifacts live under `data/bronze` and `data/silver`.
- Durable modeling evidence lives under `data/gold`; forecast/evaluation/reporting read from gold and reports.
- Run-specific forecasts, metrics, diagnostics, and LaTeX tables live under `reports/runs/<run_id>`.

### Model And Evaluation Protocol

- The registered risk level is `tail_level = 0.95`; the nominal VaR exception rate is 5%.
- A VaR exception is counted when `realized_loss > var_forecast`; this follows the
  standard exception-counting logic of VaR backtesting, but the snapshot does not
  apply Basel green/yellow/red traffic-light capital zones.
- Forecast evaluation is based on coverage diagnostics, Kupiec/Christoffersen
  tests where available, quantile loss, Fissler-Ziegel joint VaR-ES loss, and
  DM/MCS inference.
- Benchmarks use target-history information only. ML-tail models add predictors through fixed nested information sets.
- Most specifications use expanding pre-forecast training histories. The rolling-quantile benchmark is the designed exception and uses the most recent 1,000 clean observations.
- LightGBM hyperparameters are held fixed across information sets and refit dates; the snapshot reports model-family evidence rather than tuning-search evidence.
- DM/MCS inference is read on average across the unconditional evaluation sample. CPA is read as a conditional loss-difference diagnostic, not as a forecasting model.

## Results And Discussion

### Main result tables

#### Benchmark Suite

Status: `completed`; forecast rows: `17781`; metric rows: `18`; failures: `0`.

| Benchmark layer | Status | Forecast rows | Diagnostic rows | Failures | How to read it |
| --- | --- | --- | --- | --- | --- |
| baseline | `completed` | `8544` | `12` | `0` | Implemented evidence for target-history and econometric baseline benchmark models. |
| advanced econometric | `completed_nonblocking` | `9237` | `2690` | `0` | Implemented nonblocking advanced econometric benchmark forecasts; review with common-sample gates. |

| Model | Information set | Tail side | Rows | VaR breach rate | Exceptions | Mean quantile loss | Mean FZ loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Taylor ALD/FZ0 asymmetric slope | Target history | left_tail | 712 | 6.039% | 43 | 0.0013351 | -3.71346 |
| Taylor ALD/FZ0 asymmetric slope | Target history | right_tail | 712 | 6.039% | 43 | 0.0012591 | -3.68621 |
| Taylor ALD/FZ0 SAV | Target history | left_tail | 712 | 5.618% | 40 | 0.00133287 | -3.71098 |
| Taylor ALD/FZ0 SAV | Target history | right_tail | 712 | 5.758% | 41 | 0.00129168 | -3.66603 |
| ewma_vol_scaled | Target history | left_tail | 712 | 5.337% | 38 | 0.00140619 | -3.64732 |
| ewma_vol_scaled | Target history | right_tail | 712 | 4.494% | 32 | 0.00134642 | -3.6576 |
| garch_t | Target history | left_tail | 712 | 6.180% | 44 | 0.00136884 | -3.69845 |
| garch_t | Target history | right_tail | 712 | 4.073% | 29 | 0.00127529 | -3.71067 |
| gas_t_location_scale | Target history | left_tail | 712 | 6.461% | 46 | 0.00135331 | -3.68971 |
| gas_t_location_scale | Target history | right_tail | 712 | 4.916% | 35 | 0.00130513 | -3.67517 |
| gjr_garch_evt | Target history | left_tail | 712 | 6.180% | 44 | 0.00133292 | -3.74126 |
| gjr_garch_evt | Target history | right_tail | 712 | 5.618% | 40 | 0.00122515 | -3.72456 |
| gjr_garch_t | Target history | left_tail | 712 | 7.163% | 51 | 0.00134197 | -3.71716 |
| gjr_garch_t | Target history | right_tail | 712 | 4.073% | 29 | 0.00121663 | -3.75116 |
| historical_quantile | Target history | left_tail | 712 | 5.618% | 40 | 0.00148102 | -3.53341 |
| historical_quantile | Target history | right_tail | 712 | 6.742% | 48 | 0.00150422 | -3.40805 |
| rolling_quantile | Target history | left_tail | 712 | 5.899% | 42 | 0.0014857 | -3.51769 |
| rolling_quantile | Target history | right_tail | 712 | 7.163% | 51 | 0.00149803 | -3.42807 |

- Baseline benchmark rows set the target-history/econometric reference that ML models should be interpreted against.
- Advanced econometric benchmark families are nonblocking; rows with valid forecasts are empirical evidence subject to the same sample and inference gates, while unavailable rows remain diagnostics.
- The table is not a leaderboard by itself; coverage, exception counts, quantile loss, and FZ loss must be read together.
- Common-sample rows are reported directly so readers can see the effective evidence size.

#### Primary ML Specifications

Status: `completed LGBM ML-tail models`; implemented models: `LGBM direct quantile`, `LGBM location-scale empirical`, `LGBM POT-GPD plain MLE`, `LGBM POT-GPD UniBM block-maxima shape`, `LGBM median/MAD POT-GPD plain MLE`, `LGBM median/MAD POT-GPD UniBM block-maxima shape`, `LGBM median/IQR POT-GPD plain MLE`, `LGBM median/IQR POT-GPD UniBM block-maxima shape`; forecast rows: `42448`; failures: `0`.

| Model | Information set | Tail side | Rows | VaR breach rate | Exceptions | Mean quantile loss | Mean FZ loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LGBM direct quantile | JP only | left_tail | 526 | 8.935% | 47 | 0.0014354 | -3.48857 |
| LGBM direct quantile | JP + US close core | left_tail | 526 | 11.217% | 59 | 0.00115991 | -3.64375 |
| LGBM direct quantile | JP + US close core + JP proxy | left_tail | 526 | 10.837% | 57 | 0.00111243 | -3.82564 |
| LGBM direct quantile | JP + US close core + JP proxy + Asia proxy | left_tail | 526 | 10.646% | 56 | 0.00111593 | -3.81429 |
| LGBM direct quantile | JP only | right_tail | 526 | 8.745% | 46 | 0.00130129 | -3.53217 |
| LGBM direct quantile | JP + US close core | right_tail | 526 | 11.027% | 58 | 0.00124553 | -3.49907 |
| LGBM direct quantile | JP + US close core + JP proxy | right_tail | 526 | 12.167% | 64 | 0.00120732 | -3.58074 |
| LGBM direct quantile | JP + US close core + JP proxy + Asia proxy | right_tail | 526 | 12.167% | 64 | 0.00120213 | -3.59251 |

- This primary ML table remains strict and reports only ML-tail rows that pass the registered common-sample and forecast-validity gates; coverage is reviewed separately.
- Location-scale empirical and plain POT-GPD are primary candidates only after their valid OOS coverage, standardized-loss, exceedance, and ES-validity gates pass.
- Differences across information blocks are candidate forecast evidence only after the common-sample, coverage, and inference diagnostics are reviewed.
- Coverage review: `8/8` primary ML rows differ from the expected breach rate by more than 2.5 percentage points, so quantile/FZ loss differences alone must not be read as forecast improvement.

#### Side-specific ML-tail Promotion Gate

| Role | Model | Information set | Tail side | Rows | Breach | Q loss | FZ loss | DM q | DM FZ | MCS q/FZ | Gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| left promoted | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | left_tail | 525 | 5.333% | 0.000931646 | -4.17075 | -0.000219582; p=0.025; reject10 | -0.440666; p=0.054; reject10 | in / in | pass |
| right promoted | LGBM location-scale empirical | JP + US close core + JP proxy | right_tail | 492 | 5.285% | 0.00107217 | -3.93242 | -0.000178235; p=0.034; reject10 | -0.394587; p=0.008; reject10 | in / in | pass |

- This paper-facing bridge promotes side-specific ML-tail candidates only after the N/coverage gate and restricted common-sample inference are visible.
- The current run's promoted rows are exactly the rows shown above; read them as side-specific paper candidates, not as a universal family ranking.
- This is not a universal model-family ranking and does not replace the strict primary nested-information-set table above.

#### ML-tail artifact relationship

| Artifact | Rows | Role | Claim boundary |
| --- | --- | --- | --- |
| `ml_tail_metrics.parquet` | 8 | Primary ML nested-information-set comparison | Eligible for primary discussion after author review. |
| `ml_tail_metrics_per_model.parquet` | 64 | Per-model diagnostics on each model's own valid OOS rows | Not a cross-model comparison and not a replacement primary ML table. |
| `ml_tail_result_matrix.parquet` | 384 | Restricted common-sample VaR-only and VaR-ES comparisons | Restricted evidence; direct quantile rows here are comparison anchors. |

- `ml_tail_metrics.parquet` is the primary nested-information-set artifact. It contains the ML-tail rows that survived the strict common-sample gate in this run.
- `ml_tail_metrics_per_model.parquet` reports each implemented ML-tail model on its own valid OOS rows; it is useful for debugging coverage but is not a cross-model comparison table.
- `ml_tail_result_matrix.parquet` creates restricted common samples for VaR-only and VaR-ES comparisons across model families and within-model information-set increments.

### Other result tables

#### All-model diagnostic scan

| Suite | Model | Information set | Metric rows | OOS N mean+-sd | Breach mean+-sd | Abs cov err mean+-sd | Q loss mean+-sd | FZ loss mean+-sd | ES severity mean+-sd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benchmark_advanced | Taylor ALD/FZ0 SAV | Target history | 2 | 712 +/- 0 | 5.688% +/- 0.099% | 0.688% +/- 0.099% | 0.00131228 +/- 2.9124e-05 | -3.68851 +/- 0.0317793 | 0.00890717 +/- 0.000780652 |
| benchmark_advanced | Taylor ALD/FZ0 asymmetric slope | Target history | 2 | 712 +/- 0 | 6.039% +/- 0.000% | 1.039% +/- 0.000% | 0.0012971 +/- 5.37372e-05 | -3.69984 +/- 0.0192644 | 0.00853049 +/- 0.000741618 |
| benchmark_advanced | care_expectile_asymmetric_slope | Target history | 2 | 643 +/- 36.7696 | 7.857% +/- 0.119% | 2.857% +/- 0.119% | 0.00138179 +/- 9.09011e-05 | -3.5814 +/- 0.0433453 | 0.00828488 +/- 0.00057407 |
| benchmark_advanced | care_expectile_sav | Target history | 2 | 639.5 +/- 41.7193 | 7.628% +/- 1.050% | 2.628% +/- 1.050% | 0.00141169 +/- 6.66442e-05 | -3.54433 +/- 0.0812983 | 0.00860785 +/- 0.00047848 |
| benchmark_advanced | caviar_asymmetric_slope | Target history | 2 | 496 +/- 2.82843 | 6.853% +/- 0.531% | 1.853% +/- 0.531% | 0.00153106 +/- 5.83979e-05 | -3.50138 +/- 0.0280187 | 0.0101962 +/- 0.00111158 |
| benchmark_advanced | caviar_sav | Target history | 2 | 491 +/- 4.24264 | 6.109% +/- 0.235% | 1.109% +/- 0.235% | 0.00156616 +/- 1.15443e-05 | -3.47302 +/- 0.0818915 | 0.0116927 +/- 2.42033e-05 |
| benchmark_advanced | gas_t_location_scale | Target history | 2 | 712 +/- 0 | 5.688% +/- 1.092% | 0.772% +/- 0.973% | 0.00132922 +/- 3.40701e-05 | -3.68244 +/- 0.0102815 | 0.00963117 +/- 0.00135966 |
| benchmark_advanced | gas_t_pot_gpd | Target history | 2 | 213 +/- 0 | 6.338% +/- 2.324% | 1.643% +/- 1.892% | 0.00153384 +/- 0.000369124 | -3.4095 +/- 0.531756 | 0.0102243 +/- 0.00490727 |
| benchmark_baseline | ewma_vol_scaled | Target history | 2 | 712 +/- 0 | 4.916% +/- 0.596% | 0.421% +/- 0.119% | 0.00137631 +/- 4.22623e-05 | -3.65246 +/- 0.00726491 | 0.00935753 +/- 0.00102075 |
| benchmark_baseline | garch_t | Target history | 2 | 712 +/- 0 | 5.126% +/- 1.490% | 1.053% +/- 0.179% | 0.00132206 +/- 6.61472e-05 | -3.70456 +/- 0.008634 | 0.00980706 +/- 0.00169367 |
| benchmark_baseline | gjr_garch_evt | Target history | 2 | 712 +/- 0 | 5.899% +/- 0.397% | 0.899% +/- 0.397% | 0.00127904 +/- 7.62103e-05 | -3.73291 +/- 0.0118038 | 0.00835519 +/- 0.00102391 |
| benchmark_baseline | gjr_garch_t | Target history | 2 | 712 +/- 0 | 5.618% +/- 2.185% | 1.545% +/- 0.874% | 0.0012793 +/- 8.86285e-05 | -3.73416 +/- 0.0240435 | 0.00897632 +/- 0.00228707 |
| benchmark_baseline | historical_quantile | Target history | 2 | 712 +/- 0 | 6.180% +/- 0.795% | 1.180% +/- 0.795% | 0.00149262 +/- 1.64042e-05 | -3.47073 +/- 0.0886467 | 0.0122237 +/- 0.000118131 |
| benchmark_baseline | rolling_quantile | Target history | 2 | 712 +/- 0 | 6.531% +/- 0.894% | 1.531% +/- 0.894% | 0.00149186 +/- 8.71876e-06 | -3.47288 +/- 0.0633731 | 0.0116079 +/- 0.000106648 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP only | 2 | 483 +/- 0 | 5.383% +/- 1.171% | 0.828% +/- 0.542% | 0.00146985 +/- 0.000109461 | -3.5216 +/- 0.0707293 | 0.00888447 +/- 0.000143937 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP + US close core | 2 | 481.5 +/- 2.12132 | 6.436% +/- 0.853% | 1.436% +/- 0.853% | 0.00108676 +/- 8.86793e-05 | -3.99403 +/- 0.158346 | 0.00718449 +/- 0.00207257 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy | 2 | 471.5 +/- 0.707107 | 5.302% +/- 0.308% | 0.302% +/- 0.308% | 0.00100749 +/- 0.000100313 | -4.09971 +/- 0.264164 | 0.00680265 +/- 0.00163721 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy + Asia proxy | 2 | 468.5 +/- 0.707107 | 5.549% +/- 0.897% | 0.634% +/- 0.776% | 0.00104722 +/- 0.000163982 | -4.06048 +/- 0.276386 | 0.00711972 +/- 0.00104464 |
| ml_tail | LGBM POT-GPD plain MLE | JP only | 2 | 483 +/- 0 | 5.383% +/- 1.464% | 1.035% +/- 0.542% | 0.00147256 +/- 0.000106565 | -3.52244 +/- 0.0781069 | 0.00885274 +/- 0.000158527 |
| ml_tail | LGBM POT-GPD plain MLE | JP + US close core | 2 | 480.5 +/- 2.12132 | 6.345% +/- 1.002% | 1.345% +/- 1.002% | 0.00108631 +/- 9.54067e-05 | -4.00193 +/- 0.176328 | 0.00721847 +/- 0.00240082 |
| ml_tail | LGBM POT-GPD plain MLE | JP + US close core + JP proxy | 2 | 471.5 +/- 0.707107 | 4.984% +/- 0.157% | 0.111% +/- 0.022% | 0.00101241 +/- 0.000106195 | -4.09404 +/- 0.254903 | 0.00716331 +/- 0.00181962 |
| ml_tail | LGBM POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | 2 | 468.5 +/- 0.707107 | 5.335% +/- 1.199% | 0.848% +/- 0.474% | 0.00104789 +/- 0.000164757 | -4.03719 +/- 0.252588 | 0.00740795 +/- 0.000681032 |
| ml_tail | LGBM direct quantile | JP only | 2 | 553 +/- 0 | 8.590% +/- 0.128% | 3.590% +/- 0.128% | 0.00134342 +/- 0.000113822 | -3.53431 +/- 0.0641321 | 0.00804484 +/- 0.000442493 |
| ml_tail | LGBM direct quantile | JP + US close core | 2 | 553 +/- 0 | 10.669% +/- 0.256% | 5.669% +/- 0.256% | 0.00117965 +/- 3.54633e-05 | -3.60368 +/- 0.0582045 | 0.00667986 +/- 0.000619209 |
| ml_tail | LGBM direct quantile | JP + US close core + JP proxy | 2 | 526 +/- 0 | 11.502% +/- 0.941% | 6.502% +/- 0.941% | 0.00115987 +/- 6.70949e-05 | -3.70319 +/- 0.173172 | 0.00604356 +/- 9.51192e-05 |
| ml_tail | LGBM direct quantile | JP + US close core + JP proxy + Asia proxy | 2 | 526 +/- 0 | 11.407% +/- 1.075% | 6.407% +/- 1.075% | 0.00115903 +/- 6.09532e-05 | -3.7034 +/- 0.15682 | 0.00610003 +/- 7.05826e-05 |
| ml_tail | LGBM location-scale empirical | JP only | 2 | 507 +/- 0 | 5.325% +/- 1.116% | 0.789% +/- 0.460% | 0.00146285 +/- 0.000100628 | -3.50895 +/- 0.044279 | 0.0091254 +/- 0.000211464 |
| ml_tail | LGBM location-scale empirical | JP + US close core | 2 | 504 +/- 1.41421 | 6.845% +/- 0.402% | 1.845% +/- 0.402% | 0.00106462 +/- 9.52559e-05 | -4.03689 +/- 0.210575 | 0.00647965 +/- 0.00167941 |
| ml_tail | LGBM location-scale empirical | JP + US close core + JP proxy | 2 | 490.5 +/- 2.12132 | 5.096% +/- 0.266% | 0.188% +/- 0.136% | 0.00100219 +/- 9.89683e-05 | -4.09044 +/- 0.22347 | 0.00696187 +/- 0.00127074 |
| ml_tail | LGBM location-scale empirical | JP + US close core + JP proxy + Asia proxy | 2 | 488 +/- 1.41421 | 5.530% +/- 1.723% | 1.218% +/- 0.750% | 0.00102991 +/- 0.000167558 | -4.10565 +/- 0.353898 | 0.00710378 +/- 0.000292529 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP only | 2 | 553 +/- 0 | 3.526% +/- 0.639% | 1.474% +/- 0.639% | 0.00129257 +/- 0.00011271 | -3.73974 +/- 0.0651108 | 0.010541 +/- 0.000601292 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP + US close core | 2 | 553 +/- 0 | 5.515% +/- 0.639% | 0.515% +/- 0.639% | 0.00103011 +/- 5.46154e-05 | -3.97795 +/- 0.099235 | 0.00700977 +/- 0.000580301 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy | 2 | 526 +/- 0 | 4.658% +/- 0.403% | 0.342% +/- 0.403% | 0.000954686 +/- 5.82553e-05 | -4.09369 +/- 0.134897 | 0.00677158 +/- 0.000279547 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy + Asia proxy | 2 | 525.5 +/- 0.707107 | 4.853% +/- 0.948% | 0.671% +/- 0.208% | 0.000960087 +/- 4.06676e-05 | -4.07525 +/- 0.120714 | 0.00696095 +/- 0.00131627 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP only | 2 | 553 +/- 0 | 3.345% +/- 0.639% | 1.655% +/- 0.639% | 0.00129686 +/- 0.000101457 | -3.74068 +/- 0.0616673 | 0.010795 +/- 0.00030634 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP + US close core | 2 | 553 +/- 0 | 5.515% +/- 0.895% | 0.633% +/- 0.729% | 0.00102732 +/- 5.76573e-05 | -3.97539 +/- 0.0916481 | 0.00687791 +/- 0.00084042 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy | 2 | 526 +/- 0 | 4.848% +/- 0.403% | 0.285% +/- 0.215% | 0.000956345 +/- 5.92859e-05 | -4.09815 +/- 0.139272 | 0.00655753 +/- 0.000221165 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | 2 | 525.5 +/- 0.707107 | 4.758% +/- 0.814% | 0.575% +/- 0.342% | 0.000959934 +/- 4.00052e-05 | -4.08048 +/- 0.127666 | 0.00692973 +/- 0.00115493 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP only | 2 | 483 +/- 0 | 5.901% +/- 0.439% | 0.901% +/- 0.439% | 0.00140616 +/- 0.000128187 | -3.61262 +/- 0.025875 | 0.00953278 +/- 0.000274886 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP + US close core | 2 | 482.5 +/- 0.707107 | 7.461% +/- 0.011% | 2.461% +/- 0.011% | 0.00110292 +/- 2.28841e-05 | -4.05501 +/- 0.0364613 | 0.00749599 +/- 9.46231e-05 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy | 2 | 473 +/- 0 | 7.822% +/- 0.000% | 2.822% +/- 0.000% | 0.0010485 +/- 5.11708e-05 | -4.119 +/- 0.141249 | 0.00673152 +/- 0.000401304 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy + Asia proxy | 2 | 472 +/- 0 | 7.415% +/- 0.599% | 2.415% +/- 0.599% | 0.00104843 +/- 4.66491e-05 | -4.0884 +/- 0.0812837 | 0.0071145 +/- 0.000971143 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP only | 2 | 483 +/- 0 | 5.590% +/- 0.878% | 0.621% +/- 0.834% | 0.0014044 +/- 0.000126909 | -3.60432 +/- 0.0205047 | 0.00980936 +/- 0.000169992 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP + US close core | 2 | 482 +/- 1.41421 | 6.951% +/- 0.461% | 1.951% +/- 0.461% | 0.00110068 +/- 2.85627e-05 | -4.02564 +/- 0.104884 | 0.00787408 +/- 0.000308957 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP + US close core + JP proxy | 2 | 473 +/- 0 | 7.611% +/- 0.299% | 2.611% +/- 0.299% | 0.00104318 +/- 5.82811e-05 | -4.1223 +/- 0.111809 | 0.00673212 +/- 0.000276524 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | 2 | 472 +/- 0 | 6.886% +/- 0.150% | 1.886% +/- 0.150% | 0.001045 +/- 5.33707e-05 | -4.11482 +/- 0.0764907 | 0.00745997 +/- 0.000750903 |

- This table joins `benchmark_metrics_per_model.parquet` and `ml_tail_metrics_per_model.parquet` so all benchmark and LGBM tail-model variants are visible in one place.
- Mean and standard deviation are computed across registered metric rows for the same suite/model/information-set configuration; for most rows this summarizes left- and right-tail metrics.
- It is a diagnostic scan, not the formal cross-model comparison table. Cross-model claims still require common-sample result-matrix, DM, and MCS evidence because valid dates and model gates can differ.

#### Restricted Common-Sample Result Matrix

| Family | Axis | Loss | Rows | Common N | Date range | Joint exceptions |
| --- | --- | --- | --- | --- | --- | --- |
| nested information sets | information_set_increment | var_coverage | 64 | 466 to 526 | 2023-01-26 to 2026-05-08 | 37 to 76 |
| nested information sets | information_set_increment | var_es_fz_loss | 64 | 466 to 526 | 2023-01-26 to 2026-05-08 | 37 to 76 |
| nested information sets | information_set_increment | var_quantile_loss | 64 | 466 to 526 | 2023-01-26 to 2026-05-08 | 37 to 76 |
| tail_model_family | model_family | var_coverage | 64 | 467 to 483 | 2023-06-16 to 2026-05-08 | 48 to 67 |
| tail_model_family | model_family | var_es_fz_loss | 64 | 467 to 483 | 2023-06-16 to 2026-05-08 | 48 to 67 |
| tail_model_family | model_family | var_quantile_loss | 64 | 467 to 483 | 2023-06-16 to 2026-05-08 | 48 to 67 |

- The result matrix is the right place to compare direct quantile, location-scale empirical, plain POT-GPD, and the robust plain POT-GPD routes on their restricted common dates.
- It separates VaR-only losses from VaR-ES joint scoring, so VaR-only claims are not confused with ES claims.
- Restricted direct-quantile performance is only a comparison anchor for the tail-model family; it does not replace the primary direct-quantile evidence.
- DM and MCS records are emitted only where registered row-count and exception-count gates pass; otherwise the result matrix remains descriptive.

#### Stress And Diagnostic Windows

| Suite | Rows | Window labels |
| --- | --- | --- |
| benchmark | 144 | `loss_top_decile` |
| ml_tail | 212 | `loss_top_decile`, `vix_top_decile` |

- Stress windows identify high-loss or high-volatility subsamples for two-sided risk diagnostics.
- These rows use reproducible full-sample classifiers in this first pass, so they should be described as diagnostics rather than a live stress classifier.
- They are useful for finding whether model behavior changes in difficult regimes before writing manuscript discussion.

### Results interpretation and claim boundaries

<!-- generated: results_discussion -->

#### Data and timing audit

- The gold timing map covers `2016-07-19 to 2026-05-08` and the combined clean start is `2018-06-20`.
- No forecast-sample rows before `2018-06-20` enter the modeling evidence.
- The leakage check reports status `pass_with_warnings` with zero leakage failures and `609237` warnings.
- FRED vintage safety is recorded as `False`; FRED values use conservative release timing but remain current historical observations rather than ALFRED real-time vintages.

#### Baseline benchmarks and advanced econometric benchmarks

- `benchmark_metrics.parquet` reports `18` common-sample rows across `9` baseline benchmark model families and `2` tail side(s), while benchmark forecasts contain `17781` model-date rows.
- Baseline benchmark models are external target-history and econometric references; this section does not rank them.
- Advanced econometric benchmark rows are implemented for `8` model families and contribute `9237` nonblocking forecast rows; these rows are claim-gated diagnostics unless a manuscript table explicitly promotes them through the same sample and inference review.
- Baseline benchmark breach rates have a median of `0.0589888`, within 2.5 percentage points of the nominal level, indicating reasonable coverage calibration relative to the ML-tail models whose breach rates are reported in the nested-information-set section.

#### Primary ML specifications across nested information sets

- `ml_tail_metrics.parquet` defines the primary ML specification comparison across nested information sets for this run.
- The primary ML artifact contains `4` information sets, `1` tail level(s), and `2` tail side(s); the retained primary ML rows are `LGBM direct quantile`.
- The implemented ML-tail registry is `LGBM direct quantile`, `LGBM location-scale empirical`, `LGBM POT-GPD plain MLE`, `LGBM POT-GPD UniBM block-maxima shape`, `LGBM median/MAD POT-GPD plain MLE`, `LGBM median/MAD POT-GPD UniBM block-maxima shape`, `LGBM median/IQR POT-GPD plain MLE`, `LGBM median/IQR POT-GPD UniBM block-maxima shape`, but the primary nested-information-set comparison should be read only from `ml_tail_metrics.parquet`.
- The nested information sets report downside-risk and upside-risk surfaces separately. The registered artifacts show different left/right patterns, and the generator does not assume that the two sides share the same economic mechanism.
- Coverage warning: all `8` primary ML rows exhibit VaR breach rates (`0.0874525` to `0.121673`) that exceed the nominal level by more than 2.5 percentage points. Quantile-loss and FZ-loss differences across the nested information sets must be interpreted in this context; lower loss scores may partly reflect less conservative VaR estimates rather than better conditional tail calibration.
- For `left_tail / LGBM direct quantile / tail=0.950`, the largest quantile-loss change occurs at the first information-set augmentation (adding U.S. close core); subsequent additions of Japan proxy and Asia proxy ETFs contribute diminishing incremental loss changes. This saturation pattern is descriptive and does not automatically reduce the value of the broader information set.
- The nested information sets are used to assess candidate incremental U.S.-close information under strict common-sample rules; they do not by themselves establish forecast improvement.

#### Restricted model-family comparison

- `ml_tail_result_matrix.parquet` contains restricted common-sample comparisons for `8` LightGBM tail-model families.
- The restricted common-N range is `466 to 526` and the joint-exception range is `37 to 76`.
- Recorded claim scopes are `restricted_model_comparison_not_primary`; these rows are restricted evidence and cannot replace the primary ML nested-information-set comparison.
- The tail-model family comparison is severely sample-limited: the largest restricted common-N is `483` rows. No model-family ranking claim is supportable from this restricted sample; extended OOS coverage is needed before tail-model family ranking becomes meaningful.
- Result-matrix inference is recorded separately from the primary suite-level DM/MCS: restricted DM records include `208` gate-pass rows and `104` unavailable rows; restricted MCS records include `128` gate-pass rows and `64` unavailable rows. These entries are restricted common-sample diagnostics, not primary model-family rankings.
- The result matrix is a matched-date diagnostic layer. It should not be worded as one family being better than another.

#### Coverage and inference gates

- Coverage review flags `8/8` primary ML rows with breach rates more than 2.5 percentage points from nominal coverage; Kupiec p-values fall below 0.05 in `8/8` reported rows and Christoffersen p-values fall below 0.05 in `0/8` reported rows.
- Model-eviction artifacts record `8` retained rows and `56` non-retained rows under the primary ML sample policy.
- Block-bootstrap DM and HLN Tmax MCS artifacts are unconditional forecast-comparison diagnostics; any p-value should be read on average across the unconditional evaluation sample, not as condition-specific evidence.
- Loss differentials alone do not constitute an improvement claim; coverage, exception counts, sample gates, and inference status must be reviewed together.
- Result-matrix tail-event power flags and suite-level inference gates report `0` restricted rows with insufficient tail-event power and `0/48` unavailable DM/MCS inference rows.

#### CPA as conditional loss-difference diagnostics

- The ML-tail nested-information-set CPA artifact is a conditional loss-difference diagnostic across `2` tail side(s), with `48` registered row(s), `48` HAC-Wald gate pass(es), and loss families `var_es_fz_loss`, `var_quantile_loss`.
- The registered cross-model CPA artifact is a conditional loss-difference diagnostic with `560` row(s), `496` HAC-Wald gate pass(es), and loss families `var_es_fz_loss`, `var_quantile_loss`.
- Quantile-loss CPA and FZ-loss CPA are downstream inference over existing loss differentials; CPA does not generate VaR/ES forecasts and does not replace DM/MCS.

#### Supporting diagnostics

- Supporting LaTeX diagnostic table files are present for `4/4` registered diagnostic families.
- `ml_tail_dst_attenuation.parquet` contains `6` DST attenuation rows; these are descriptive timing-regime forecast diagnostics. They do not establish a structural timing mechanism.
- ES severity diagnostics contain `90` finite rows with mean exceedance severity ranging from `0.00529213` to `0.0123073`; this is conditional-on-exception evidence.
- The diagnostic 75th-percentile VaR trigger rule marks `3300` model-date rows; `307` of those rows coincide with VaR exceptions out of `942` total exceptions, and mean triggered exception severity is `0.0122159`. This is a pre-open risk-monitoring diagnostic, not hedge PnL, transaction-cost, or trading-alpha evidence.
- Stress-window diagnostics contain `356` rows, and Murphy diagnostics contain `1600` ML-tail rows.
- Feature-unavailability diagnostics contain `384` rows.
- Figure manifest references:
  - Figure: market_timing_design (Source: manifest.json, config/research_config.json, panel/calendar_map.parquet; Claim scope: design_forecast_origin_not_causal_price_discovery; File: latex/figures/market_timing_design.png).
  - Figure: coverage_breach_rates_simplified_left_tail (Source: metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: headline_coverage_diagnostic_simplified_main_text; File: latex/figures/coverage_breach_rates_simplified_left_tail.png).
  - Figure: coverage_breach_rates_simplified_right_tail (Source: metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: headline_coverage_diagnostic_simplified_main_text; File: latex/figures/coverage_breach_rates_simplified_right_tail.png).
  - Figure: coverage_breach_rates_left_tail (Source: metrics/benchmark_metrics.parquet, metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: coverage_diagnostic_not_primary_claim; File: latex/figures/coverage_breach_rates_left_tail.png).
  - Figure: coverage_breach_rates_right_tail (Source: metrics/benchmark_metrics.parquet, metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: coverage_diagnostic_not_primary_claim; File: latex/figures/coverage_breach_rates_right_tail.png).
  - Figure: tailrisk_information_ladder (Source: metrics/ml_tail_metrics.parquet; Claim scope: headline_nested_information_set_ladder; File: latex/figures/tailrisk_information_ladder.png).
  - Figure: cumulative_loss_difference_left_tail (Source: metrics/benchmark_loss_matrix.parquet, metrics/ml_tail_loss_matrix.parquet, forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: headline_cumulative_loss_difference_sign_fixed; File: latex/figures/cumulative_loss_difference_left_tail.png).
  - Figure: cumulative_loss_difference_right_tail (Source: metrics/benchmark_loss_matrix.parquet, metrics/ml_tail_loss_matrix.parquet, forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: headline_cumulative_loss_difference_sign_fixed; File: latex/figures/cumulative_loss_difference_right_tail.png).
  - Figure: selected_model_performance_left_tail (Source: metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: selected_benchmark_vs_lgbm_main_figure_not_full_result_set; File: latex/figures/selected_model_performance_left_tail.png).
  - Figure: selected_model_performance_right_tail (Source: metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: selected_benchmark_vs_lgbm_main_figure_not_full_result_set; File: latex/figures/selected_model_performance_right_tail.png).
  - Figure: full_sample_var_overlay_left_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: full_sample_var_overlay_fixed_selection_visual_diagnostic; File: latex/figures/full_sample_var_overlay_left_tail.png).
  - Figure: full_sample_var_overlay_right_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: full_sample_var_overlay_fixed_selection_visual_diagnostic; File: latex/figures/full_sample_var_overlay_right_tail.png).
  - Figure: benchmark_murphy_left_tail (Source: metrics/benchmark_murphy.parquet; Claim scope: murphy_diagnostic_benchmark_baseline_common_grid; File: latex/figures/benchmark_murphy_left_tail.png).
  - Figure: benchmark_murphy_right_tail (Source: metrics/benchmark_murphy.parquet; Claim scope: murphy_diagnostic_benchmark_baseline_common_grid; File: latex/figures/benchmark_murphy_right_tail.png).
  - Figure: ml_tail_murphy_left_tail (Source: metrics/ml_tail_murphy.parquet; Claim scope: murphy_diagnostic_ml_tail_nested_information_sets_common_grid; File: latex/figures/ml_tail_murphy_left_tail.png).
  - Figure: ml_tail_murphy_right_tail (Source: metrics/ml_tail_murphy.parquet; Claim scope: murphy_diagnostic_ml_tail_nested_information_sets_common_grid; File: latex/figures/ml_tail_murphy_right_tail.png).
  - Figure: dst_attenuation_left_tail (Source: metrics/ml_tail_dst_attenuation.parquet; Claim scope: descriptive_dst_attenuation_not_structural_causal_identification; File: latex/figures/dst_attenuation_left_tail.png).
  - Figure: dst_attenuation_right_tail (Source: metrics/ml_tail_dst_attenuation.parquet; Claim scope: descriptive_dst_attenuation_not_structural_causal_identification; File: latex/figures/dst_attenuation_right_tail.png).
  - Figure: es_severity_left_tail (Source: metrics/benchmark_metrics.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: es_severity_diagnostic_not_model_selection_claim; File: latex/figures/es_severity_left_tail.png).
  - Figure: es_severity_right_tail (Source: metrics/benchmark_metrics.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: es_severity_diagnostic_not_model_selection_claim; File: latex/figures/es_severity_right_tail.png).
  - Figure: trigger_diagnostics_left_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: trigger_diagnostic_not_pnl_cost_or_alpha; File: latex/figures/trigger_diagnostics_left_tail.png).
  - Figure: trigger_diagnostics_right_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: trigger_diagnostic_not_pnl_cost_or_alpha; File: latex/figures/trigger_diagnostics_right_tail.png).
  - Figure: var_es_stress_overlay_left_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: appendix_stress_overlay_illustration_not_validation; File: latex/figures/var_es_stress_overlay_left_tail.png).
  - Figure: var_es_stress_overlay_right_tail (Source: forecasts/benchmark_forecasts.parquet, forecasts/ml_tail_forecasts.parquet; Claim scope: appendix_stress_overlay_illustration_not_validation; File: latex/figures/var_es_stress_overlay_right_tail.png).
  - Figure: dm_mcs_heatmap_left_tail (Source: metrics/ml_tail_result_matrix_dm.parquet, metrics/ml_tail_result_matrix_mcs.parquet; Claim scope: appendix_dm_mcs_visual_diagnostic; File: latex/figures/dm_mcs_heatmap_left_tail.png).
  - Figure: dm_mcs_heatmap_right_tail (Source: metrics/ml_tail_result_matrix_dm.parquet, metrics/ml_tail_result_matrix_mcs.parquet; Claim scope: appendix_dm_mcs_visual_diagnostic; File: latex/figures/dm_mcs_heatmap_right_tail.png).
  - Figure: evt_standardized_qq_left_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_qq_left_tail.png).
  - Figure: evt_standardized_log_survival_left_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_log_survival_left_tail.png).
  - Figure: evt_standardized_mean_excess_left_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_mean_excess_left_tail.png).
  - Figure: evt_standardized_hill_left_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_hill_left_tail.png).
  - Figure: evt_standardized_threshold_stability_left_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_threshold_stability_left_tail.png).
  - Figure: evt_standardized_qq_right_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_qq_right_tail.png).
  - Figure: evt_standardized_log_survival_right_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_log_survival_right_tail.png).
  - Figure: evt_standardized_mean_excess_right_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_mean_excess_right_tail.png).
  - Figure: evt_standardized_hill_right_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_hill_right_tail.png).
  - Figure: evt_standardized_threshold_stability_right_tail (Source: forecasts/ml_tail_forecasts.parquet; Claim scope: evt_standardized_residual_diagnostic_not_forecast_claim; File: latex/figures/evt_standardized_threshold_stability_right_tail.png).

#### Not yet claimed

- DST attenuation rows are descriptive forecast evidence; structural DST causal identification is not claimed.
- No hedge PnL, transaction-cost, or trading-alpha analysis is performed. The trigger table is a pre-open risk-monitoring diagnostic only.
- Left-tail and right-tail outputs are both economic tail-risk surfaces for futures positions; neither side should be promoted beyond the sample, coverage, and inference gates without author review.
- The current evidence does not create an automatic model-selection statement; any manuscript claim still requires author review of sample gates, coverage, loss metrics, and inference diagnostics.

## Results And Discussion: Figures, Tables, And Source Artifacts

This section merges the former figure/table placement page into the results
snapshot. All generated figures and tables are listed with their intended
interpretation. The words "supporting" and "diagnostic" describe claim scope;
they do not mean the artifact is missing from this page.

### Configuration Robustness Evidence

| Field | Value |
| --- | --- |
| Source primary run | `tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa` |
| Primary-claim allowed | `False` |
| Forecast rows | `142671` |
| Metric rows | `264` |
| Status | `ok` |

| Sensitivity family | Rows / classifications |
| --- | --- |
| LGBM capacity | 108 rows (mixed=16, robust=73, sensitive=19) |
| EWMA lambda | 6 rows (robust=6) |
| POT threshold | 150 rows (boundary_diagnostic=50, robust=99, sensitive=1) |

- The primary design compares pre-specified point-in-time forecast specifications. Configuration sensitivity is robustness evidence and is not used to select primary selections.
- LGBM rows vary only capacity settings; EWMA reports the primary lambda 0.94 plus 0.90 and 0.97; POT threshold rows use forecastable 0.90/0.925 settings and mark 0.95 as a boundary diagnostic at the 95% VaR level.
- Robustness classes describe conclusion stability versus the registered primary specification. They do not feed DM/MCS gates, promoted-model logic, or selected-model figures.

### Generated Table Manifest

| Table | Source artifacts | Claim scope | Tail side | File |
| --- | --- | --- | --- | --- |
| tailrisk_predictor_block_coverage | `panel/feature_coverage.parquet` | `main_text_predictor_block_coverage_information_transparency` | `None` | `latex/tables/tailrisk_predictor_block_coverage_table.tex` |
| benchmark_metrics | `metrics/benchmark_metrics.parquet` | `benchmark_common_sample_metric_table` | `None` | `latex/tables/benchmark_metrics_table.tex` |
| benchmark_left_tail_risk | `metrics/benchmark_metrics.parquet` | `left_tail_benchmark_risk_table` | `left_tail` | `latex/tables/benchmark_left_tail_risk_table.tex` |
| benchmark_right_tail_risk | `metrics/benchmark_metrics.parquet` | `right_tail_benchmark_risk_table` | `right_tail` | `latex/tables/benchmark_right_tail_risk_table.tex` |
| ml_tail_metrics | `metrics/ml_tail_metrics.parquet` | `ml_tail_nested_information_set_table` | `None` | `latex/tables/ml_tail_metrics_table.tex` |
| ml_tail_left_tail_risk | `metrics/ml_tail_metrics.parquet` | `left_tail_ml_tail_primary_risk_table` | `left_tail` | `latex/tables/ml_tail_left_tail_risk_table.tex` |
| ml_tail_right_tail_risk | `metrics/ml_tail_metrics.parquet` | `right_tail_ml_tail_primary_risk_table` | `right_tail` | `latex/tables/ml_tail_right_tail_risk_table.tex` |
| tailrisk_model_inventory | `config/research_config.json`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet` | `main_text_model_inventory_forecast_construction` | `None` | `latex/tables/tailrisk_model_inventory_table.tex` |
| tailrisk_selected_model_performance | `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet` | `selected_benchmark_vs_lgbm_main_figure_rows` | `None` | `latex/tables/tailrisk_selected_model_performance_table.tex` |
| appendix_benchmark_all_models | `metrics/benchmark_metrics_per_model.parquet` | `appendix_full_benchmark_results` | `None` | `latex/tables/appendix_benchmark_all_models_table.tex` |
| ml_tail_promoted_tail_models | `metrics/ml_tail_metrics_per_model.parquet`, `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet` | `side_specific_ml_tail_promotion_gate` | `None` | `latex/tables/ml_tail_promoted_tail_models_table.tex` |
| appendix_lgbm_all_models | `metrics/ml_tail_metrics_per_model.parquet` | `appendix_full_lgbm_results` | `None` | `latex/tables/appendix_lgbm_all_models_table.tex` |
| tailrisk_es_severity | `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet` | `es_severity_diagnostic_table` | `None` | `latex/tables/tailrisk_es_severity_table.tex` |
| tailrisk_trigger_diagnostics | `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet` | `trigger_diagnostic_table` | `None` | `latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` |
| tailrisk_claim_scope | `manifest.json`, `config/research_config.json` | `claim_boundary_reference_table` | `None` | `latex/tables/tailrisk_claim_scope_table.tex` |
| ml_tail_result_matrix | `metrics/ml_tail_result_matrix.parquet` | `restricted_model_comparison_table` | `None` | `latex/tables/ml_tail_result_matrix_table.tex` |
| ml_tail_result_matrix_summary | `metrics/ml_tail_result_matrix.parquet`, `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet` | `restricted_result_matrix_summary_table` | `None` | `latex/tables/ml_tail_result_matrix_summary_table.tex` |
| tailrisk_dm_mcs_summary | `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet` | `main_text_compact_dm_mcs_summary` | `None` | `latex/tables/tailrisk_dm_mcs_summary_table.tex` |
| ml_tail_dst_attenuation | `metrics/ml_tail_dst_attenuation.parquet` | `descriptive_dst_attenuation_table` | `None` | `latex/tables/ml_tail_dst_attenuation_table.tex` |
| appendix_lgbm_configuration_sensitivity | `sensitivity/metrics/lgbm_configuration_sensitivity_metrics.parquet` | `appendix_configuration_robustness_lgbm` | `None` | `sensitivity/latex/tables/appendix_lgbm_configuration_sensitivity_table.tex` |
| appendix_benchmark_configuration_sensitivity | `sensitivity/metrics/benchmark_configuration_sensitivity_metrics.parquet` | `appendix_configuration_robustness_benchmark` | `None` | `sensitivity/latex/tables/appendix_benchmark_configuration_sensitivity_table.tex` |
| appendix_evt_threshold_sensitivity | `sensitivity/metrics/evt_threshold_sensitivity_metrics.parquet` | `appendix_configuration_robustness_evt_threshold` | `None` | `sensitivity/latex/tables/appendix_evt_threshold_sensitivity_table.tex` |

- The table manifest records the generated LaTeX table files, their source artifacts, and their claim scopes.
- Tables are paper-facing exports; the Markdown tables above are snapshot summaries for browser review.

### Table Interpretation Guide

| Results/Discussion role | Artifact | How to read it |
| --- | --- | --- |
| Predictor block and coverage | [tailrisk_predictor_block_coverage_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_predictor_block_coverage_table.tex) | Data/Methods table showing source families, feature counts, examples, missingness, and model role; coverage is not timestamp admissibility. |
| Model inventory | [tailrisk_model_inventory_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_model_inventory_table.tex) | Methods table explaining model families, information sets, VaR construction, ES construction, and role; performance belongs elsewhere. |
| Benchmark floor summary | [benchmark_metrics_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/benchmark_metrics_table.tex) | Results table for target-history and econometric benchmark calibration and loss evidence. |
| Benchmark tail-side details | [benchmark_left_tail_risk_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/benchmark_left_tail_risk_table.tex), [benchmark_right_tail_risk_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/benchmark_right_tail_risk_table.tex) | Tail-specific benchmark rows for left and right risk surfaces. |
| ML information ladder | [ml_tail_metrics_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_metrics_table.tex) | Core nested-information-set table for direct LightGBM; read loss changes with coverage gates. |
| ML tail-side details | [ml_tail_left_tail_risk_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_left_tail_risk_table.tex), [ml_tail_right_tail_risk_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_right_tail_risk_table.tex) | Tail-specific direct LightGBM information-set rows. |
| Selected model performance | [tailrisk_selected_model_performance_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_selected_model_performance_table.tex) | Deterministic selected-row summary after sample-size, coverage, FZ-loss, and quantile-loss gates. |
| Promoted tail rows | [ml_tail_promoted_tail_models_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_promoted_tail_models_table.tex) | Locked side-specific promotion-gate rows; not a universal model-family ranking. |
| Full benchmark scan | [appendix_benchmark_all_models_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/appendix_benchmark_all_models_table.tex) | Complete benchmark inventory supporting benchmark breadth. |
| Full LGBM scan | [appendix_lgbm_all_models_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/appendix_lgbm_all_models_table.tex) | Complete per-model LightGBM scan; do not use as a raw leaderboard. |
| Restricted result matrix | [ml_tail_result_matrix_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_result_matrix_table.tex), [ml_tail_result_matrix_summary_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_result_matrix_summary_table.tex) | Restricted common-sample model-family comparison and summary. |
| Compact DM/MCS summary | [tailrisk_dm_mcs_summary_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_dm_mcs_summary_table.tex) | Headline paired inference table; negative loss differences favor the candidate. |
| ES severity | [tailrisk_es_severity_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_es_severity_table.tex) | Conditional-on-exception severity diagnostic; not standalone model selection. |
| Pre-open trigger diagnostics | [tailrisk_hedge_trigger_diagnostics_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_hedge_trigger_diagnostics_table.tex) | Risk-monitoring diagnostic; not hedge PnL, transaction-cost, alpha, or execution evidence. |
| Claim boundary | [tailrisk_claim_scope_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_claim_scope_table.tex) | Reference table separating headline, restricted, diagnostic, and robustness claims. |
| DST attenuation | [ml_tail_dst_attenuation_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_dst_attenuation_table.tex) | Descriptive timing-regime table; not structural causality. |
| LGBM capacity robustness | [appendix_lgbm_configuration_sensitivity_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/appendix_lgbm_configuration_sensitivity_table.tex) | Configuration robustness only; rows do not select headline models. |
| Benchmark robustness | [appendix_benchmark_configuration_sensitivity_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/appendix_benchmark_configuration_sensitivity_table.tex) | EWMA/benchmark robustness evidence, separate from primary selection. |
| EVT threshold robustness | [appendix_evt_threshold_sensitivity_table.tex](tables/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/appendix_evt_threshold_sensitivity_table.tex) | POT threshold robustness and boundary diagnostics at the 95% VaR level. |

#### Figure 1. Market Timing Design

- Key readings: the diagram defines JST event timing, the matched U.S.-close cutoff, and the OSE day-open target.
- OSE schedule note: pre-2024-11-05 hours use day close 15:15 JST and night session 16:30-05:30 JST; from 2024-11-05, JPX uses day close 15:45 JST and night session 17:00-06:00 JST, with day open still 08:45 JST.
- The OSE night close is timing context; the forecast origin is the matched U.S. cash close plus the data-availability lag.
- It is a session-alignment schematic, not a structural market-transmission diagram.

![market_timing_design](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/market_timing_design.png)

_Figure: `market_timing_design`. Source: `manifest.json`, `config/research_config.json`, `panel/calendar_map.parquet`. Claim scope: `design_forecast_origin_not_causal_price_discovery`. Tail side: `design`. Run file: `latex/figures/market_timing_design.png`._

#### Figure 2. Opening-Gap Tail Motivation

- Key readings: the composite figure combines density, log survival, and mean-excess diagnostics for the raw opening-gap target.
- It motivates tail-risk modeling and does not validate any forecast model.

![target_tail_motivation](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_tail_motivation.png)

_Figure: `target_tail_motivation`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_tail_motivation.png`._

#### Figure 3. Simplified Coverage Breach-Rate Diagnostics

- Key readings: this main-text figure strips coverage diagnostics down to fixed benchmark, direct information ladder, and side-specific promoted candidates.
- Wilson intervals show exception-rate uncertainty around the nominal 5% line.

![coverage_breach_rates_simplified_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/coverage_breach_rates_simplified_left_tail.png)

_Figure: `coverage_breach_rates_simplified_left_tail`. Source: `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `headline_coverage_diagnostic_simplified_main_text`. Tail side: `left_tail`. Run file: `latex/figures/coverage_breach_rates_simplified_left_tail.png`._

![coverage_breach_rates_simplified_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/coverage_breach_rates_simplified_right_tail.png)

_Figure: `coverage_breach_rates_simplified_right_tail`. Source: `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `headline_coverage_diagnostic_simplified_main_text`. Tail side: `right_tail`. Run file: `latex/figures/coverage_breach_rates_simplified_right_tail.png`._

#### Figure 4. Information-Set Ladder

- Key readings: the figure is the direct visual counterpart to the nested-information-set research question.
- Loss changes must still be read with coverage and inference gates.

![tailrisk_information_ladder](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/tailrisk_information_ladder.png)

_Figure: `tailrisk_information_ladder`. Source: `metrics/ml_tail_metrics.parquet`. Claim scope: `headline_nested_information_set_ladder`. Tail side: `left_right`. Run file: `latex/figures/tailrisk_information_ladder.png`._

#### Figure 5. Cumulative Loss Difference

- Key readings: upward movement means the candidate has lower cumulative loss under the fixed anchor-loss-minus-candidate-loss convention.
- This shows whether improvements accumulate through time or are concentrated in a few dates.

![cumulative_loss_difference_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/cumulative_loss_difference_left_tail.png)

_Figure: `cumulative_loss_difference_left_tail`. Source: `metrics/benchmark_loss_matrix.parquet`, `metrics/ml_tail_loss_matrix.parquet`, `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `headline_cumulative_loss_difference_sign_fixed`. Tail side: `left_tail`. Run file: `latex/figures/cumulative_loss_difference_left_tail.png`._

![cumulative_loss_difference_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/cumulative_loss_difference_right_tail.png)

_Figure: `cumulative_loss_difference_right_tail`. Source: `metrics/benchmark_loss_matrix.parquet`, `metrics/ml_tail_loss_matrix.parquet`, `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `headline_cumulative_loss_difference_sign_fixed`. Tail side: `right_tail`. Run file: `latex/figures/cumulative_loss_difference_right_tail.png`._

#### Figure 6. Raw Target Distribution Diagnostics

- Key readings: these figures describe the raw settlement-to-open gap and the left/right loss tails.
- They motivate VaR/ES and POT-GPD modeling, but they do not validate LightGBM+EVT forecasts.

![target_gap_histogram_density](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_gap_histogram_density.png)

_Figure: `target_gap_histogram_density`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `target_distribution`. Run file: `latex/figures/target_gap_histogram_density.png`._

![target_loss_qq_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_loss_qq_left_tail.png)

_Figure: `target_loss_qq_left_tail`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_tail`. Run file: `latex/figures/target_loss_qq_left_tail.png`._

![target_loss_qq_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_loss_qq_right_tail.png)

_Figure: `target_loss_qq_right_tail`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `right_tail`. Run file: `latex/figures/target_loss_qq_right_tail.png`._

![target_log_survival](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_log_survival.png)

_Figure: `target_log_survival`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_log_survival.png`._

![target_mean_excess](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_mean_excess.png)

_Figure: `target_mean_excess`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_mean_excess.png`._

![target_hill_plot](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_hill_plot.png)

_Figure: `target_hill_plot`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_hill_plot.png`._

#### Figure 7. Full Coverage Breach-Rate Diagnostics

- Key readings: bars report realized VaR exception rates against the nominal line.
- Read this first: exception-rate deviations set the boundary for any loss-based interpretation.

![coverage_breach_rates_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/coverage_breach_rates_left_tail.png)

_Figure: `coverage_breach_rates_left_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `coverage_diagnostic_not_primary_claim`. Tail side: `left_tail`. Run file: `latex/figures/coverage_breach_rates_left_tail.png`._

![coverage_breach_rates_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/coverage_breach_rates_right_tail.png)

_Figure: `coverage_breach_rates_right_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `coverage_diagnostic_not_primary_claim`. Tail side: `right_tail`. Run file: `latex/figures/coverage_breach_rates_right_tail.png`._

#### Figure 8. Selected Benchmark-vs-LGBM Performance

- Key readings: compact main-figure rows split models into two broad groups, Benchmark and LGBM.
- Within each tail and group, rows are selected by sufficient sample size, VaR coverage near 5%, then lower FZ loss and quantile loss.
- Full benchmark and LGBM per-model results are exported in full-result tables, so this figure is a readable summary rather than the full result set.

![selected_model_performance_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/selected_model_performance_left_tail.png)

_Figure: `selected_model_performance_left_tail`. Source: `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `selected_benchmark_vs_lgbm_main_figure_not_full_result_set`. Tail side: `left_tail`. Run file: `latex/figures/selected_model_performance_left_tail.png`._

![selected_model_performance_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/selected_model_performance_right_tail.png)

_Figure: `selected_model_performance_right_tail`. Source: `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `selected_benchmark_vs_lgbm_main_figure_not_full_result_set`. Tail side: `right_tail`. Run file: `latex/figures/selected_model_performance_right_tail.png`._

#### Figure 9. Full-Sample VaR Overlay Diagnostics

- Key readings: full-sample overlays show realized loss against a fixed benchmark-comparator VaR and the locked side-specific promoted ML-tail VaR.
- The benchmark line uses GJR-GARCH-EVT with GJR-GARCH-t fallback; the ML line is not selected by inspecting this plot.
- Treat the plot as a visual diagnostic. Formal validation remains the coverage, loss, DM/MCS, Murphy, and EVT evidence.

![full_sample_var_overlay_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/full_sample_var_overlay_left_tail.png)

_Figure: `full_sample_var_overlay_left_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `full_sample_var_overlay_fixed_selection_visual_diagnostic`. Tail side: `left_tail`. Run file: `latex/figures/full_sample_var_overlay_left_tail.png`._

![full_sample_var_overlay_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/full_sample_var_overlay_right_tail.png)

_Figure: `full_sample_var_overlay_right_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `full_sample_var_overlay_fixed_selection_visual_diagnostic`. Tail side: `right_tail`. Run file: `latex/figures/full_sample_var_overlay_right_tail.png`._

#### Figure 10. VaR/ES Stress-Window Overlays

- Supporting diagnostic: stress-window overlays illustrate threshold behavior around fixed windows.
- They do not report hedge PnL, transaction-cost evidence, or trading performance.

![var_es_stress_overlay_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/var_es_stress_overlay_left_tail.png)

_Figure: `var_es_stress_overlay_left_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `appendix_stress_overlay_illustration_not_validation`. Tail side: `left_tail`. Run file: `latex/figures/var_es_stress_overlay_left_tail.png`._

![var_es_stress_overlay_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/var_es_stress_overlay_right_tail.png)

_Figure: `var_es_stress_overlay_right_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `appendix_stress_overlay_illustration_not_validation`. Tail side: `right_tail`. Run file: `latex/figures/var_es_stress_overlay_right_tail.png`._

#### Figure 11. DM/MCS Heatmaps

- Supporting diagnostic: heatmap cells report one-sided DM p-values and candidate-minus-anchor loss differences.
- Negative loss differences favor the candidate; MCS markers indicate retained candidates where available.

![dm_mcs_heatmap_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/dm_mcs_heatmap_left_tail.png)

_Figure: `dm_mcs_heatmap_left_tail`. Source: `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet`. Claim scope: `appendix_dm_mcs_visual_diagnostic`. Tail side: `left_tail`. Run file: `latex/figures/dm_mcs_heatmap_left_tail.png`._

![dm_mcs_heatmap_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/dm_mcs_heatmap_right_tail.png)

_Figure: `dm_mcs_heatmap_right_tail`. Source: `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet`. Claim scope: `appendix_dm_mcs_visual_diagnostic`. Tail side: `right_tail`. Run file: `latex/figures/dm_mcs_heatmap_right_tail.png`._

#### Figure 12. Benchmark Murphy Diagnostics

- Key readings: curves report benchmark elementary-score diagnostics on a common grid.
- The plot is a scoring-family diagnostic, not a pairwise ranking statement.

![benchmark_murphy_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/benchmark_murphy_left_tail.png)

_Figure: `benchmark_murphy_left_tail`. Source: `metrics/benchmark_murphy.parquet`. Claim scope: `murphy_diagnostic_benchmark_baseline_common_grid`. Tail side: `left_tail`. Run file: `latex/figures/benchmark_murphy_left_tail.png`._

![benchmark_murphy_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/benchmark_murphy_right_tail.png)

_Figure: `benchmark_murphy_right_tail`. Source: `metrics/benchmark_murphy.parquet`. Claim scope: `murphy_diagnostic_benchmark_baseline_common_grid`. Tail side: `right_tail`. Run file: `latex/figures/benchmark_murphy_right_tail.png`._

#### Figure 13. ML-Tail Murphy Diagnostics

- Key readings: curves report the ML-tail nested information sets on a common grid.
- Interpret curve separation together with the primary ML coverage warning and unconditional inference gates.

![ml_tail_murphy_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_murphy_left_tail.png)

_Figure: `ml_tail_murphy_left_tail`. Source: `metrics/ml_tail_murphy.parquet`. Claim scope: `murphy_diagnostic_ml_tail_nested_information_sets_common_grid`. Tail side: `left_tail`. Run file: `latex/figures/ml_tail_murphy_left_tail.png`._

![ml_tail_murphy_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/ml_tail_murphy_right_tail.png)

_Figure: `ml_tail_murphy_right_tail`. Source: `metrics/ml_tail_murphy.parquet`. Claim scope: `murphy_diagnostic_ml_tail_nested_information_sets_common_grid`. Tail side: `right_tail`. Run file: `latex/figures/ml_tail_murphy_right_tail.png`._

#### Figure 14. ES Severity Diagnostics

- Key readings: bars report conditional-on-exception severity diagnostics.
- Severity is reported for risk interpretation but is not a standalone model-selection claim.

![es_severity_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/es_severity_left_tail.png)

_Figure: `es_severity_left_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `es_severity_diagnostic_not_model_selection_claim`. Tail side: `left_tail`. Run file: `latex/figures/es_severity_left_tail.png`._

![es_severity_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/es_severity_right_tail.png)

_Figure: `es_severity_right_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `es_severity_diagnostic_not_model_selection_claim`. Tail side: `right_tail`. Run file: `latex/figures/es_severity_right_tail.png`._

#### Figure 15. Selected Trigger Diagnostics

- Key readings: bars report pre-open VaR-trigger diagnostics for the same selected Benchmark-vs-LGBM candidates used in the compact performance figures.
- The trigger rule is within-model: `trigger = VaR forecast above that model's 75th-percentile VaR forecast` on the evaluation sample.
- This top-quartile rule is separate from the 95% VaR forecast target: VaR calibration is evaluated by breach rates, coverage tests, quantile loss, and FZ loss.
- Lower false-alarm and missed-exception rates are better; the trigger-rate bar is omitted because it is expected to be near 25% by construction.
- The trigger output is a monitoring diagnostic, not hedge PnL, not transaction-cost evidence, and not an execution-performance result.

![trigger_diagnostics_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/trigger_diagnostics_left_tail.png)

_Figure: `trigger_diagnostics_left_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `trigger_diagnostic_not_pnl_cost_or_alpha`. Tail side: `left_tail`. Run file: `latex/figures/trigger_diagnostics_left_tail.png`._

![trigger_diagnostics_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/trigger_diagnostics_right_tail.png)

_Figure: `trigger_diagnostics_right_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `trigger_diagnostic_not_pnl_cost_or_alpha`. Tail side: `right_tail`. Run file: `latex/figures/trigger_diagnostics_right_tail.png`._

#### Figure 16. EVT Standardized-Residual Diagnostics

- Key readings: figures show EVT diagnostics for LightGBM location-scale standardized residuals.
- QQ, log-survival, mean-excess, Hill, and threshold-stability diagnostics validate the POT-GPD tail assumption.
- These are assumption-validation diagnostics, not forecast-performance claims.

![evt_standardized_hill_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_hill_left_tail.png)

_Figure: `evt_standardized_hill_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_hill_left_tail.png`._

![evt_standardized_log_survival_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_log_survival_left_tail.png)

_Figure: `evt_standardized_log_survival_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_log_survival_left_tail.png`._

![evt_standardized_mean_excess_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_mean_excess_left_tail.png)

_Figure: `evt_standardized_mean_excess_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_mean_excess_left_tail.png`._

![evt_standardized_qq_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_qq_left_tail.png)

_Figure: `evt_standardized_qq_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_qq_left_tail.png`._

![evt_standardized_threshold_stability_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_threshold_stability_left_tail.png)

_Figure: `evt_standardized_threshold_stability_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_threshold_stability_left_tail.png`._

![evt_standardized_hill_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_hill_right_tail.png)

_Figure: `evt_standardized_hill_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_hill_right_tail.png`._

![evt_standardized_log_survival_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_log_survival_right_tail.png)

_Figure: `evt_standardized_log_survival_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_log_survival_right_tail.png`._

![evt_standardized_mean_excess_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_mean_excess_right_tail.png)

_Figure: `evt_standardized_mean_excess_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_mean_excess_right_tail.png`._

![evt_standardized_qq_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_qq_right_tail.png)

_Figure: `evt_standardized_qq_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_qq_right_tail.png`._

![evt_standardized_threshold_stability_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/evt_standardized_threshold_stability_right_tail.png)

_Figure: `evt_standardized_threshold_stability_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_threshold_stability_right_tail.png`._

#### Figure 17. DST Attenuation Diagnostics

- Supporting diagnostic: the left/right timing-regime patterns are not stable enough for a headline claim.
- Key readings: bars report loss gains from adding `JP + US close core` to `JP only`, split by EST/EDT timing regime.
- A positive gain means the expanded information set has lower average loss; a negative gain means it performs worse on that loss metric.
- This diagnostic is computed for the current primary nested-information-set anchor, `LGBM direct quantile`; it is not an average across all LightGBM/EVT variants or a model-selection exercise.
- Treat this as descriptive timing evidence; left/right patterns should not be assigned a shared structural mechanism.

![dst_attenuation_left_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/dst_attenuation_left_tail.png)

_Figure: `dst_attenuation_left_tail`. Source: `metrics/ml_tail_dst_attenuation.parquet`. Claim scope: `descriptive_dst_attenuation_not_structural_causal_identification`. Tail side: `left_tail`. Run file: `latex/figures/dst_attenuation_left_tail.png`._

![dst_attenuation_right_tail](figures/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/dst_attenuation_right_tail.png)

_Figure: `dst_attenuation_right_tail`. Source: `metrics/ml_tail_dst_attenuation.parquet`. Claim scope: `descriptive_dst_attenuation_not_structural_causal_identification`. Tail side: `right_tail`. Run file: `latex/figures/dst_attenuation_right_tail.png`._

### Source Artifact Index

| Artifact | Path | Exists |
| --- | --- | --- |
| manifest | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/manifest.json` | yes |
| data_vintage | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/data_vintage.json` | yes |
| modeling_panel | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/modeling_panel.parquet` | yes |
| target_audit | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/target_audit.parquet` | yes |
| calendar_map | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/calendar_map.parquet` | yes |
| feature_coverage | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/feature_coverage.parquet` | yes |
| leakage_summary | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/ls/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/summary.json` | yes |
| benchmark_status | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/benchmark_status.json` | yes |
| benchmark_metrics | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/benchmark_metrics.parquet` | yes |
| benchmark_metrics_per_model | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/benchmark_metrics_per_model.parquet` | yes |
| benchmark_forecasts | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/forecasts/benchmark_forecasts.parquet` | yes |
| benchmark_dm_inference | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/benchmark_dm_inference.parquet` | yes |
| benchmark_mcs | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/benchmark_mcs.parquet` | yes |
| ml_tail_status | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_status.json` | yes |
| ml_tail_metrics | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_metrics.parquet` | yes |
| ml_tail_metrics_per_model | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_metrics_per_model.parquet` | yes |
| ml_tail_forecasts | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/forecasts/ml_tail_forecasts.parquet` | yes |
| ml_tail_result_matrix | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_result_matrix.parquet` | yes |
| ml_tail_result_matrix_dm | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_result_matrix_dm.parquet` | yes |
| ml_tail_result_matrix_mcs | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_result_matrix_mcs.parquet` | yes |
| ml_tail_dm_inference | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_dm_inference.parquet` | yes |
| ml_tail_mcs | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_mcs.parquet` | yes |
| ml_tail_cpa_inference | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_cpa_inference.parquet` | yes |
| cross_model_cpa_inference | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/cross_model_cpa_inference.parquet` | yes |
| ml_tail_model_eviction | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_model_eviction.parquet` | yes |
| ml_tail_dst_attenuation | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_dst_attenuation.parquet` | yes |
| ml_tail_murphy | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_murphy.parquet` | yes |
| ml_tail_feature_unavailability | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_feature_unavailability.parquet` | yes |
| benchmark_stress_windows | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/benchmark_stress_windows.parquet` | yes |
| ml_tail_stress_windows | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/metrics/ml_tail_stress_windows.parquet` | yes |
| figure_manifest | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/figure_manifest.json` | yes |
| table_manifest | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/table_manifest.json` | yes |
| latex_dir | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/tables` | yes |
| claim_scope_table | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/tables/tailrisk_claim_scope_table.tex` | yes |
| es_severity_table | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/tables/tailrisk_es_severity_table.tex` | yes |
| hedge_trigger_table | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` | yes |
| dst_attenuation_table | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/tables/ml_tail_dst_attenuation_table.tex` | yes |
| result_matrix_summary_table | `reports/runs/tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa/latex/tables/ml_tail_result_matrix_summary_table.tex` | yes |

- All paths above are local ignored artifacts; they are reproducible outputs, not tracked source files.
- Forecast/reporting rebuilds should read these artifacts and must not call vendor APIs.
- If this page is stale, rerun `just snapshot` after a completed `just full` or pass an explicit run id to the CLI snapshot command.
