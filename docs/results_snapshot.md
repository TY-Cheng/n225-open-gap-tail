---
hide:
  - navigation
---

# Results Snapshot

> **Research-candidate evidence map.** This page interprets the locked run
> `tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4`.
> It is a paper-facing guide to the figures, tables, and diagnostics rather
> than manuscript prose or a raw artifact dump. The empirical source is the
> May 27 locked evidence package only.

!!! warning "Claim boundary"
    The current evidence supports a 95% point-in-time VaR/ES forecast-evaluation
    design for the OSE Nikkei 225 Futures settlement-to-open opening gap. It
    does not support a trading rule, a production margin system, a structural
    price-discovery claim, a universal best-model ranking, or 97.5%/99% tail
    claims.

## 1. How To Read The Evidence

The results are easiest to read as a hierarchy.

1. **Target and timing.** The risk object is the total OSE settlement-to-open
   gap, forecast from the U.S.-close forecast origin under a row-by-row
   feature-availability audit.
2. **Direct information-set ladder.** Direct LightGBM quantile rows test how
   nested information sets change loss and coverage. These rows are the clean
   information-set experiment.
3. **Coverage-loss tension.** Lower average quantile or Fissler-Ziegel joint
   VaR-ES loss (FZ loss) is not enough for a risk forecast if VaR exceptions
   move away from the nominal 5% rate.
4. **Filtered-tail calibration.** Filtered-tail specifications are a separate
   calibration layer. Side-specific promoted rows are gated candidates under
   the locked evaluation, not universal winners across the full model universe.
5. **Diagnostics.** DM heatmaps, Murphy diagrams, severity plots, stress
   overlays, and sensitivity checks support interpretation and robustness.
   They do not replace the main loss-plus-coverage evidence.

The main empirical reading is therefore not "U.S.-close information always
improves forecasts." The reading is narrower: U.S.-close and proxy information
changes loss and coverage; usable opening-gap VaR/ES forecasts require
filtered-tail calibration and exception discipline.

## 2. Locked Run And Sample

| Field | Value |
| --- | --- |
| Run ID | `tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4` |
| Artifact root | `reports/runs/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4` |
| Claim level | `research_candidate` |
| Requested window | `2016-07-19` to `2026-05-22` |
| Combined clean start | `2018-06-20` |
| Forecast sample | 1,722 observations, `2018-06-20` to `2026-05-22` |
| Gold panel | 2,403 rows and 1,428 columns |
| Git commit in run | `7f628ff4f66258a36314f492b652cdf7ef594b7e` |
| Git dirty in run | `False` |
| Config hash | `874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c` |
| Panel signature | `8094755ffc96b01af6fb904876e0abdd3920370fa1b07e44c2c95681cd3e5431` |

The 1,722-row sample is the clean forecast sample after timing alignment,
opening-gap cleaning, and source-coverage checks. Model comparison samples are
smaller because each comparison is made on dates where the relevant forecasts,
VaR, ES, and losses are all available. The headline common samples are:

| Evidence surface | Common sample |
| --- | ---: |
| Benchmark floor metrics | 722 |
| Direct LightGBM information-set rows | 527 |
| Downside promoted row metrics | 527 |
| Upside promoted row metrics | 493 |
| Downside direct-anchor restricted DM | 472 |
| Upside direct-anchor restricted DM | 473 |
| Coverage-admissible heatmaps | 473 left, 474 right |

Read loss comparisons only on their stated common sample. A row-level metric
sample and a paired-DM matched sample can differ because paired tests require
both forecasts to exist on the same dates.

## 3. Target, Timing, And Feature Audit

### 3.1 Target Distribution And EVT Evidence

The opening-gap target is fat-tailed on both sides. This is empirical support
for the paper's starting point: the settlement-to-open gap is a conditional
tail-risk object, not merely a conditional mean or variance forecasting target.

| Target fact | Value |
| --- | ---: |
| Mean log gap | 0.000599 |
| Standard deviation | 0.011039 |
| Skewness | -0.066817 |
| Excess kurtosis | 11.2 |
| 1% quantile | -0.031062 log (-3.06%) |
| 5% quantile | -0.015606 log (-1.55%) |
| Median | 0.001031 log (+0.10%) |
| 95% quantile | 0.015357 log (+1.55%) |
| 99% quantile | 0.027480 log (+2.79%) |
| 1% to 99% quantile range | -3.06% to +2.79% |
| Largest downside gap | -8.38% on 13 March 2020 |
| Largest upside gap | +10.18% on 10 April 2025 |
| Jarque-Bera statistic | 8962.16 |
| Jarque-Bera p-value | 0 |

The raw-tail EVT diagnostics are part of the target evidence. They are not
forecast backtests, but they document empirical tail behavior consistent with
using VaR/ES and tail calibration.

| Tail | Threshold probability | Threshold | Exceedances | Mean excess | GPD xi | GPD scale | Hill xi |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| left_tail_loss | 0.900 | 0.0160237 | 78 | 0.0104227 | 0.148364 | 0.00886263 | 0.432871 |
| left_tail_loss | 0.925 | 0.0195554 | 59 | 0.00979449 | 0.318986 | 0.00680111 | 0.342056 |
| left_tail_loss | 0.950 | 0.0223228 | 39 | 0.0114201 | 0.232349 | 0.0088172 | 0.354783 |
| left_tail_loss | 0.975 | 0.0293044 | 20 | 0.0127979 | 0.257683 | 0.00960064 | 0.31884 |
| left_tail_loss | 0.990 | 0.0373166 | 8 | 0.0175619 | 0.204438 | 0.0142233 | 0.342351 |
| right_tail_loss | 0.900 | 0.0150066 | 92 | 0.00903798 | 0.403374 | 0.00560621 | 0.381845 |
| right_tail_loss | 0.925 | 0.0169408 | 69 | 0.00984642 | 0.47548 | 0.00563718 | 0.370713 |
| right_tail_loss | 0.950 | 0.0189956 | 46 | 0.0122032 | 0.29399 | 0.00878548 | 0.41336 |
| right_tail_loss | 0.975 | 0.0259629 | 23 | 0.0146916 | 0.225126 | 0.0115191 | 0.383413 |
| right_tail_loss | 0.990 | 0.0369444 | 10 | 0.0171855 | 0.218772 | 0.0136836 | 0.352692 |
| absolute_gap | 0.900 | 0.0155233 | 170 | 0.00965025 | 0.287887 | 0.00694789 | 0.401867 |
| absolute_gap | 0.925 | 0.0175227 | 127 | 0.0106185 | 0.249472 | 0.00801625 | 0.397719 |
| absolute_gap | 0.950 | 0.0208133 | 85 | 0.011767 | 0.256151 | 0.00884033 | 0.383021 |
| absolute_gap | 0.975 | 0.0269986 | 43 | 0.0144273 | 0.164437 | 0.0120976 | 0.372398 |
| absolute_gap | 0.990 | 0.0371795 | 17 | 0.0183049 | 0.0605131 | 0.0172189 | 0.353301 |

Both loss sides show positive GPD shape estimates over the main 90% to 97.5%
thresholds, and the absolute-gap tail also remains positive over the same
range. The 99% threshold has few exceedances and should be treated as a
sensitivity point. Reporting both Hill and GPD estimates over multiple
thresholds is deliberate because tail-index estimates are sample-sensitive.

**Interpretation.** These diagnostics are evidence that the opening gap has
tail-risk content. They support the paper's move from variance forecasting to
VaR/ES and filtered-tail calibration. They do not, by themselves, choose the
forecast model.

### 3.2 Timing Audit

The timing audit records 783,378 feature-date checks, zero hard leakage
failures, and 611,790 warnings. The warnings are not timestamp violations. They
cover conservative release-lag handling, missing/source-coverage flags, and
vendor timestamp granularity. The manuscript should keep the zero-failure
result prominent while explaining that `pass_with_warnings` is a conservative
audit status, not evidence of leakage.

The calendar map also records the institutional timing environment: EDT/EST
status is handled row by row, NYSE early closes are identified, and U.S./Japan
desynchronization days are flagged. This supports the point-in-time forecast
origin; it is not a DST subsample result.

### 3.3 Predictor Coverage

The predictor coverage table is a data-transparency artifact. Most market-data
families are close to complete on the forecast sample, while some macro/credit
and option-state series have higher missingness. Coverage is not admissibility:
a predictor must also pass the timestamp audit and feature-availability cutoff.

| Source family | Information set / role | Features | Mean missing | Max missing |
| --- | --- | ---: | ---: | ---: |
| Asia proxy | Asia proxy | 10 | 0.000% | 0.000% |
| CBOE volatility | FRED/core volatility | 2 | 0.000% | 0.000% |
| cross-market derived | Asia proxy | 1 | 0.000% | 0.000% |
| cross-market derived | FRED/core | 2 | 0.000% | 0.000% |
| cross-market derived | Japan proxy | 2 | 0.000% | 0.000% |
| cross-market derived | U.S. core | 2 | 0.000% | 0.000% |
| event calendar | calendar controls | 7 | 0.000% | 0.000% |
| FRED core | FRED/core | 9 | 0.000% | 0.000% |
| FRED credit enriched | FRED credit enriched | 4 | 62.398% | 62.427% |
| FX core | FX core | 4 | 0.000% | 0.000% |
| Japan history | Japan-only | 37 | 0.005% | 0.058% |
| Japan proxy | Japan proxy | 8 | 0.000% | 0.000% |
| J-Quants N225 options | Japan-only | 30 | 1.605% | 14.634% |
| Massive daily | U.S. core | 40 | 0.001% | 0.058% |
| Massive minute | Asia proxy | 60 | 0.000% | 0.000% |
| Massive minute | Japan proxy | 24 | 0.348% | 4.181% |
| Massive minute | U.S. late session | 84 | 0.000% | 0.000% |
| Massive optional | optional diagnostics | 2 | 0.000% | 0.000% |

### 3.4 Gold Panel And Sample Gates

| Measure | Value |
| --- | ---: |
| Gold modeling rows | 2,403 |
| Gold columns | 1,428 |
| Target-audit rows | 2,403 |
| Clean target rows | 2,206 |
| Forecast-sample rows | 1,722 |
| Rows before combined clean start | 420 |
| Target-not-clean rows | 197 |
| Mapping excluded rows | 64 |

| Target audit reason | Rows |
| --- | ---: |
| None | 2,206 |
| roll/SQ excluded | 195 |
| missing previous JPX session | 1 |
| missing reference price | 1 |

The cache lower bound is 2016-07-19, but the actual forecast evidence begins
at the combined clean start on 2018-06-20. Roll/SQ windows and missing
reference rows are carried as explicit exclusions rather than silent drops.

### 3.5 Calendar And Leakage Summary

| Calendar / audit item | Value |
| --- | ---: |
| Normal trading mappings | 2,333 |
| U.S./Japan desync mappings | 1 |
| NYSE early-close mappings | 32 |
| EDT rows | 1,563 |
| EST rows | 840 |
| Leakage audit status | pass_with_warnings |
| Rows audited | 783,378 |
| Hard timestamp failures | 0 |
| Warnings | 611,790 |
| Panel row count | 2,403 |

The calendar map covers EST/EDT, NYSE early closes, U.S./Japan holiday
desynchronization, and normal trading alignments. Desynchronization rows are
not treated as normal forecast rows. The leakage summary is tied to the same
panel signature reported in the locked run metadata.

## 4. Model And Evaluation Setup

| Step | Layer | Purpose |
| --- | --- | --- |
| 1 | Vendor and calendar sources | Read J-Quants, Massive, FRED, CBOE, and exchange-calendar inputs. |
| 2 | Bronze/silver cache | Preserve typed vendor rows, then normalize point-in-time research features. |
| 3 | Gold modeling panel | Join targets, calendar map, feature coverage, and leakage-bound signatures. |
| 4 | Leakage and coverage gates | Enforce timestamp ordering and sample eligibility before evaluation. |
| 5 | Benchmark and ML-tail registry | Run target-history/econometric benchmarks and LightGBM tail-model families. |
| 6 | Metrics and inference | Build loss matrices, DM/Murphy diagnostics, stress windows, and result matrices. |
| 7 | Results snapshot | Summarize run-specific evidence and claim boundaries for review. |

The registered risk level is 95% VaR. Exceptions are counted when realized
loss exceeds the VaR forecast. Forecast evaluation is based on exception
rates, Kupiec and Christoffersen checks, quantile loss, FZ loss, and
block-bootstrap Diebold-Mariano comparisons where registered. Benchmark rows
use target-history information only. LightGBM rows add predictors through fixed
nested information sets.

## 5. Forecast Evidence

### 5.1 Benchmark Floor

The benchmark floor is credible. It includes historical quantile, rolling
quantile, EWMA, GARCH-type, Student-t, and GJR-GARCH-EVT rows rather than only
naive baselines.

Status: completed. Forecast rows: 15,173. Metric rows: 14. Failures: 0.

| Model | Tail side | N | Breach rate | Exceptions | Quantile loss | FZ loss |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| EWMA volatility-scaled | left_tail | 722 | 5.263% | 38 | 0.001409 | -3.647 |
| EWMA volatility-scaled | right_tail | 722 | 4.571% | 33 | 0.001342 | -3.657 |
| GARCH-t | left_tail | 722 | 6.094% | 44 | 0.001368 | -3.701 |
| GARCH-t | right_tail | 722 | 4.155% | 30 | 0.001278 | -3.703 |
| GAS-t location-scale | left_tail | 722 | 6.371% | 46 | 0.001352 | -3.694 |
| GAS-t location-scale | right_tail | 722 | 4.986% | 36 | 0.001307 | -3.668 |
| GJR-GARCH-EVT | left_tail | 722 | 6.094% | 44 | 0.001330 | -3.746 |
| GJR-GARCH-EVT | right_tail | 722 | 5.817% | 42 | 0.001233 | -3.709 |
| GJR-GARCH-t | left_tail | 722 | 7.064% | 51 | 0.001338 | -3.723 |
| GJR-GARCH-t | right_tail | 722 | 4.294% | 31 | 0.001222 | -3.740 |
| Historical quantile | left_tail | 722 | 5.540% | 40 | 0.001476 | -3.541 |
| Historical quantile | right_tail | 722 | 6.925% | 50 | 0.001502 | -3.407 |
| Rolling quantile | left_tail | 722 | 5.817% | 42 | 0.001481 | -3.525 |
| Rolling quantile | right_tail | 722 | 7.202% | 52 | 0.001496 | -3.427 |

The benchmark results matter for two reasons. First, the flexible forecasts are
not being compared against a weak strawman. Second, some conventional
conditional-tail rows have near-nominal exception behavior, so later loss
improvements must still pass coverage discipline.

The best benchmark by FZ loss is GJR-GARCH-EVT on the downside and GJR-GARCH-t
on the upside. The GJR-GARCH-EVT row also provides the main EVT-style
econometric benchmark against which flexible filtered-tail forecasts are
interpreted.

### 5.2 Direct Information-Set Ladder

The direct LightGBM quantile rows isolate the information-set experiment. Each
row uses the same direct conditional-quantile family while the information set
is expanded from Japan-only history to U.S.-close core variables, U.S.-traded
Japan proxies, and regional Asia proxies.

| Tail side | Information set | N | Exceptions | Breach rate | Quantile loss | FZ loss |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Left/downside | Japan-only | 527 | 43 | 8.159% | 0.001412 | -3.489 |
| Left/downside | +U.S.-close core | 527 | 59 | 11.195% | 0.001158 | -3.668 |
| Left/downside | +Japan proxy | 527 | 62 | 11.765% | 0.001114 | -3.869 |
| Left/downside | +Asia proxy | 527 | 62 | 11.765% | 0.001119 | -3.808 |
| Right/upside | Japan-only | 527 | 51 | 9.677% | 0.001310 | -3.487 |
| Right/upside | +U.S.-close core | 527 | 63 | 11.954% | 0.001252 | -3.486 |
| Right/upside | +Japan proxy | 527 | 61 | 11.575% | 0.001211 | -3.557 |
| Right/upside | +Asia proxy | 527 | 68 | 12.903% | 0.001222 | -3.559 |

The direct rows show the coverage-loss tension. On the downside, external
information lowers average loss, but the U.S.-close and proxy layers also push
95% VaR exceptions well above the nominal 5% rate. On the upside, the
U.S.-close core layer changes the row, but the FZ-loss movement is small and
coverage also deteriorates. All eight direct rows breach the 2.5 percentage
point coverage band around the nominal 5% rate.

### 5.3 Incremental Information Tests

The paired information-ladder tests should be read as information-set evidence,
not as broad model-family ranking.

| Tail side | Transition | FZ-loss gain | DM p-value | Reading |
| --- | --- | ---: | ---: | --- |
| Left/downside | Japan-only to +U.S.-close core | 0.179 | 0.194 | Descriptive loss movement |
| Left/downside | +U.S.-close core to +Japan proxy | 0.200 | 0.045 | Stronger paired evidence, but coverage remains poor |
| Left/downside | +Japan proxy to +Asia proxy | -0.061 | 0.894 | Asia layer gives back FZ loss |
| Left/downside | Japan-only to all layers | 0.318 | 0.019 | Direct-ladder cumulative evidence, still coverage-limited |
| Right/upside | Japan-only to +U.S.-close core | -0.001 | 0.510 | No meaningful FZ improvement |
| Right/upside | +U.S.-close core to +Japan proxy | 0.071 | 0.054 | Borderline loss movement, coverage-limited |
| Right/upside | +Japan proxy to +Asia proxy | 0.002 | 0.480 | Little incremental content |
| Right/upside | Japan-only to all layers | 0.072 | 0.316 | Not a strong cumulative result |

The U.S.-close direct layer is therefore not the strongest statistical step.
The defensible claim is that U.S.-close and proxy information changes the
loss/coverage profile; it is not that the U.S.-close block alone delivers a
coverage-admissible improvement.

### 5.4 Promoted Filtered-Tail Rows

The promoted rows are side-specific gated candidates. They combine loss,
coverage, sample-size, and model-validity screens. They should not be described
as universal best models.

| Tail side | Promoted row | Information set | N | Exceptions | Breach rate | Q loss | FZ loss | Kupiec p | Christoffersen p |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Left/downside | LightGBM median/IQR POT-GPD plain MLE | all layers | 527 | 31 | 5.882% | 0.000917 | -4.222 | 0.365 | 0.481 |
| Right/upside | LightGBM location-scale empirical | Japan-only + U.S.-close core + Japan proxy | 493 | 30 | 6.085% | 0.001023 | -4.027 | 0.284 | 0.393 |

Restricted paired comparisons against the direct-quantile anchors favor these
promoted rows on their matched samples:

| Tail side | Candidate-minus-anchor FZ difference | Matched N | DM p-value | Reading |
| --- | ---: | ---: | ---: | --- |
| Left/downside | -0.489 | 472 | 0.049 | Candidate has lower FZ loss, screened evidence |
| Right/upside | -0.530 | 473 | 0.003 | Candidate has lower FZ loss, screened evidence |

Negative FZ-loss differences favor the candidate. These p-values are restricted
comparisons after screening; they are not multiplicity-adjusted evidence for a
universal best model across the full candidate universe.

### 5.5 Screening Audit And Filtered-Tail Diagnostics

The LightGBM candidate universe is 8 forecast families times 4 information
sets times 2 tails. Per tail, that gives 32 candidate rows before gates.

| Gate | Left/downside rows remaining | Right/upside rows remaining |
| --- | ---: | ---: |
| Initial LightGBM universe | 32 | 32 |
| Valid VaR/ES/FZ | 32 | 32 |
| N >= 450 | 32 | 32 |
| Within 2.5 percentage point breach band | 28 | 24 |
| Kupiec and Christoffersen screens | 25 | 20 |
| Side-specific promoted row | 1 | 1 |

The downside promoted POT-GPD row also has a filtered-tail diagnostic trail:
41 monthly POT refits, median exceedance count 111, exceedance-count IQR
92-128, median fitted shape xi 0.238, xi IQR 0.163-0.292, and 100% ES-valid
refits under the finite-ES condition. The upside promoted row uses empirical
location-scale calibration, so POT-GPD shape diagnostics are not applicable.

These diagnostics support the finite-ES and sample-support reading for the
promoted downside row. They do not prove EVT stability in a formal asymptotic
sense.

### 5.6 ML-Tail Artifact Relationship

| Artifact | Rows | Role | Claim boundary |
| --- | ---: | --- | --- |
| `ml_tail_metrics.parquet` | 8 | Primary direct information-set comparison | Eligible for primary discussion after author review. |
| `ml_tail_metrics_per_model.parquet` | 64 | Per-model diagnostics on each model's own valid OOS rows | Not a cross-model comparison. |
| `ml_tail_result_matrix.parquet` | 384 | Restricted common-sample VaR-only and VaR/ES comparisons | Restricted evidence; direct quantile rows are anchors. |

The primary direct information-set table, the promoted-row table, and the
restricted result matrix answer different questions. Keeping those artifacts
separate prevents an all-model scan from becoming a leaderboard.

### 5.7 All-Model Diagnostic Scan

The all-model scan makes the full benchmark and LightGBM universe visible. It
is useful for auditability and for seeing why promoted rows are gated. It is
not the formal cross-model comparison table because valid samples differ.

<details>
<summary>Full all-model diagnostic scan</summary>

| Suite | Model | Information set | Metric rows | OOS N mean+-sd | Breach mean+-sd | Abs cov err mean+-sd | Q loss mean+-sd | FZ loss mean+-sd | ES severity mean+-sd |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| benchmark_advanced | CARE asymmetric slope | Target history | 2 | 653 +/- 36.770 | 7.884% +/- 0.097% | 2.884% +/- 0.097% | 0.001383 +/- 0.000080 | -3.577 +/- 0.064 | 0.008274 +/- 0.000559 |
| benchmark_advanced | CARE SAV | Target history | 2 | 649.5 +/- 41.719 | 7.658% +/- 1.250% | 2.658% +/- 1.250% | 0.001414 +/- 0.000060 | -3.541 +/- 0.094 | 0.008572 +/- 0.000529 |
| benchmark_advanced | CAViaR asymmetric slope | Target history | 2 | 506 +/- 2.828 | 6.916% +/- 0.241% | 1.916% +/- 0.241% | 0.001529 +/- 0.000049 | -3.499 +/- 0.047 | 0.010065 +/- 0.000926 |
| benchmark_advanced | CAViaR SAV | Target history | 2 | 501 +/- 4.243 | 6.086% +/- 0.372% | 1.086% +/- 0.372% | 0.001563 +/- 0.000007 | -3.474 +/- 0.094 | 0.011652 +/- 0.000033 |
| benchmark_advanced | GAS-t location-scale | Target history | 2 | 722 +/- 0 | 5.679% +/- 0.979% | 0.693% +/- 0.960% | 0.001330 +/- 0.000032 | -3.681 +/- 0.018 | 0.009592 +/- 0.001304 |
| benchmark_advanced | GAS-t POT-GPD | Target history | 2 | 223 +/- 0 | 6.502% +/- 2.854% | 2.018% +/- 2.124% | 0.001531 +/- 0.000359 | -3.412 +/- 0.534 | 0.009774 +/- 0.004270 |
| benchmark_baseline | EWMA volatility-scaled | Target history | 2 | 722 +/- 0 | 4.917% +/- 0.490% | 0.346% +/- 0.118% | 0.001375 +/- 0.000048 | -3.652 +/- 0.006 | 0.009211 +/- 0.000814 |
| benchmark_baseline | GARCH-t | Target history | 2 | 722 +/- 0 | 5.125% +/- 1.371% | 0.970% +/- 0.176% | 0.001323 +/- 0.000064 | -3.702 +/- 0.002 | 0.009749 +/- 0.001611 |
| benchmark_baseline | GJR-GARCH-EVT | Target history | 2 | 722 +/- 0 | 5.956% +/- 0.196% | 0.956% +/- 0.196% | 0.001282 +/- 0.000069 | -3.727 +/- 0.027 | 0.008309 +/- 0.000959 |
| benchmark_baseline | GJR-GARCH-t | Target history | 2 | 722 +/- 0 | 5.679% +/- 1.959% | 1.385% +/- 0.960% | 0.001280 +/- 0.000083 | -3.732 +/- 0.011 | 0.008815 +/- 0.002060 |
| benchmark_baseline | Historical quantile | Target history | 2 | 722 +/- 0 | 6.233% +/- 0.979% | 1.233% +/- 0.979% | 0.001489 +/- 0.000018 | -3.474 +/- 0.095 | 0.012072 +/- 0.000097 |
| benchmark_baseline | Rolling quantile | Target history | 2 | 722 +/- 0 | 6.510% +/- 0.979% | 1.510% +/- 0.979% | 0.001488 +/- 0.000010 | -3.476 +/- 0.069 | 0.011582 +/- 0.000144 |
| ml_tail | LGBM direct quantile | Japan-only | 2 | 554 +/- 0 | 8.664% +/- 1.021% | 3.664% +/- 1.021% | 0.001338 +/- 0.000093 | -3.503 +/- 0.039 | 0.008137 +/- 0.001136 |
| ml_tail | LGBM direct quantile | +U.S.-close core | 2 | 554 +/- 0 | 11.101% +/- 0.383% | 6.101% +/- 0.383% | 0.001180 +/- 0.000043 | -3.614 +/- 0.092 | 0.006439 +/- 0.000248 |
| ml_tail | LGBM direct quantile | +Japan proxy | 2 | 527 +/- 0 | 11.670% +/- 0.134% | 6.670% +/- 0.134% | 0.001163 +/- 0.000069 | -3.713 +/- 0.220 | 0.005980 +/- 0.000663 |
| ml_tail | LGBM direct quantile | +Asia proxy | 2 | 527 +/- 0 | 12.334% +/- 0.805% | 7.334% +/- 0.805% | 0.001171 +/- 0.000073 | -3.683 +/- 0.176 | 0.005717 +/- 0.000192 |
| ml_tail | LGBM location-scale empirical | Japan-only | 2 | 508 +/- 0 | 4.823% +/- 0.696% | 0.492% +/- 0.251% | 0.001416 +/- 0.000100 | -3.564 +/- 0.014 | 0.009987 +/- 0.000172 |
| ml_tail | LGBM location-scale empirical | +U.S.-close core | 2 | 505.5 +/- 0.707 | 6.133% +/- 0.009% | 1.133% +/- 0.009% | 0.001018 +/- 0.000042 | -4.011 +/- 0.056 | 0.006046 +/- 0.000458 |
| ml_tail | LGBM location-scale empirical | +Japan proxy | 2 | 492.5 +/- 0.707 | 6.295% +/- 0.296% | 1.295% +/- 0.296% | 0.001006 +/- 0.000025 | -4.085 +/- 0.081 | 0.005910 +/- 0.000534 |
| ml_tail | LGBM location-scale empirical | +Asia proxy | 2 | 492 +/- 0 | 6.707% +/- 0.575% | 1.707% +/- 0.575% | 0.001036 +/- 0.000070 | -3.985 +/- 0.105 | 0.005902 +/- 0.001530 |
| ml_tail | LGBM POT-GPD plain MLE | Japan-only | 2 | 484 +/- 0 | 4.649% +/- 1.315% | 0.930% +/- 0.497% | 0.001444 +/- 0.000107 | -3.551 +/- 0.036 | 0.010610 +/- 0.001116 |
| ml_tail | LGBM POT-GPD plain MLE | +U.S.-close core | 2 | 482 +/- 0 | 5.498% +/- 0.440% | 0.498% +/- 0.440% | 0.001024 +/- 0.000039 | -4.032 +/- 0.069 | 0.006536 +/- 0.000836 |
| ml_tail | LGBM POT-GPD plain MLE | +Japan proxy | 2 | 473.5 +/- 0.707 | 5.808% +/- 0.158% | 0.808% +/- 0.158% | 0.001012 +/- 0.000031 | -4.091 +/- 0.086 | 0.006235 +/- 0.000519 |
| ml_tail | LGBM POT-GPD plain MLE | +Asia proxy | 2 | 473 +/- 0 | 6.131% +/- 0.598% | 1.131% +/- 0.598% | 0.001038 +/- 0.000072 | -4.008 +/- 0.118 | 0.006227 +/- 0.001685 |
| ml_tail | LGBM POT-GPD UniBM | Japan-only | 2 | 484 +/- 0 | 4.855% +/- 1.023% | 0.723% +/- 0.205% | 0.001440 +/- 0.000109 | -3.547 +/- 0.051 | 0.010130 +/- 0.000667 |
| ml_tail | LGBM POT-GPD UniBM | +U.S.-close core | 2 | 483 +/- 0 | 5.901% +/- 0.732% | 0.901% +/- 0.732% | 0.001023 +/- 0.000035 | -4.029 +/- 0.064 | 0.006307 +/- 0.000887 |
| ml_tail | LGBM POT-GPD UniBM | +Japan proxy | 2 | 473.5 +/- 0.707 | 6.019% +/- 0.457% | 1.019% +/- 0.457% | 0.001015 +/- 0.000024 | -4.076 +/- 0.078 | 0.006327 +/- 0.000531 |
| ml_tail | LGBM POT-GPD UniBM | +Asia proxy | 2 | 473.5 +/- 0.707 | 6.125% +/- 0.606% | 1.125% +/- 0.606% | 0.001042 +/- 0.000062 | -3.993 +/- 0.090 | 0.006436 +/- 0.001328 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | Japan-only | 2 | 484 +/- 0 | 5.165% +/- 0.000% | 0.165% +/- 0.000% | 0.001410 +/- 0.000113 | -3.604 +/- 0.010 | 0.010510 +/- 0.001016 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | +U.S.-close core | 2 | 484 +/- 0 | 6.818% +/- 0.584% | 1.818% +/- 0.584% | 0.001094 +/- 0.000037 | -4.059 +/- 0.086 | 0.007904 +/- 0.000395 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | +Japan proxy | 2 | 473.5 +/- 0.707 | 7.287% +/- 0.758% | 2.287% +/- 0.758% | 0.001024 +/- 0.000082 | -4.198 +/- 0.159 | 0.006601 +/- 0.000331 |
| ml_tail | LGBM median/MAD POT-GPD plain MLE | +Asia proxy | 2 | 473.5 +/- 0.707 | 7.076% +/- 0.757% | 2.076% +/- 0.757% | 0.001059 +/- 0.000093 | -4.096 +/- 0.245 | 0.007306 +/- 0.000570 |
| ml_tail | LGBM median/MAD POT-GPD UniBM | Japan-only | 2 | 484 +/- 0 | 5.579% +/- 0.584% | 0.579% +/- 0.584% | 0.001413 +/- 0.000111 | -3.606 +/- 0.011 | 0.010119 +/- 0.001675 |
| ml_tail | LGBM median/MAD POT-GPD UniBM | +U.S.-close core | 2 | 484 +/- 0 | 6.921% +/- 0.438% | 1.921% +/- 0.438% | 0.001095 +/- 0.000034 | -4.068 +/- 0.111 | 0.007922 +/- 0.000309 |
| ml_tail | LGBM median/MAD POT-GPD UniBM | +Japan proxy | 2 | 473.5 +/- 0.707 | 7.603% +/- 0.310% | 2.603% +/- 0.310% | 0.001032 +/- 0.000074 | -4.170 +/- 0.158 | 0.006603 +/- 0.000523 |
| ml_tail | LGBM median/MAD POT-GPD UniBM | +Asia proxy | 2 | 473.5 +/- 0.707 | 7.497% +/- 0.161% | 2.497% +/- 0.161% | 0.001066 +/- 0.000085 | -4.090 +/- 0.239 | 0.007114 +/- 0.000950 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | Japan-only | 2 | 554 +/- 0 | 3.339% +/- 0.383% | 1.661% +/- 0.383% | 0.001297 +/- 0.000121 | -3.718 +/- 0.054 | 0.010472 +/- 0.000488 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | +U.S.-close core | 2 | 553.5 +/- 0.707 | 5.330% +/- 0.121% | 0.330% +/- 0.121% | 0.001006 +/- 0.000059 | -4.058 +/- 0.117 | 0.006776 +/- 0.000092 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | +Japan proxy | 2 | 526 +/- 0 | 4.753% +/- 0.000% | 0.247% +/- 0.000% | 0.000972 +/- 0.000096 | -4.064 +/- 0.190 | 0.007180 +/- 0.000904 |
| ml_tail | LGBM median/IQR POT-GPD plain MLE | +Asia proxy | 2 | 527 +/- 0 | 5.977% +/- 0.134% | 0.977% +/- 0.134% | 0.000982 +/- 0.000091 | -4.073 +/- 0.211 | 0.005951 +/- 0.000648 |
| ml_tail | LGBM median/IQR POT-GPD UniBM | Japan-only | 2 | 554 +/- 0 | 3.430% +/- 0.255% | 1.570% +/- 0.255% | 0.001292 +/- 0.000129 | -3.723 +/- 0.055 | 0.010390 +/- 0.000333 |
| ml_tail | LGBM median/IQR POT-GPD UniBM | +U.S.-close core | 2 | 553.5 +/- 0.707 | 5.420% +/- 0.249% | 0.420% +/- 0.249% | 0.001005 +/- 0.000064 | -4.038 +/- 0.106 | 0.006803 +/- 0.000029 |
| ml_tail | LGBM median/IQR POT-GPD UniBM | +Japan proxy | 2 | 527 +/- 0 | 4.934% +/- 0.268% | 0.190% +/- 0.094% | 0.000977 +/- 0.000100 | -4.072 +/- 0.268 | 0.007226 +/- 0.000739 |
| ml_tail | LGBM median/IQR POT-GPD UniBM | +Asia proxy | 2 | 527 +/- 0 | 5.882% +/- 0.000% | 0.882% +/- 0.000% | 0.000982 +/- 0.000096 | -4.078 +/- 0.191 | 0.006175 +/- 0.001006 |

</details>

This scan shows why the promoted-row gate is needed. Several filtered-tail rows
have better FZ loss than direct quantile rows, but coverage and valid-sample
support differ by family. The promoted rows are selected only after the
coverage and inference gates are applied.

## 6. Restricted Diagnostics

### 6.1 Result Matrix And DM Evidence

The result matrix provides common-date comparisons for registered loss and
coverage surfaces. Coverage metrics are descriptive in the DM table, while FZ
loss and quantile loss have block-bootstrap Diebold-Mariano diagnostics where
registered.

| Family | Axis | Loss | Rows | Common N | Date range | Joint exceptions |
| --- | --- | --- | ---: | --- | --- | --- |
| nested information sets | information-set increment | VaR coverage | 64 | 471 to 527 | 2023-01-26 to 2026-05-21 | 34 to 80 |
| nested information sets | information-set increment | FZ loss | 64 | 471 to 527 | 2023-01-26 to 2026-05-21 | 34 to 80 |
| nested information sets | information-set increment | quantile loss | 64 | 471 to 527 | 2023-01-26 to 2026-05-21 | 34 to 80 |
| tail-model family | model family | VaR coverage | 64 | 472 to 484 | 2023-06-16 to 2026-05-21 | 47 to 70 |
| tail-model family | model family | FZ loss | 64 | 472 to 484 | 2023-06-16 to 2026-05-21 | 47 to 70 |
| tail-model family | model family | quantile loss | 64 | 472 to 484 | 2023-06-16 to 2026-05-21 | 47 to 70 |

| Comparison object | Tail side | Candidate-minus-anchor FZ difference | DM p-value | Reading |
| --- | --- | ---: | ---: | --- |
| Japan-only to +U.S.-close core direct row | left_tail | -0.179 | 0.194 | Descriptive U.S.-close loss movement |
| Japan-only to +U.S.-close core direct row | right_tail | 0.001 | 0.510 | No FZ improvement |
| Direct quantile anchor to promoted row | left_tail | -0.489 | 0.049 | Screened restricted evidence |
| Direct quantile anchor to promoted row | right_tail | -0.530 | 0.003 | Screened restricted evidence |

The compact DM summary should be the first inference table read from the full
matrix. It separates three objects:

- direct information-set transitions;
- direct-quantile anchor versus promoted filtered-tail row;
- unsupported benchmark-floor versus promoted-row dominance claims.

The benchmark-floor to promoted-row comparison is not registered as a headline
cross-suite DM claim in the compact table. Separate heatmaps visualize the
coverage-admissible comparison set, but they should be read as restricted
diagnostics rather than replacement evidence for the promoted-row gates.

### 6.2 Murphy, Severity, And Stress Diagnostics

| Diagnostic family | Rows | Main reading |
| --- | ---: | --- |
| Benchmark Murphy | 2,800 | Benchmark scoring-family sensitivity on a common grid. |
| LightGBM 24-check Murphy | 3,200 | Scoring sensitivity among rows that pass the 24-check screen. |
| ES severity | 86 finite rows | Conditional-on-exception loss severity, not standalone selection. |
| Benchmark stress windows | 146 | High-loss diagnostic windows. |
| ML-tail stress windows | 212 | High-loss and high-VIX diagnostic windows. |

Murphy diagrams check how conclusions vary across scoring-function
decompositions. They help assess scoring robustness but do not override VaR
coverage or FZ loss.

ES severity plots condition on exceptions and compare realized losses beyond
the VaR threshold. They are useful for understanding exception size, not for
selecting a model by themselves.

Stress overlays for 2024 and 2025 show how selected VaR/ES paths behave around
named high-loss windows. They are visual diagnostics, not trading backtests or
stress-window validation claims. The stress-window classifier is fixed as a
full-sample reproducible decile diagnostic; rolling stress-window validation is
future work and is not part of the first-round evidence.

### 6.3 Sensitivity Evidence

Sensitivity outputs are explicitly not primary-claim evidence. Threshold
perturbations around POT-GPD are useful for checking whether the selected
filtered-tail conclusions are fragile to nearby threshold choices. LightGBM
capacity sensitivity is a robustness check on specification dependence. Neither
surface is used to reselect the headline sample, information set, or model.

| Sensitivity item | Value |
| --- | --- |
| Primary run | `tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4` |
| Primary-claim allowed | `False` |
| Selected LGBM models | POT-GPD plain MLE and POT-GPD UniBM |
| Selected benchmark model | GJR-GARCH-EVT |
| Selected information set | +U.S.-close core + Japan proxy |
| Forecast rows | 13,096 |
| Metric rows | 26 |
| LGBM capacity classifications | 8 robust rows |
| POT threshold classifications | 12 robust rows, 6 boundary-diagnostic rows |
| Status | ok |

## 7. Figure Interpretation Guide

The figure guide includes every generated figure in the docs bundle. Each
figure appears with a short interpretation and the boundary on what it can
support.

| Figure | Source artifacts | Claim scope | Tail side |
| --- | --- | --- | --- |
| market_timing_design | `manifest.json`, `config/research_config.json`, `panel/calendar_map.parquet` | design forecast origin, not causal price discovery | design |
| target_tail_motivation | `panel/modeling_panel.parquet` | target distribution motivation, not forecast validation | left/right target distribution |
| coverage_breach_rates_left_tail | benchmark and ML-tail metric artifacts | coverage diagnostic, not primary claim alone | left_tail |
| coverage_breach_rates_right_tail | benchmark and ML-tail metric artifacts | coverage diagnostic, not primary claim alone | right_tail |
| cumulative_lgbm_a_anchor_fz_gain | benchmark/ML loss matrices and forecasts | headline LGBM A-anchor FZ-gain diagnostic | left/right |
| selected_model_performance_left_tail | benchmark and ML per-model metrics | selected benchmark-vs-LGBM summary, not full result set | left_tail |
| selected_model_performance_right_tail | benchmark and ML per-model metrics | selected benchmark-vs-LGBM summary, not full result set | right_tail |
| full_sample_var_overlay_left_tail | benchmark and ML forecasts | fixed-selection visual diagnostic | left_tail |
| full_sample_var_overlay_right_tail | benchmark and ML forecasts | fixed-selection visual diagnostic | right_tail |
| var_es_stress_overlay_2024_stress_episode | benchmark and ML forecasts | appendix stress illustration, not validation | left/right |
| var_es_stress_overlay_2025_stress_episode | benchmark and ML forecasts | appendix stress illustration, not validation | left/right |
| dm_heatmap_left_tail | benchmark and ML forecasts | coverage-admissible FZ DM diagnostic | left_tail |
| dm_heatmap_right_tail | benchmark and ML forecasts | coverage-admissible FZ DM diagnostic | right_tail |
| benchmark_murphy_left_tail | `metrics/benchmark_murphy.parquet` | benchmark Murphy diagnostic | left_tail |
| benchmark_murphy_right_tail | `metrics/benchmark_murphy.parquet` | benchmark Murphy diagnostic | right_tail |
| lgbm_24check_murphy_left_tail | LGBM Murphy and ML-tail artifacts | LightGBM 24-check Murphy diagnostic | left_tail |
| lgbm_24check_murphy_right_tail | LGBM Murphy and ML-tail artifacts | LightGBM 24-check Murphy diagnostic | right_tail |
| es_severity_left_tail | benchmark and ML-tail metrics | ES severity diagnostic, not model selection | left_tail |
| es_severity_right_tail | benchmark and ML-tail metrics | ES severity diagnostic, not model selection | right_tail |

### Figure 1. Timing Design

**Use for:** target timing, U.S.-close forecast origin, OSE night/day-session
structure, and point-in-time cutoff logic.

**Do not use for:** price discovery, causal market transmission, or a claim
that the night session fully absorbs U.S. information.

![market_timing_design](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/market_timing_design.png)

### Figure 2. Target Tail Motivation

**Use for:** why the settlement-to-open gap is a tail-risk target. The figure
shows heavy tails, tail-index evidence, and threshold diagnostics for the raw
target.

**Do not use for:** forecast superiority or model selection.

![target_tail_motivation](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/target_tail_motivation.png)

### Figure 3. Coverage Breach Rates

**Use for:** coverage-first reading of all major forecast families. The direct
LightGBM rows over-breach, which is the main reason raw loss improvement cannot
be read as forecast admissibility.

**Do not use for:** ranking models by breach rate alone; loss and ES behavior
also matter.

![coverage_breach_rates_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/coverage_breach_rates_left_tail.png)

![coverage_breach_rates_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/coverage_breach_rates_right_tail.png)

### Figure 4. Cumulative Direct-Ladder FZ Gain

**Use for:** visualizing cumulative FZ-loss movements as information sets are
expanded from Japan-only to +U.S.-close core, +Japan proxy, and +Asia proxy.
Upward movement means the candidate has lower cumulative FZ loss under the
anchor-loss-minus-candidate-loss convention.

**Do not use for:** coverage admissibility. This figure must be read with the
breach-rate figures and promoted-row gates.

![cumulative_lgbm_a_anchor_fz_gain](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/cumulative_lgbm_a_anchor_fz_gain.png)

### Figure 5. Selected Model Performance

**Use for:** compact selected-row performance after sample-size and coverage
screens. It is a reader-friendly view of rows that survive the major gates.

**Do not use for:** a full model universe ranking. The appendix LGBM scan gives
the full candidate inventory.

![selected_model_performance_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/selected_model_performance_left_tail.png)

![selected_model_performance_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/selected_model_performance_right_tail.png)

### Figure 6. Full-Sample VaR Overlays

**Use for:** visual inspection of realized losses relative to selected VaR
paths across the full evaluation sample.

**Do not use for:** model selection, trading timing, or realized stress-window
performance claims.

![full_sample_var_overlay_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/full_sample_var_overlay_left_tail.png)

![full_sample_var_overlay_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/full_sample_var_overlay_right_tail.png)

### Figure 7. Stress Episode VaR/ES Overlays

**Use for:** stress-window illustration of selected VaR/ES paths in 2024 and
2025 episodes.

**Do not use for:** stress backtesting or capital-savings claims.

![var_es_stress_overlay_2024_stress_episode](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/var_es_stress_overlay_2024_stress_episode.png)

![var_es_stress_overlay_2025_stress_episode](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/var_es_stress_overlay_2025_stress_episode.png)

### Figure 8. DM Heatmaps

**Use for:** restricted pairwise FZ-loss diagnostics within the
coverage-admissible comparison set.

**Do not use for:** universal model ranking or benchmark-floor versus promoted
row dominance unless that paired comparison is explicitly registered in the
table being cited.

![dm_heatmap_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/dm_heatmap_left_tail.png)

![dm_heatmap_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/dm_heatmap_right_tail.png)

### Figure 9. Benchmark Murphy Diagrams

**Use for:** checking benchmark scoring robustness across Murphy-style
evaluation surfaces.

**Do not use for:** replacing the benchmark metrics table or coverage tests.

![benchmark_murphy_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_murphy_left_tail.png)

![benchmark_murphy_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_murphy_right_tail.png)

### Figure 10. LightGBM 24-Check Murphy Diagrams

**Use for:** diagnostic scoring comparison among LightGBM rows that pass the
24-check screen.

**Do not use for:** introducing a new main-text model-selection rule. The
24-check screen is a coverage-admissibility screen, not a replacement for the
promoted-row table.

![lgbm_24check_murphy_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/lgbm_24check_murphy_left_tail.png)

![lgbm_24check_murphy_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/lgbm_24check_murphy_right_tail.png)

### Figure 11. ES Severity

**Use for:** conditional-on-exception severity diagnostics. These plots show
how losses behave once the VaR threshold is breached.

**Do not use for:** standalone model selection.

![es_severity_left_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/es_severity_left_tail.png)

![es_severity_right_tail](figures/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/es_severity_right_tail.png)

## 8. Table Artifact Guide

The table guide includes every generated table in the docs bundle. The first
table is the manifest-level routing; the second table gives the reader-facing
interpretation.

| Table | Source artifacts | Claim scope | Tail side |
| --- | --- | --- | --- |
| tailrisk_predictor_block_coverage | `panel/feature_coverage.parquet` | main text predictor-block coverage and information transparency | None |
| benchmark_metrics | `metrics/benchmark_metrics.parquet` | benchmark common-sample metric table | None |
| benchmark_left_tail_risk | `metrics/benchmark_metrics.parquet` | left-tail benchmark risk table | left_tail |
| benchmark_right_tail_risk | `metrics/benchmark_metrics.parquet` | right-tail benchmark risk table | right_tail |
| ml_tail_metrics | `metrics/ml_tail_metrics.parquet` | ML-tail nested information-set table | None |
| ml_tail_left_tail_risk | `metrics/ml_tail_metrics.parquet` | left-tail ML-tail primary risk table | left_tail |
| ml_tail_right_tail_risk | `metrics/ml_tail_metrics.parquet` | right-tail ML-tail primary risk table | right_tail |
| tailrisk_model_inventory | config and per-model metric artifacts | model inventory and forecast construction | None |
| tailrisk_selected_model_performance | benchmark and ML per-model metrics | selected benchmark-vs-LGBM figure rows | None |
| appendix_benchmark_all_models | `metrics/benchmark_metrics_per_model.parquet` | appendix full benchmark results | None |
| ml_tail_promoted_tail_models | ML per-model metrics and result-matrix DM | side-specific ML-tail promotion gate | None |
| appendix_lgbm_all_models | `metrics/ml_tail_metrics_per_model.parquet` | appendix full LightGBM results | None |
| tailrisk_es_severity | benchmark and ML metric artifacts | ES severity diagnostic table | None |
| tailrisk_claim_scope | `manifest.json`, `config/research_config.json` | claim-boundary reference table | None |
| ml_tail_result_matrix | `metrics/ml_tail_result_matrix.parquet` | restricted model-comparison table | None |
| ml_tail_result_matrix_summary | result matrix and result-matrix DM | restricted result-matrix summary table | None |
| tailrisk_dm_summary | `metrics/ml_tail_result_matrix_dm.parquet` | compact DM summary | None |
| appendix_lgbm_configuration_sensitivity | LGBM capacity sensitivity metrics | appendix configuration robustness, LightGBM | None |
| appendix_evt_threshold_sensitivity | EVT threshold sensitivity metrics | appendix configuration robustness, EVT threshold | None |

| Result object | Table artifact | How to read it |
| --- | --- | --- |
| Predictor coverage | [tailrisk_predictor_block_coverage_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_predictor_block_coverage_table.tex) | Data transparency by source family; coverage is not timing admissibility. |
| Model inventory | [tailrisk_model_inventory_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_model_inventory_table.tex) | Methods inventory; use for model definitions, not performance claims. |
| Benchmark floor | [benchmark_metrics_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_metrics_table.tex) | Main benchmark calibration and loss table. |
| Benchmark tail details | [benchmark_left_tail_risk_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_left_tail_risk_table.tex), [benchmark_right_tail_risk_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_right_tail_risk_table.tex) | Tail-specific benchmark rows. |
| Direct information ladder | [ml_tail_metrics_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_metrics_table.tex) | Direct LightGBM information-set experiment; read loss with coverage. |
| Direct tail details | [ml_tail_left_tail_risk_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_left_tail_risk_table.tex), [ml_tail_right_tail_risk_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_right_tail_risk_table.tex) | Tail-specific direct LightGBM rows. |
| Promoted rows | [ml_tail_promoted_tail_models_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_promoted_tail_models_table.tex) | Side-specific gated candidates; not a universal model ranking. |
| Selected performance | [tailrisk_selected_model_performance_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_selected_model_performance_table.tex) | Compact selected-row summary after gates. |
| Full benchmark scan | [appendix_benchmark_all_models_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_benchmark_all_models_table.tex) | Appendix inventory supporting benchmark breadth. |
| Full LightGBM scan | [appendix_lgbm_all_models_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_lgbm_all_models_table.tex) | Full candidate inventory; do not use as a raw leaderboard. |
| Result matrix | [ml_tail_result_matrix_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_result_matrix_table.tex), [ml_tail_result_matrix_summary_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_result_matrix_summary_table.tex) | Restricted common-sample comparison matrix. |
| DM summary | [tailrisk_dm_summary_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_dm_summary_table.tex) | Headline paired inference; negative loss differences favor the candidate. |
| ES severity | [tailrisk_es_severity_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_es_severity_table.tex) | Exception-size diagnostic, not model selection. |
| Claim scope | [tailrisk_claim_scope_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_claim_scope_table.tex) | Reference table separating headline, restricted, diagnostic, and sensitivity claims. |
| Breach audit | [model_metrics_breach_audit.md](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/model_metrics_breach_audit.md) | Coverage audit in plain text. |
| Full row export | [model_metrics_full_rows.csv](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/model_metrics_full_rows.csv) | Machine-readable row export for verification. |
| EVT threshold sensitivity | [appendix_evt_threshold_sensitivity_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_evt_threshold_sensitivity_table.tex) | Robustness only; not primary claim evidence. |
| LightGBM capacity sensitivity | [appendix_lgbm_configuration_sensitivity_table.tex](tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_lgbm_configuration_sensitivity_table.tex) | Robustness only; not primary claim evidence. |
