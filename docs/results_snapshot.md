---
hide:
  - navigation
---

# Results Snapshot

> **Research-candidate full-run artifact.** This page is generated from `tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e`.
> It summarizes the durable gold modeling sample and run outputs, not the older
> bounded access-check snapshot. It is still a research-candidate artifact:
> final manuscript claims require a clean committed run and author review of the
> tables and notes.

## Introduction

The framing questions have moved to [Discussion Q&A](discussion_qa.md). This snapshot is organized as a paper-facing evidence map: data and target construction first, model and evaluation design second, results third, and paper-facing exports and artifact provenance at the end.

The main result tables are in the Results section. Full table and figure provenance is collected in the Appendix section, including source artifacts and claim scopes for paper-facing outputs.

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

## Materials: Data And Target

### Run Metadata

| Field | Value |
| --- | --- |
| Run ID | `tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e` |
| Artifact root | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e` |
| Claim level | `research_candidate` |
| Requested window | `['2016-07-19', '2026-05-08']` |
| Combined clean start | `2018-06-20` |
| Gold panel dates | `2016-07-19 to 2026-05-01` |
| Forecast sample dates | `2018-06-20 to 2026-05-01 (1661 rows)` |
| Git commit | `2b473c4e177fb9776ba0710411bf990513cd701d` |
| Git dirty | `False` |
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
| Clean forecast observations | `1661` |
| Date range | `2018-06-20 to 2026-05-01` |
| Mean gap | 0.000522 log (+0.05%) |
| Standard deviation | 0.010649 log (+1.07%) |
| Skewness | -0.0336644 |
| Excess kurtosis | 13.1331 |
| 1% quantile | -0.028697 log (-2.83%) |
| 5% quantile | -0.014868 log (-1.48%) |
| Median | 0.000890 log (+0.09%) |
| 95% quantile | 0.014344 log (+1.44%) |
| 99% quantile | 0.027361 log (+2.77%) |
| Max drawdown gap | -0.087513 log (-8.38%) on `2020-03-13` |
| Max upside gap | 0.096937 log (+10.18%) on `2025-04-10` |
| Jarque-Bera p-value | 0 |
| Jarque-Bera statistic | 11972.7 |

#### Raw-Tail EVT Diagnostics

| Tail | Threshold probability | Threshold | Exceedances | Mean excess | GPD xi | GPD scale | Hill xi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| left_tail_loss | 0.900 | 0.0104713 | 166 | 0.00809322 | 0.204603 | 0.00641777 | 0.476705 |
| left_tail_loss | 0.925 | 0.0124096 | 125 | 0.00847607 | 0.234934 | 0.00648125 | 0.433857 |
| left_tail_loss | 0.950 | 0.0148675 | 83 | 0.00960529 | 0.212263 | 0.00755758 | 0.418714 |
| left_tail_loss | 0.975 | 0.0210536 | 42 | 0.0102367 | 0.446797 | 0.00607498 | 0.331429 |
| left_tail_loss | 0.990 | 0.0286967 | 17 | 0.0139643 | 0.284419 | 0.0101838 | 0.34578 |
| right_tail_loss | 0.900 | 0.0108676 | 166 | 0.00720714 | 0.346438 | 0.0047221 | 0.408732 |
| right_tail_loss | 0.925 | 0.0124484 | 125 | 0.00772818 | 0.426386 | 0.00457968 | 0.384777 |
| right_tail_loss | 0.950 | 0.0143435 | 83 | 0.00924099 | 0.42009 | 0.00558805 | 0.398242 |
| right_tail_loss | 0.975 | 0.0184656 | 42 | 0.0122865 | 0.407723 | 0.00773658 | 0.419593 |
| right_tail_loss | 0.990 | 0.0273614 | 17 | 0.0165888 | 0.191275 | 0.0135495 | 0.404539 |
| absolute_gap | 0.900 | 0.0146899 | 166 | 0.00934487 | 0.331036 | 0.0063527 | 0.402974 |
| absolute_gap | 0.925 | 0.016469 | 125 | 0.01035 | 0.304284 | 0.00729168 | 0.402961 |
| absolute_gap | 0.950 | 0.0196277 | 83 | 0.0116699 | 0.312179 | 0.00818106 | 0.387247 |
| absolute_gap | 0.975 | 0.0259904 | 42 | 0.0141731 | 0.297623 | 0.0102021 | 0.36961 |
| absolute_gap | 0.990 | 0.0363397 | 17 | 0.018341 | 0.213979 | 0.0147211 | 0.357836 |

- The GPD threshold table is computed on raw left loss, raw right loss, and the absolute gap; it should not be read as a forecast-model diagnostic.
- The Hill and GPD shape estimates are deliberately reported over multiple thresholds because tail-index estimates are sensitive in samples of this length.

#### Target Distribution Figures

| Figure | Tail side | Source | Claim scope | Docs file |
| --- | --- | --- | --- | --- |
| `target_gap_histogram_density` | `target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_gap_histogram_density.png` |
| `target_loss_qq_left_tail` | `left_tail` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_loss_qq_left_tail.png` |
| `target_loss_qq_right_tail` | `right_tail` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_loss_qq_right_tail.png` |
| `target_log_survival` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_log_survival.png` |
| `target_mean_excess` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_mean_excess.png` |
| `target_hill_plot` | `left_right_target_distribution` | `panel/modeling_panel.parquet` | `target_distribution_motivation_not_forecast_validation` | `figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_hill_plot.png` |

### Gold Panel Construction

| Measure | Value |
| --- | --- |
| Gold modeling rows | 2395 |
| Gold columns | 1588 |
| Target-audit rows | 2395 |
| Clean target rows | 2199 |
| Forecast-sample rows | 1661 |
| Rows before combined clean start | 412 |
| Target-not-clean rows | 196 |
| Mapping excluded rows | 126 |

| Target audit reason | Rows |
| --- | --- |
| None | 2199 |
| roll_sq_excluded | 195 |
| missing_reference_price | 1 |

- The cache lower bound is 2016-07-19, but XLC/core predictor coverage pushes the actual forecast sample to the combined clean start.
- Target exclusion is explicit: roll/SQ windows and the single missing reference price are carried as audit evidence, not silently dropped.
- The forecast-sample reason column makes the sample boundary reproducible row by row.

### Calendar And Timing Map

| Measure | Value |
| --- | --- |
| Normal trading mappings | 2268 |
| U.S./Japan desync mappings | 127 |
| NYSE early-close mappings | 32 |
| EDT rows | 1551 |
| EST rows | 844 |

- The map covers EST/EDT, early closes, U.S./Japan holiday desynchronization, and normal trading alignments.
- Desync rows are not treated as normal forecast rows.
- The timing map is part of the leakage-bound gold artifact, not ad hoc evaluation logic.

### Feature Coverage

| Source family | Block | Features | Mean missing | Max missing |
| --- | --- | --- | --- | --- |
| Asia proxy | Asia proxy | 10 | 0.000% | 0.000% |
| Asia proxy options | Asia proxy | 7 | 49.067% | 49.067% |
| cboe_volatility | fred_core | 2 | 0.000% | 0.000% |
| cross_market_derived | Asia proxy | 1 | 0.000% | 0.000% |
| cross_market_derived | fred_core | 2 | 0.000% | 0.000% |
| cross_market_derived | JP proxy | 2 | 0.000% | 0.000% |
| cross_market_derived | US core | 2 | 0.000% | 0.000% |
| event_calendar | calendar_controls | 7 | 0.000% | 0.000% |
| fred_core | fred_core | 9 | 0.000% | 0.000% |
| FRED credit enriched | FRED credit enriched | 4 | 62.041% | 62.071% |
| fx_core | fx_core | 2 | 0.000% | 0.000% |
| JP history | JP only | 37 | 0.000% | 0.000% |
| JP proxy | JP proxy | 8 | 0.000% | 0.000% |
| JP proxy options | JP proxy | 13 | 54.675% | 68.272% |
| J-Quants N225 options | JP only | 30 | 1.481% | 14.269% |
| massive_daily | US core | 40 | 0.002% | 0.060% |
| massive_minute | Asia proxy | 60 | 0.000% | 0.000% |
| massive_minute | JP proxy | 24 | 0.341% | 4.094% |
| massive_minute | US late session | 84 | 0.000% | 0.000% |
| massive_optional | massive_optional | 2 | 0.000% | 0.000% |
| unknown | unknown | 2 | 0.000% | 0.000% |
| US core options | US core | 21 | 49.067% | 49.067% |

- U.S. core, proxy ETFs, minute late-session features, CBOE VIX, FRED rates, FRED H.10 FX, and any audit-gated options-risk fields are separated by source family and block.
- Credit-spread FRED features are enriched/optional and visibly late-starting, so they do not move the core clean start.
- Feature coverage should be read together with the leakage summary; high coverage alone is not enough without timestamp validity.

### Leakage Audit

| Field | Value |
| --- | --- |
| Status | `pass_with_warnings` |
| Rows audited | `869385` |
| Failures | `0` |
| Warnings | `708149` |
| Panel row count | `2395` |
| Panel signature seed | `42` |
| Panel signature | `63ea2acb4baad92e9cb757fc661e47e8852e1f9b7ef78714a2a8eb564417da13` |

- Zero failures means no audited row violated the hard timestamp invariant.
- Warnings are retained because they identify conservative-lag or missing-feature situations that may matter for interpretation.
- The panel signature is deterministic and binds the leakage check to the current gold panel/config.

## Methods: Model Configuration And Evaluation

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

Status: `completed`; forecast rows: `21146`; metric rows: `12`; failures: `0`.

| Benchmark layer | Status | Forecast rows | Diagnostic rows | Failures | How to read it |
| --- | --- | --- | --- | --- | --- |
| baseline | `completed` | `7932` | `12` | `0` | Implemented evidence for target-history and econometric baseline benchmark models. |
| advanced econometric | `completed_nonblocking` | `13214` | `786` | `0` | Implemented nonblocking advanced econometric benchmark forecasts; review with common-sample gates. |

| Model | Information set | Tail side | Rows | VaR breach rate | Exceptions | Mean quantile loss | Mean FZ loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ewma_vol_scaled | Target history | left_tail | 661 | 5.295% | 35 | 0.00139273 | -3.65402 |
| ewma_vol_scaled | Target history | right_tail | 661 | 4.539% | 30 | 0.00131562 | -3.69642 |
| garch_t | Target history | left_tail | 661 | 6.354% | 42 | 0.00135048 | -3.70463 |
| garch_t | Target history | right_tail | 661 | 3.933% | 26 | 0.00122176 | -3.78739 |
| gjr_garch_evt | Target history | left_tail | 661 | 5.598% | 37 | 0.00133528 | -3.73239 |
| gjr_garch_evt | Target history | right_tail | 661 | 5.295% | 35 | 0.00117898 | -3.80163 |
| gjr_garch_t | Target history | left_tail | 661 | 6.505% | 43 | 0.0013401 | -3.7092 |
| gjr_garch_t | Target history | right_tail | 661 | 3.782% | 25 | 0.00117343 | -3.81523 |
| historical_quantile | Target history | left_tail | 661 | 6.051% | 40 | 0.00147767 | -3.5142 |
| historical_quantile | Target history | right_tail | 661 | 6.354% | 42 | 0.0014632 | -3.43894 |
| rolling_quantile | Target history | left_tail | 661 | 6.051% | 40 | 0.00147769 | -3.5066 |
| rolling_quantile | Target history | right_tail | 661 | 6.657% | 44 | 0.00147041 | -3.43407 |

- Baseline benchmark rows set the target-history/econometric reference that ML models should be interpreted against.
- Advanced econometric benchmark families are nonblocking; rows with valid forecasts are empirical evidence subject to the same sample and inference gates, while unavailable rows remain diagnostics.
- The table is not a leaderboard by itself; coverage, exception counts, quantile loss, and FZ loss must be read together.
- Common-sample rows are reported directly so readers can see the effective evidence size.

#### Primary ML Specifications

Status: `completed LGBM ML-tail models`; implemented models: `LGBM direct quantile`, `LGBM location-scale empirical`, `LGBM POT-GPD plain MLE`, `LGBM POT-GPD UniBM block-maxima shape`, `LGBM median/MAD POT-GPD plain MLE`, `LGBM median/MAD POT-GPD UniBM block-maxima shape`, `LGBM median/IQR POT-GPD plain MLE`, `LGBM median/IQR POT-GPD UniBM block-maxima shape`; forecast rows: `38544`; failures: `0`.

| Model | Information set | Tail side | Rows | VaR breach rate | Exceptions | Mean quantile loss | Mean FZ loss |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LGBM direct quantile | JP only | left_tail | 495 | 9.293% | 46 | 0.00142329 | -3.44237 |
| LGBM direct quantile | JP + US close core | left_tail | 495 | 10.303% | 51 | 0.00117044 | -3.6105 |
| LGBM direct quantile | JP + US close core + JP proxy | left_tail | 495 | 11.515% | 57 | 0.00116469 | -3.72689 |
| LGBM direct quantile | JP + US close core + JP proxy + Asia proxy | left_tail | 495 | 11.717% | 58 | 0.00115395 | -3.75666 |
| LGBM direct quantile | JP only | right_tail | 495 | 10.101% | 50 | 0.00126483 | -3.57732 |
| LGBM direct quantile | JP + US close core | right_tail | 495 | 11.717% | 58 | 0.00117494 | -3.57676 |
| LGBM direct quantile | JP + US close core + JP proxy | right_tail | 495 | 12.525% | 62 | 0.00115856 | -3.64983 |
| LGBM direct quantile | JP + US close core + JP proxy + Asia proxy | right_tail | 495 | 12.323% | 61 | 0.00117719 | -3.63373 |

- This primary ML table remains strict and reports only ML-tail rows that pass the registered common-sample and coverage gates.
- Location-scale empirical and plain POT-GPD are primary candidates only after their valid OOS coverage, standardized-loss, exceedance, and ES-validity gates pass.
- Differences across information blocks are candidate forecast evidence only after the common-sample, coverage, and inference diagnostics are reviewed.
- Coverage review: `8/8` primary ML rows differ from the expected breach rate by more than 2.5 percentage points, so quantile/FZ loss differences alone must not be read as forecast improvement.

#### Side-specific ML-tail Promotion Gate

| Role | Model | Information set | Tail side | Rows | Breach | Q loss | FZ loss | DM q | DM FZ | MCS q/FZ | Gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| left promoted | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | left_tail | 495 | 4.646% | 0.000877006 | -4.27411 | -0.000316309; p=0.005; reject10 | -0.590285; p=0.019; reject10 | in / in | pass |
| right promoted | LGBM location-scale empirical | JP + US close core + JP proxy | right_tail | 452 | 5.531% | 0.000995576 | -4.30874 | -0.00021776; p=0.034; reject10 | -0.748251; p=0.006; reject10 | in / in | pass |

- This paper-facing bridge promotes side-specific ML-tail candidates only after the N/coverage gate and restricted common-sample inference are visible.
- In the current run the left-tail promoted row is median/IQR POT-GPD, while the right-tail promoted row is location-scale empirical.
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
| benchmark_advanced | ald_taylor_var_es_asymmetric_slope | Target history | 2 | 661 +/- 0 | 5.825% +/- 0.107% | 0.825% +/- 0.107% | 0.00127576 +/- 8.04588e-05 | -3.7264 +/- 0.0333965 | 0.00869969 +/- 0.000405801 |
| benchmark_advanced | ald_taylor_var_es_sav | Target history | 2 | 661 +/- 0 | 5.522% +/- 0.535% | 0.522% +/- 0.535% | 0.00128271 +/- 3.8144e-05 | -3.73056 +/- 0.00716924 | 0.00886176 +/- 0.000129554 |
| benchmark_advanced | care_expectile_asymmetric_slope | Target history | 2 | 661 +/- 0 | 7.867% +/- 1.498% | 2.867% +/- 1.498% | 0.00127718 +/- 8.34e-05 | -3.70044 +/- 0.0127067 | 0.0073354 +/- 0.00110666 |
| benchmark_advanced | care_expectile_sav | Target history | 2 | 661 +/- 0 | 6.732% +/- 0.749% | 1.732% +/- 0.749% | 0.00129396 +/- 4.30045e-05 | -3.68574 +/- 0.0442191 | 0.00850544 +/- 0.000289762 |
| benchmark_advanced | caviar_asymmetric_slope | Target history | 2 | 658.5 +/- 0.707107 | 5.922% +/- 0.208% | 0.922% +/- 0.208% | 0.00127214 +/- 7.44272e-05 | -3.74253 +/- 0.0317651 | 0.00850709 +/- 0.000182887 |
| benchmark_advanced | caviar_sav | Target history | 2 | 660.5 +/- 0.707107 | 5.451% +/- 0.648% | 0.458% +/- 0.637% | 0.001287 +/- 4.0599e-05 | -3.7291 +/- 0.0043629 | 0.00935712 +/- 0.000659042 |
| benchmark_advanced | direct_fz_loss_asymmetric_slope | Target history | 2 | 661 +/- 0 | 5.825% +/- 0.107% | 0.825% +/- 0.107% | 0.00127576 +/- 8.04588e-05 | -3.7264 +/- 0.0333965 | 0.00869969 +/- 0.000405801 |
| benchmark_advanced | direct_fz_loss_sav | Target history | 2 | 661 +/- 0 | 5.522% +/- 0.535% | 0.522% +/- 0.535% | 0.00128271 +/- 3.8144e-05 | -3.73056 +/- 0.00716924 | 0.00886176 +/- 0.000129554 |
| benchmark_advanced | gas_t_location_scale | Target history | 2 | 661 +/- 0 | 5.522% +/- 1.391% | 0.983% +/- 0.738% | 0.00128515 +/- 5.79748e-05 | -3.73231 +/- 0.0419237 | 0.00939352 +/- 0.00130429 |
| benchmark_advanced | gas_t_pot_gpd | Target history | 2 | 661 +/- 0 | 5.446% +/- 0.000% | 0.446% +/- 0.000% | 0.00128952 +/- 4.66132e-05 | -3.74198 +/- 0.00836893 | 0.00945829 +/- 0.000793522 |
| benchmark_baseline | ewma_vol_scaled | Target history | 2 | 661 +/- 0 | 4.917% +/- 0.535% | 0.378% +/- 0.118% | 0.00135418 +/- 5.45215e-05 | -3.67522 +/- 0.0299802 | 0.00916441 +/- 0.000276157 |
| benchmark_baseline | garch_t | Target history | 2 | 661 +/- 0 | 5.144% +/- 1.712% | 1.210% +/- 0.203% | 0.00128612 +/- 9.10169e-05 | -3.74601 +/- 0.0585218 | 0.00955344 +/- 0.00130639 |
| benchmark_baseline | gjr_garch_evt | Target history | 2 | 661 +/- 0 | 5.446% +/- 0.214% | 0.446% +/- 0.214% | 0.00125713 +/- 0.000110519 | -3.76701 +/- 0.0489599 | 0.00888388 +/- 6.5351e-05 |
| benchmark_baseline | gjr_garch_t | Target history | 2 | 661 +/- 0 | 5.144% +/- 1.926% | 1.362% +/- 0.203% | 0.00125676 +/- 0.000117851 | -3.76221 +/- 0.0749739 | 0.00940623 +/- 0.00137493 |
| benchmark_baseline | historical_quantile | Target history | 2 | 661 +/- 0 | 6.203% +/- 0.214% | 1.203% +/- 0.214% | 0.00147044 +/- 1.02336e-05 | -3.47657 +/- 0.0532175 | 0.0122667 +/- 0.000676839 |
| benchmark_baseline | rolling_quantile | Target history | 2 | 661 +/- 0 | 6.354% +/- 0.428% | 1.354% +/- 0.428% | 0.00147405 +/- 5.15148e-06 | -3.47034 +/- 0.0512931 | 0.0120561 +/- 0.000415452 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP only | 2 | 426 +/- 0 | 4.930% +/- 0.664% | 0.469% +/- 0.100% | 0.00142322 +/- 6.19873e-05 | -3.53544 +/- 0.0779634 | 0.00923484 +/- 0.0015398 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP + US close core | 2 | 426 +/- 0 | 5.869% +/- 0.000% | 0.869% +/- 0.000% | 0.00107962 +/- 4.12874e-05 | -3.93795 +/- 0.176898 | 0.00709234 +/- 0.000372636 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy | 2 | 416 +/- 0 | 5.529% +/- 0.680% | 0.529% +/- 0.680% | 0.00100689 +/- 2.38279e-05 | -4.17888 +/- 0.14923 | 0.00730443 +/- 0.000684948 |
| ml_tail | LGBM POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy + Asia proxy | 2 | 416 +/- 0 | 5.409% +/- 1.190% | 0.841% +/- 0.578% | 0.00100391 +/- 3.64729e-05 | -4.20893 +/- 0.0169545 | 0.00736623 +/- 0.000770711 |
| ml_tail | LGBM POT-GPD plain MLE | JP only | 2 | 426 +/- 0 | 4.812% +/- 0.498% | 0.352% +/- 0.266% | 0.00142729 +/- 5.76747e-05 | -3.52832 +/- 0.0967262 | 0.0091695 +/- 0.00120523 |
| ml_tail | LGBM POT-GPD plain MLE | JP + US close core | 2 | 426 +/- 0 | 5.634% +/- 0.332% | 0.634% +/- 0.332% | 0.00108226 +/- 4.18835e-05 | -3.93657 +/- 0.175119 | 0.00731769 +/- 2.89668e-05 |
| ml_tail | LGBM POT-GPD plain MLE | JP + US close core + JP proxy | 2 | 416 +/- 0 | 5.409% +/- 0.510% | 0.409% +/- 0.510% | 0.0010067 +/- 2.43187e-05 | -4.21871 +/- 0.0703156 | 0.00729024 +/- 0.000445848 |
| ml_tail | LGBM POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | 2 | 416 +/- 0 | 5.288% +/- 1.020% | 0.721% +/- 0.408% | 0.00100421 +/- 4.02046e-05 | -4.11451 +/- 0.135809 | 0.00736978 +/- 0.000358334 |
| ml_tail | LGBM direct quantile | JP only | 2 | 516 +/- 0 | 9.496% +/- 0.548% | 4.496% +/- 0.548% | 0.00132934 +/- 0.000130656 | -3.51693 +/- 0.129817 | 0.00739887 +/- 0.00116877 |
| ml_tail | LGBM direct quantile | JP + US close core | 2 | 516 +/- 0 | 10.659% +/- 0.822% | 5.659% +/- 0.822% | 0.00115725 +/- 2.00728e-05 | -3.61469 +/- 0.0203174 | 0.00667106 +/- 0.000689168 |
| ml_tail | LGBM direct quantile | JP + US close core + JP proxy | 2 | 495 +/- 0 | 12.020% +/- 0.714% | 7.020% +/- 0.714% | 0.00116163 +/- 4.33578e-06 | -3.68836 +/- 0.0544907 | 0.00601208 +/- 0.000423924 |
| ml_tail | LGBM direct quantile | JP + US close core + JP proxy + Asia proxy | 2 | 495 +/- 0 | 12.020% +/- 0.429% | 7.020% +/- 0.429% | 0.00116557 +/- 1.64324e-05 | -3.6952 +/- 0.0869245 | 0.00599574 +/- 0.000147116 |
| ml_tail | LGBM location-scale empirical | JP only | 2 | 462 +/- 0 | 4.437% +/- 0.765% | 0.563% +/- 0.765% | 0.00137828 +/- 5.64626e-05 | -3.5718 +/- 0.0832536 | 0.00959949 +/- 0.00162364 |
| ml_tail | LGBM location-scale empirical | JP + US close core | 2 | 462 +/- 0 | 5.411% +/- 0.306% | 0.411% +/- 0.306% | 0.00104582 +/- 5.14417e-05 | -4.04021 +/- 0.0887163 | 0.00725437 +/- 9.25385e-06 |
| ml_tail | LGBM location-scale empirical | JP + US close core + JP proxy | 2 | 452 +/- 0 | 5.531% +/- 0.000% | 0.531% +/- 0.000% | 0.000973591 +/- 3.10915e-05 | -4.30732 +/- 0.00200193 | 0.00672751 +/- 0.000211495 |
| ml_tail | LGBM location-scale empirical | JP + US close core + JP proxy + Asia proxy | 2 | 452 +/- 0 | 5.199% +/- 0.782% | 0.553% +/- 0.282% | 0.000962933 +/- 4.62441e-05 | -4.16974 +/- 0.130829 | 0.00691636 +/- 7.19081e-06 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP only | 2 | 516 +/- 0 | 3.973% +/- 0.685% | 1.027% +/- 0.685% | 0.0012686 +/- 0.000150459 | -3.76409 +/- 0.125039 | 0.0104619 +/- 0.00290007 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP + US close core | 2 | 516 +/- 0 | 5.136% +/- 0.411% | 0.291% +/- 0.192% | 0.00101073 +/- 4.2221e-05 | -4.03529 +/- 0.119595 | 0.00800925 +/- 1.92251e-05 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy | 2 | 495 +/- 0 | 5.556% +/- 0.143% | 0.556% +/- 0.143% | 0.000930474 +/- 2.32341e-05 | -4.12385 +/- 0.0660107 | 0.00646086 +/- 1.15773e-06 |
| ml_tail | LGBM median/IQR POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy + Asia proxy | 2 | 495 +/- 0 | 5.253% +/- 0.286% | 0.253% +/- 0.286% | 0.000922889 +/- 6.29039e-05 | -4.13973 +/- 0.202322 | 0.00638644 +/- 0.000326663 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP only | 2 | 516 +/- 0 | 3.682% +/- 0.274% | 1.318% +/- 0.274% | 0.00126704 +/- 0.000143917 | -3.75891 +/- 0.119927 | 0.0109748 +/- 0.00266665 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP + US close core | 2 | 516 +/- 0 | 4.845% +/- 0.000% | 0.155% +/- 0.000% | 0.0010105 +/- 4.76974e-05 | -4.03352 +/- 0.117195 | 0.00826553 +/- 0.000681949 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy | 2 | 495 +/- 0 | 5.051% +/- 0.571% | 0.404% +/- 0.071% | 0.000928873 +/- 2.29852e-05 | -4.13562 +/- 0.064733 | 0.00701335 +/- 0.000915113 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | 2 | 495 +/- 0 | 5.051% +/- 0.571% | 0.404% +/- 0.071% | 0.000921648 +/- 6.31333e-05 | -4.12943 +/- 0.204612 | 0.00646357 +/- 2.19199e-05 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP only | 2 | 426 +/- 0 | 5.751% +/- 1.162% | 0.822% +/- 1.062% | 0.00136414 +/- 0.000186208 | -3.68534 +/- 0.141874 | 0.00940542 +/- 0.00331666 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP + US close core | 2 | 426 +/- 0 | 7.042% +/- 0.664% | 2.042% +/- 0.664% | 0.00111737 +/- 3.02008e-05 | -4.0321 +/- 0.0522886 | 0.00828091 +/- 0.00141668 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy | 2 | 416 +/- 0 | 6.971% +/- 1.700% | 1.971% +/- 1.700% | 0.00103539 +/- 4.11815e-05 | -4.19106 +/- 0.120658 | 0.00752165 +/- 0.00114041 |
| ml_tail | LGBM median/MAD POT-GPD UniBM block-maxima shape | JP + US close core + JP proxy + Asia proxy | 2 | 416 +/- 0 | 6.851% +/- 0.850% | 1.851% +/- 0.850% | 0.00104855 +/- 4.76867e-05 | -4.14044 +/- 0.0865602 | 0.00774411 +/- 0.000297524 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP only | 2 | 426 +/- 0 | 5.516% +/- 0.830% | 0.587% +/- 0.730% | 0.00136404 +/- 0.000194626 | -3.68214 +/- 0.140278 | 0.00936482 +/- 0.0032345 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP + US close core | 2 | 426 +/- 0 | 7.160% +/- 0.498% | 2.160% +/- 0.498% | 0.00111367 +/- 2.65088e-05 | -4.03557 +/- 0.0600049 | 0.00799174 +/- 0.00116166 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP + US close core + JP proxy | 2 | 416 +/- 0 | 6.971% +/- 1.700% | 1.971% +/- 1.700% | 0.0010351 +/- 4.57607e-05 | -4.1789 +/- 0.135315 | 0.00747101 +/- 0.00097698 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | 2 | 416 +/- 0 | 6.971% +/- 1.020% | 1.971% +/- 1.020% | 0.00104617 +/- 5.10335e-05 | -4.14228 +/- 0.0941646 | 0.00750515 +/- 0.000292362 |

- This table joins `benchmark_metrics_per_model.parquet` and `ml_tail_metrics_per_model.parquet` so all benchmark and LGBM tail-model variants are visible in one place.
- Mean and standard deviation are computed across registered metric rows for the same suite/model/information-set configuration; for most rows this summarizes left- and right-tail metrics.
- It is a diagnostic scan, not the formal cross-model comparison table. Cross-model claims still require common-sample result-matrix, DM, and MCS evidence because valid dates and model gates can differ.

#### Restricted Common-Sample Result Matrix

| Family | Axis | Loss | Rows | Common N | Date range | Joint exceptions |
| --- | --- | --- | --- | --- | --- | --- |
| nested information sets | information_set_increment | var_coverage | 64 | 416 to 495 | 2023-03-24 to 2026-05-01 | 38 to 79 |
| nested information sets | information_set_increment | var_es_fz_loss | 64 | 416 to 495 | 2023-03-24 to 2026-05-01 | 38 to 79 |
| nested information sets | information_set_increment | var_quantile_loss | 64 | 416 to 495 | 2023-03-24 to 2026-05-01 | 38 to 79 |
| tail_model_family | model_family | var_coverage | 64 | 416 to 426 | 2023-09-14 to 2026-05-01 | 45 to 61 |
| tail_model_family | model_family | var_es_fz_loss | 64 | 416 to 426 | 2023-09-14 to 2026-05-01 | 45 to 61 |
| tail_model_family | model_family | var_quantile_loss | 64 | 416 to 426 | 2023-09-14 to 2026-05-01 | 45 to 61 |

- The result matrix is the right place to compare direct quantile, location-scale empirical, plain POT-GPD, and the robust plain POT-GPD routes on their restricted common dates.
- It separates VaR-only losses from VaR-ES joint scoring, so VaR-only claims are not confused with ES claims.
- Restricted direct-quantile performance is only a comparison anchor for the tail-model family; it does not replace the primary direct-quantile evidence.
- DM and MCS records are emitted only where registered row-count and exception-count gates pass; otherwise the result matrix remains descriptive.

#### Stress And Diagnostic Windows

| Suite | Rows | Window labels |
| --- | --- | --- |
| benchmark | 134 | `loss_top_decile` |
| ml_tail | 200 | `loss_top_decile`, `vix_top_decile` |

- Stress windows identify high-loss or high-volatility subsamples for two-sided risk diagnostics.
- These rows use reproducible full-sample classifiers in this first pass, so they should be described as diagnostics rather than a live stress classifier.
- They are useful for finding whether model behavior changes in difficult regimes before writing manuscript discussion.

### Results interpretation and claim boundaries

<!-- generated: results_discussion -->

#### Data and timing audit

- The gold timing map covers `2016-07-19 to 2026-05-01` and the combined clean start is `2018-06-20`.
- No forecast-sample rows before `2018-06-20` enter the modeling evidence.
- The leakage check reports status `pass_with_warnings` with zero leakage failures and `708149` warnings.
- FRED vintage safety is recorded as `False`; FRED values use conservative release timing but remain current historical observations rather than ALFRED real-time vintages.

#### Baseline benchmarks and advanced econometric benchmarks

- `benchmark_metrics.parquet` reports `12` common-sample rows across `6` baseline benchmark model families and `2` tail side(s), while benchmark forecasts contain `21146` model-date rows.
- Baseline benchmark models are external target-history and econometric references; this section does not rank them.
- Advanced econometric benchmark rows are implemented for `10` model families and contribute `13214` nonblocking forecast rows; these rows are claim-gated diagnostics unless a manuscript table explicitly promotes them through the same sample and inference review.
- Baseline benchmark breach rates have a median of `0.0605144`, within 2.5 percentage points of the nominal level, indicating reasonable coverage calibration relative to the ML-tail models whose breach rates are reported in the nested-information-set section.

#### Primary ML specifications across nested information sets

- `ml_tail_metrics.parquet` defines the primary ML specification comparison across nested information sets for this run.
- The primary ML artifact contains `4` information sets, `1` tail level(s), and `2` tail side(s); the retained primary ML rows are `LGBM direct quantile`.
- The implemented ML-tail registry is `LGBM direct quantile`, `LGBM location-scale empirical`, `LGBM POT-GPD plain MLE`, `LGBM POT-GPD UniBM block-maxima shape`, `LGBM median/MAD POT-GPD plain MLE`, `LGBM median/MAD POT-GPD UniBM block-maxima shape`, `LGBM median/IQR POT-GPD plain MLE`, `LGBM median/IQR POT-GPD UniBM block-maxima shape`, but the primary nested-information-set comparison should be read only from `ml_tail_metrics.parquet`.
- The nested information sets report downside-risk and upside-risk surfaces separately. The registered artifacts show different left/right patterns, and the generator does not assume that the two sides share the same economic mechanism.
- Coverage warning: all `8` primary ML rows exhibit VaR breach rates (`0.0929293` to `0.125253`) that exceed the nominal level by more than 2.5 percentage points. Quantile-loss and FZ-loss differences across the nested information sets must be interpreted in this context; lower loss scores may partly reflect less conservative VaR estimates rather than better conditional tail calibration.
- On `left_tail`, `right_tail`, the largest quantile-loss change occurs at the first information-set augmentation (adding U.S. close core); subsequent additions of Japan proxy and Asia proxy ETFs contribute diminishing incremental loss changes. This saturation pattern is descriptive and does not automatically reduce the value of the broader information set.
- The nested information sets are used to assess candidate incremental U.S.-close information under strict common-sample rules; they do not by themselves establish forecast improvement.

#### Restricted model-family comparison

- `ml_tail_result_matrix.parquet` contains restricted common-sample comparisons for `8` LightGBM tail-model families.
- The restricted common-N range is `416 to 495` and the joint-exception range is `38 to 79`.
- Recorded claim scopes are `restricted_model_comparison_not_primary`; these rows are restricted evidence and cannot replace the primary ML nested-information-set comparison.
- The tail-model family comparison is severely sample-limited: the largest restricted common-N is `426` rows. No model-family ranking claim is supportable from this restricted sample; extended OOS coverage is needed before tail-model family ranking becomes meaningful.
- Result-matrix inference is recorded separately from the primary suite-level DM/MCS: restricted DM records include `208` gate-pass rows and `104` unavailable rows; restricted MCS records include `128` gate-pass rows and `64` unavailable rows. These entries are restricted common-sample diagnostics, not primary model-family rankings.
- The result matrix is a matched-date diagnostic layer. It should not be worded as one family being better than another.

#### Coverage and inference gates

- Coverage review flags `8/8` primary ML rows with breach rates more than 2.5 percentage points from nominal coverage; Kupiec p-values fall below 0.05 in `8/8` rows and Christoffersen p-values fall below 0.05 in `0/8` rows where reported.
- Model-eviction artifacts record `8` retained rows and `56` non-retained rows under the primary ML sample policy.
- Block-bootstrap DM and HLN Tmax MCS artifacts are unconditional forecast-comparison diagnostics; any p-value should be read on average across the unconditional evaluation sample, not as condition-specific evidence.
- Loss differentials alone do not constitute an improvement claim; coverage, exception counts, sample gates, and inference status must be reviewed together.
- Result-matrix tail-event power flags and suite-level inference gates report `0` restricted rows with insufficient tail-event power and `0/36` unavailable DM/MCS inference rows.

#### CPA as conditional loss-difference diagnostics

- The ML-tail nested-information-set CPA artifact is a conditional loss-difference diagnostic across `2` tail side(s), with `24` registered row(s), `24` HAC-Wald gate pass(es), and loss families `var_es_fz_loss`, `var_quantile_loss`.
- The registered cross-model CPA artifact is a conditional loss-difference diagnostic with `368` row(s), `368` HAC-Wald gate pass(es), and loss families `var_es_fz_loss`, `var_quantile_loss`.
- Quantile-loss CPA and FZ-loss CPA are downstream inference over existing loss differentials; CPA does not generate VaR/ES forecasts and does not replace DM/MCS.

#### Supporting diagnostics

- Supporting LaTeX diagnostic table files are present for `4/4` registered diagnostic families.
- `ml_tail_dst_attenuation.parquet` contains `6` DST attenuation rows; these are descriptive timing-regime forecast diagnostics. They do not establish a structural timing mechanism.
- ES severity diagnostics contain `84` finite rows with mean exceedance severity ranging from `0.00571232` to `0.0128604`; this is conditional-on-exception evidence.
- The diagnostic 75th-percentile VaR trigger rule marks `12733` model-date rows; `908` of those rows coincide with VaR exceptions out of `3059` total exceptions, and mean triggered exception severity is `0.0133166`. This is a pre-open risk-monitoring diagnostic, not hedge PnL, transaction-cost, or trading-alpha evidence.
- Stress-window diagnostics contain `334` rows, and Murphy diagnostics contain `1600` ML-tail rows.
- Feature-unavailability diagnostics contain `384` rows.
- Figure manifest references:
  - Figure: coverage_breach_rates_left_tail (Source: metrics/benchmark_metrics.parquet, metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: coverage_diagnostic_not_primary_claim; File: latex/figures/coverage_breach_rates_left_tail.png).
  - Figure: coverage_breach_rates_right_tail (Source: metrics/benchmark_metrics.parquet, metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: coverage_diagnostic_not_primary_claim; File: latex/figures/coverage_breach_rates_right_tail.png).
  - Figure: selected_model_performance_left_tail (Source: metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: selected_benchmark_vs_lgbm_main_figure_not_full_result_set; File: latex/figures/selected_model_performance_left_tail.png).
  - Figure: selected_model_performance_right_tail (Source: metrics/benchmark_metrics_per_model.parquet, metrics/ml_tail_metrics_per_model.parquet; Claim scope: selected_benchmark_vs_lgbm_main_figure_not_full_result_set; File: latex/figures/selected_model_performance_right_tail.png).
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

## Appendix: Tables, Figures, And Run Artifacts

The appendix collects generated exports and provenance. The main Results section refers back to these files when a table or figure is suitable for manuscript use.

### Paper-Facing Table And Figure Gallery

#### Appendix Configuration Robustness

| Field | Value |
| --- | --- |
| Source primary run | `tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e` |
| Primary-claim allowed | `False` |
| Forecast rows | `129766` |
| Metric rows | `264` |
| Status | `ok` |

| Sensitivity family | Rows / classifications |
| --- | --- |
| LGBM capacity | 108 rows (mixed=20, robust=78, sensitive=10) |
| EWMA lambda | 6 rows (robust=6) |
| POT threshold | 150 rows (boundary_diagnostic=50, mixed=3, robust=97) |

- The primary design compares pre-specified point-in-time forecast specifications. Configuration sensitivity is appendix robustness evidence and is not used to select primary selections.
- LGBM rows vary only capacity settings; EWMA reports the primary lambda 0.94 plus 0.90 and 0.97; POT threshold rows use forecastable 0.90/0.925 settings and mark 0.95 as a boundary diagnostic at the 95% VaR level.
- Robustness classes describe conclusion stability versus the registered primary specification. They do not feed DM/MCS gates, promoted-model logic, or selected-model figures.

#### Table Manifest

| Table | Source artifacts | Claim scope | Tail side | File |
| --- | --- | --- | --- | --- |
| benchmark_metrics | `metrics/benchmark_metrics.parquet` | `benchmark_common_sample_metric_table` | `None` | `latex/tables/benchmark_metrics_table.tex` |
| benchmark_left_tail_risk | `metrics/benchmark_metrics.parquet` | `left_tail_benchmark_risk_table` | `left_tail` | `latex/tables/benchmark_left_tail_risk_table.tex` |
| benchmark_right_tail_risk | `metrics/benchmark_metrics.parquet` | `right_tail_benchmark_risk_table` | `right_tail` | `latex/tables/benchmark_right_tail_risk_table.tex` |
| ml_tail_metrics | `metrics/ml_tail_metrics.parquet` | `ml_tail_nested_information_set_table` | `None` | `latex/tables/ml_tail_metrics_table.tex` |
| ml_tail_left_tail_risk | `metrics/ml_tail_metrics.parquet` | `left_tail_ml_tail_primary_risk_table` | `left_tail` | `latex/tables/ml_tail_left_tail_risk_table.tex` |
| ml_tail_right_tail_risk | `metrics/ml_tail_metrics.parquet` | `right_tail_ml_tail_primary_risk_table` | `right_tail` | `latex/tables/ml_tail_right_tail_risk_table.tex` |
| tailrisk_selected_model_performance | `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet` | `selected_benchmark_vs_lgbm_main_figure_rows` | `None` | `latex/tables/tailrisk_selected_model_performance_table.tex` |
| appendix_benchmark_all_models | `metrics/benchmark_metrics_per_model.parquet` | `appendix_full_benchmark_results` | `None` | `latex/tables/appendix_benchmark_all_models_table.tex` |
| ml_tail_promoted_tail_models | `metrics/ml_tail_metrics_per_model.parquet`, `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet` | `side_specific_ml_tail_promotion_gate` | `None` | `latex/tables/ml_tail_promoted_tail_models_table.tex` |
| appendix_lgbm_all_models | `metrics/ml_tail_metrics_per_model.parquet` | `appendix_full_lgbm_results` | `None` | `latex/tables/appendix_lgbm_all_models_table.tex` |
| tailrisk_es_severity | `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet` | `es_severity_diagnostic_table` | `None` | `latex/tables/tailrisk_es_severity_table.tex` |
| tailrisk_trigger_diagnostics | `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet` | `trigger_diagnostic_table` | `None` | `latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` |
| tailrisk_claim_scope | `manifest.json`, `config/research_config.json` | `claim_boundary_reference_table` | `None` | `latex/tables/tailrisk_claim_scope_table.tex` |
| ml_tail_result_matrix | `metrics/ml_tail_result_matrix.parquet` | `restricted_model_comparison_table` | `None` | `latex/tables/ml_tail_result_matrix_table.tex` |
| ml_tail_result_matrix_summary | `metrics/ml_tail_result_matrix.parquet`, `metrics/ml_tail_result_matrix_dm.parquet`, `metrics/ml_tail_result_matrix_mcs.parquet` | `restricted_result_matrix_summary_table` | `None` | `latex/tables/ml_tail_result_matrix_summary_table.tex` |
| ml_tail_dst_attenuation | `metrics/ml_tail_dst_attenuation.parquet` | `descriptive_dst_attenuation_table` | `None` | `latex/tables/ml_tail_dst_attenuation_table.tex` |
| appendix_lgbm_configuration_sensitivity | `sensitivity/metrics/lgbm_configuration_sensitivity_metrics.parquet` | `appendix_configuration_robustness_lgbm` | `None` | `sensitivity/latex/tables/appendix_lgbm_configuration_sensitivity_table.tex` |
| appendix_benchmark_configuration_sensitivity | `sensitivity/metrics/benchmark_configuration_sensitivity_metrics.parquet` | `appendix_configuration_robustness_benchmark` | `None` | `sensitivity/latex/tables/appendix_benchmark_configuration_sensitivity_table.tex` |
| appendix_evt_threshold_sensitivity | `sensitivity/metrics/evt_threshold_sensitivity_metrics.parquet` | `appendix_configuration_robustness_evt_threshold` | `None` | `sensitivity/latex/tables/appendix_evt_threshold_sensitivity_table.tex` |

- The table manifest records the generated LaTeX table files, their source artifacts, and their claim scopes.
- Tables are paper-facing exports; the Markdown tables above are snapshot summaries for browser review.

#### Figure 1. Target Distribution And Tail Diagnostics

- Key readings: these figures describe the raw settlement-to-open gap and the left/right loss tails.
- They motivate VaR/ES and POT-GPD modeling, but they do not validate LightGBM+EVT forecasts.

![target_gap_histogram_density](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_gap_histogram_density.png)

_Figure: `target_gap_histogram_density`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `target_distribution`. Run file: `latex/figures/target_gap_histogram_density.png`._

![target_loss_qq_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_loss_qq_left_tail.png)

_Figure: `target_loss_qq_left_tail`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_tail`. Run file: `latex/figures/target_loss_qq_left_tail.png`._

![target_loss_qq_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_loss_qq_right_tail.png)

_Figure: `target_loss_qq_right_tail`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `right_tail`. Run file: `latex/figures/target_loss_qq_right_tail.png`._

![target_log_survival](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_log_survival.png)

_Figure: `target_log_survival`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_log_survival.png`._

![target_mean_excess](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_mean_excess.png)

_Figure: `target_mean_excess`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_mean_excess.png`._

![target_hill_plot](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_hill_plot.png)

_Figure: `target_hill_plot`. Source: `panel/modeling_panel.parquet`. Claim scope: `target_distribution_motivation_not_forecast_validation`. Tail side: `left_right_target_distribution`. Run file: `latex/figures/target_hill_plot.png`._

#### Figure 2. Coverage Breach-Rate Diagnostics

- Key readings: bars report realized VaR exception rates against the nominal line.
- Read this first: exception-rate deviations set the boundary for any loss-based interpretation.

![coverage_breach_rates_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/coverage_breach_rates_left_tail.png)

_Figure: `coverage_breach_rates_left_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `coverage_diagnostic_not_primary_claim`. Tail side: `left_tail`. Run file: `latex/figures/coverage_breach_rates_left_tail.png`._

![coverage_breach_rates_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/coverage_breach_rates_right_tail.png)

_Figure: `coverage_breach_rates_right_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `coverage_diagnostic_not_primary_claim`. Tail side: `right_tail`. Run file: `latex/figures/coverage_breach_rates_right_tail.png`._

#### Figure 3. Selected Benchmark-vs-LGBM Performance

- Key readings: compact main-figure rows split models into two broad groups, Benchmark and LGBM.
- Within each tail and group, rows are selected by sufficient sample size, VaR coverage near 5%, then lower FZ loss and quantile loss.
- Full benchmark and LGBM per-model results are exported in appendix tables, so this figure is a readable summary rather than the full result set.

![selected_model_performance_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/selected_model_performance_left_tail.png)

_Figure: `selected_model_performance_left_tail`. Source: `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `selected_benchmark_vs_lgbm_main_figure_not_full_result_set`. Tail side: `left_tail`. Run file: `latex/figures/selected_model_performance_left_tail.png`._

![selected_model_performance_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/selected_model_performance_right_tail.png)

_Figure: `selected_model_performance_right_tail`. Source: `metrics/benchmark_metrics_per_model.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `selected_benchmark_vs_lgbm_main_figure_not_full_result_set`. Tail side: `right_tail`. Run file: `latex/figures/selected_model_performance_right_tail.png`._

#### Figure 4. Benchmark Murphy Diagnostics

- Key readings: curves report benchmark elementary-score diagnostics on a common grid.
- The plot is a scoring-family diagnostic, not a pairwise ranking statement.

![benchmark_murphy_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/benchmark_murphy_left_tail.png)

_Figure: `benchmark_murphy_left_tail`. Source: `metrics/benchmark_murphy.parquet`. Claim scope: `murphy_diagnostic_benchmark_baseline_common_grid`. Tail side: `left_tail`. Run file: `latex/figures/benchmark_murphy_left_tail.png`._

![benchmark_murphy_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/benchmark_murphy_right_tail.png)

_Figure: `benchmark_murphy_right_tail`. Source: `metrics/benchmark_murphy.parquet`. Claim scope: `murphy_diagnostic_benchmark_baseline_common_grid`. Tail side: `right_tail`. Run file: `latex/figures/benchmark_murphy_right_tail.png`._

#### Figure 5. ML-Tail Murphy Diagnostics

- Key readings: curves report the ML-tail nested information sets on a common grid.
- Interpret curve separation together with the primary ML coverage warning and unconditional inference gates.

![ml_tail_murphy_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/ml_tail_murphy_left_tail.png)

_Figure: `ml_tail_murphy_left_tail`. Source: `metrics/ml_tail_murphy.parquet`. Claim scope: `murphy_diagnostic_ml_tail_nested_information_sets_common_grid`. Tail side: `left_tail`. Run file: `latex/figures/ml_tail_murphy_left_tail.png`._

![ml_tail_murphy_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/ml_tail_murphy_right_tail.png)

_Figure: `ml_tail_murphy_right_tail`. Source: `metrics/ml_tail_murphy.parquet`. Claim scope: `murphy_diagnostic_ml_tail_nested_information_sets_common_grid`. Tail side: `right_tail`. Run file: `latex/figures/ml_tail_murphy_right_tail.png`._

#### Figure 6. ES Severity Diagnostics

- Key readings: bars report conditional-on-exception severity diagnostics.
- Severity is reported for risk interpretation but is not a standalone model-selection claim.

![es_severity_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/es_severity_left_tail.png)

_Figure: `es_severity_left_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `es_severity_diagnostic_not_model_selection_claim`. Tail side: `left_tail`. Run file: `latex/figures/es_severity_left_tail.png`._

![es_severity_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/es_severity_right_tail.png)

_Figure: `es_severity_right_tail`. Source: `metrics/benchmark_metrics.parquet`, `metrics/ml_tail_metrics.parquet`, `metrics/ml_tail_metrics_per_model.parquet`. Claim scope: `es_severity_diagnostic_not_model_selection_claim`. Tail side: `right_tail`. Run file: `latex/figures/es_severity_right_tail.png`._

#### Figure 7. Selected Trigger Diagnostics

- Key readings: bars report pre-open VaR-trigger diagnostics for the same selected Benchmark-vs-LGBM candidates used in the compact performance figures.
- The trigger rule is within-model: `trigger = VaR forecast above that model's 75th-percentile VaR forecast` on the evaluation sample.
- This top-quartile rule is separate from the 95% VaR forecast target: VaR calibration is evaluated by breach rates, coverage tests, quantile loss, and FZ loss.
- Lower false-alarm and missed-exception rates are better; the trigger-rate bar is omitted because it is expected to be near 25% by construction.
- The trigger output is a monitoring diagnostic, not hedge PnL, not transaction-cost evidence, and not an execution-performance result.

![trigger_diagnostics_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/trigger_diagnostics_left_tail.png)

_Figure: `trigger_diagnostics_left_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `trigger_diagnostic_not_pnl_cost_or_alpha`. Tail side: `left_tail`. Run file: `latex/figures/trigger_diagnostics_left_tail.png`._

![trigger_diagnostics_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/trigger_diagnostics_right_tail.png)

_Figure: `trigger_diagnostics_right_tail`. Source: `forecasts/benchmark_forecasts.parquet`, `forecasts/ml_tail_forecasts.parquet`. Claim scope: `trigger_diagnostic_not_pnl_cost_or_alpha`. Tail side: `right_tail`. Run file: `latex/figures/trigger_diagnostics_right_tail.png`._

#### Figure 8. EVT Standardized-Residual Diagnostics

- Key readings: figures show EVT diagnostics for LightGBM location-scale standardized residuals.
- QQ, log-survival, mean-excess, Hill, and threshold-stability diagnostics validate the POT-GPD tail assumption.
- These are assumption-validation diagnostics, not forecast-performance claims.

![evt_standardized_hill_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_hill_left_tail.png)

_Figure: `evt_standardized_hill_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_hill_left_tail.png`._

![evt_standardized_log_survival_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_log_survival_left_tail.png)

_Figure: `evt_standardized_log_survival_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_log_survival_left_tail.png`._

![evt_standardized_mean_excess_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_mean_excess_left_tail.png)

_Figure: `evt_standardized_mean_excess_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_mean_excess_left_tail.png`._

![evt_standardized_qq_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_qq_left_tail.png)

_Figure: `evt_standardized_qq_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_qq_left_tail.png`._

![evt_standardized_threshold_stability_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_threshold_stability_left_tail.png)

_Figure: `evt_standardized_threshold_stability_left_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `left_tail`. Run file: `latex/figures/evt_standardized_threshold_stability_left_tail.png`._

![evt_standardized_hill_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_hill_right_tail.png)

_Figure: `evt_standardized_hill_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_hill_right_tail.png`._

![evt_standardized_log_survival_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_log_survival_right_tail.png)

_Figure: `evt_standardized_log_survival_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_log_survival_right_tail.png`._

![evt_standardized_mean_excess_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_mean_excess_right_tail.png)

_Figure: `evt_standardized_mean_excess_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_mean_excess_right_tail.png`._

![evt_standardized_qq_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_qq_right_tail.png)

_Figure: `evt_standardized_qq_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_qq_right_tail.png`._

![evt_standardized_threshold_stability_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/evt_standardized_threshold_stability_right_tail.png)

_Figure: `evt_standardized_threshold_stability_right_tail`. Source: `forecasts/ml_tail_forecasts.parquet`. Claim scope: `evt_standardized_residual_diagnostic_not_forecast_claim`. Tail side: `right_tail`. Run file: `latex/figures/evt_standardized_threshold_stability_right_tail.png`._

#### Appendix Figure A. DST Attenuation Diagnostics

- Appendix-only diagnostic: the left/right timing-regime patterns are not stable enough for a main-text claim.
- Key readings: bars report loss gains from adding `JP + US close core` to `JP only`, split by EST/EDT timing regime.
- A positive gain means the expanded information set has lower average loss; a negative gain means it performs worse on that loss metric.
- This diagnostic is computed for the current primary nested-information-set anchor, `LGBM direct quantile`; it is not an average across all LightGBM/EVT variants or a model-selection exercise.
- Treat this as descriptive timing evidence; left/right patterns should not be assigned a shared structural mechanism.

![dst_attenuation_left_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/dst_attenuation_left_tail.png)

_Figure: `dst_attenuation_left_tail`. Source: `metrics/ml_tail_dst_attenuation.parquet`. Claim scope: `descriptive_dst_attenuation_not_structural_causal_identification`. Tail side: `left_tail`. Run file: `latex/figures/dst_attenuation_left_tail.png`._

![dst_attenuation_right_tail](figures/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/dst_attenuation_right_tail.png)

_Figure: `dst_attenuation_right_tail`. Source: `metrics/ml_tail_dst_attenuation.parquet`. Claim scope: `descriptive_dst_attenuation_not_structural_causal_identification`. Tail side: `right_tail`. Run file: `latex/figures/dst_attenuation_right_tail.png`._

### Artifact Index

| Artifact | Path | Exists |
| --- | --- | --- |
| manifest | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/manifest.json` | yes |
| data_vintage | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/data_vintage.json` | yes |
| modeling_panel | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/modeling_panel.parquet` | yes |
| target_audit | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/target_audit.parquet` | yes |
| calendar_map | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/calendar_map.parquet` | yes |
| feature_coverage | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/tp/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/feature_coverage.parquet` | yes |
| leakage_summary | `/Volumes/ExternalSSD/data/n225-open-gap-tail/gold/ls/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/summary.json` | yes |
| benchmark_status | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/benchmark_status.json` | yes |
| benchmark_metrics | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/benchmark_metrics.parquet` | yes |
| benchmark_metrics_per_model | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/benchmark_metrics_per_model.parquet` | yes |
| benchmark_forecasts | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/forecasts/benchmark_forecasts.parquet` | yes |
| benchmark_dm_inference | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/benchmark_dm_inference.parquet` | yes |
| benchmark_mcs | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/benchmark_mcs.parquet` | yes |
| ml_tail_status | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_status.json` | yes |
| ml_tail_metrics | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_metrics.parquet` | yes |
| ml_tail_metrics_per_model | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_metrics_per_model.parquet` | yes |
| ml_tail_forecasts | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/forecasts/ml_tail_forecasts.parquet` | yes |
| ml_tail_result_matrix | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_result_matrix.parquet` | yes |
| ml_tail_result_matrix_dm | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_result_matrix_dm.parquet` | yes |
| ml_tail_result_matrix_mcs | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_result_matrix_mcs.parquet` | yes |
| ml_tail_dm_inference | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_dm_inference.parquet` | yes |
| ml_tail_mcs | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_mcs.parquet` | yes |
| ml_tail_cpa_inference | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_cpa_inference.parquet` | yes |
| cross_model_cpa_inference | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/cross_model_cpa_inference.parquet` | yes |
| ml_tail_model_eviction | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_model_eviction.parquet` | yes |
| ml_tail_dst_attenuation | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_dst_attenuation.parquet` | yes |
| ml_tail_murphy | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_murphy.parquet` | yes |
| ml_tail_feature_unavailability | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_feature_unavailability.parquet` | yes |
| benchmark_stress_windows | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/benchmark_stress_windows.parquet` | yes |
| ml_tail_stress_windows | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/metrics/ml_tail_stress_windows.parquet` | yes |
| figure_manifest | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/figure_manifest.json` | yes |
| table_manifest | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/table_manifest.json` | yes |
| latex_dir | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/tables` | yes |
| claim_scope_table | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/tables/tailrisk_claim_scope_table.tex` | yes |
| es_severity_table | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/tables/tailrisk_es_severity_table.tex` | yes |
| hedge_trigger_table | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/tables/tailrisk_hedge_trigger_diagnostics_table.tex` | yes |
| dst_attenuation_table | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/tables/ml_tail_dst_attenuation_table.tex` | yes |
| result_matrix_summary_table | `reports/runs/tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e/latex/tables/ml_tail_result_matrix_summary_table.tex` | yes |

- All paths above are local ignored artifacts; they are reproducible outputs, not tracked source files.
- Forecast/reporting rebuilds should read these artifacts and must not call vendor APIs.
- If this page is stale, rerun `just snapshot` after a completed `just full` or pass an explicit run id to the CLI snapshot command.

### Technical Infrastructure Note

- Runtime imports are explicit at the module boundary; no dynamic runtime namespace bridge is required to generate this snapshot. This infrastructure note is separate from empirical claim boundaries.
