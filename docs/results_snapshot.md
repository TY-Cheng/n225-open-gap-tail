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

<details markdown="1">
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
- unsupported cross-suite dominance claims between the benchmark floor and
  promoted filtered-tail rows.

The comparison between the benchmark floor and promoted filtered-tail rows is
not registered as a primary cross-suite DM claim in the compact table. Separate
heatmaps visualize the coverage-admissible comparison set, but they should be
read as restricted diagnostics rather than replacement evidence for the
promoted-row gates.

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

**Do not use for:** universal model ranking or dominance between the benchmark
floor and promoted filtered-tail rows unless that paired comparison is
explicitly registered in the table being cited.

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

The manuscript wrapper also contains compact hand-authored or manuscript-local
tables that repackage the locked artifacts for readability. These files are not
additional empirical runs; they are the paper-facing table layer built from the
same evidence package.

| Manuscript table file | Source artifacts | Reader-facing role |
| --- | --- | --- |
| `table1_design.tex` | calendar map, timing audit, OSE/JSCC design inputs | market timing and forecast-origin design |
| `table2_benchmark_summary.tex` | `benchmark_metrics_table.tex` | compact benchmark floor for the main text |
| `table4_compact_exception_support.tex` | benchmark and ML-tail metric artifacts | headline exception counts behind the coverage discussion |
| `table3_ml_information_promoted.tex` | `ml_tail_metrics_table.tex`, promoted rows, and restricted DM evidence | nested information-set rows plus promoted filtered-tail rows |
| `promoted_screening_audit.tex` | locked LightGBM row universe and coverage gates | candidate-count audit for promoted rows |
| `filtered_tail_diagnostics.tex` | promoted-row diagnostics and coverage-test artifacts | compact diagnostic support for side-specific promoted rows |
| `sensitivity_family_summary_table.tex` | sensitivity metrics parquet files | manuscript compact sensitivity family summary |
| `sensitivity_evt_threshold_summary_table.tex` | EVT threshold sensitivity metrics | manuscript compact EVT-threshold sensitivity summary |
| `sensitivity_lgbm_capacity_summary_table.tex` | LightGBM capacity sensitivity metrics | manuscript compact LightGBM-capacity sensitivity summary |

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

## 9. Full Table Artifact Gallery

This section prints the table artifacts directly inside the snapshot so the evidence can be reviewed without opening separate files. LaTeX tables are shown as the exact source consumed by the manuscript; Markdown and CSV artifacts are printed in their native text form. The reader-facing summaries above remain the preferred way to read the main results, while this gallery is the audit layer for completeness.

### 9.1 Docs-Bundle Tables

These are the table artifacts copied into the documentation bundle for the locked May 27 evidence run.

<details markdown="1">
<summary><code>tailrisk_predictor_block_coverage_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_predictor_block_coverage_table.tex</code>.  
**ARS reading:** Predictor coverage by source family; use for data transparency, not timing admissibility.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: predictor_block_coverage_information_transparency
\begin{tabular}{llrllll}
\toprule
block & source & features & examples & mean miss & max miss & role \\
\midrule
Asia proxy & massive\_minute & 60 & eem\_final\_window\_momentum, eem\_late\_30m\_return, eem\_late\_60m\_down\_semivar & 0.000000 & 0.000000 & Asia proxy increment \\
Asia proxy & Asia proxy & 10 & eem\_range, eem\_return, ewh\_range & 0.000000 & 0.000000 & Asia proxy increment \\
Asia proxy & cross\_market\_derived & 1 & xmarket\_asia\_proxy\_return\_dispersion\_1d & 0.000000 & 0.000000 & Asia proxy increment \\
JP proxy & massive\_minute & 24 & dxj\_final\_window\_momentum, dxj\_late\_30m\_return, dxj\_late\_60m\_down\_semivar & 0.003484 & 0.041812 & Japan proxy increment \\
JP proxy & JP proxy & 8 & dxj\_range, dxj\_return, ewj\_range & 0.000000 & 0.000000 & Japan proxy increment \\
JP proxy & cross\_market\_derived & 2 & xmarket\_japan\_proxy\_dxj\_spy\_spread\_1d, xmarket\_japan\_proxy\_ewj\_spy\_spread\_1d & 0.000000 & 0.000000 & Japan proxy increment \\
JP only & JP history & 37 & n225\_contract\_month\_cos, n225\_contract\_month\_sin, n225\_day\_parkinson\_var\_lag\_1 & 0.000047 & 0.000581 & Japan/history anchor \\
JP only & J-Quants N225 options & 30 & n225\_option\_atm\_iv\_change\_20\_lag\_1, n225\_option\_atm\_iv\_lag\_1, n225\_option\_atm\_iv\_medium\_lag\_1 & 0.016047 & 0.146341 & Japan/history anchor \\
FRED credit enriched & FRED credit enriched & 4 & fred\_bamlc0a0cm\_diff, fred\_bamlc0a0cm\_level, fred\_bamlh0a0hym2\_diff & 0.623984 & 0.624274 & Macro/credit enrichment \\
massive\_optional & massive\_optional & 2 & uup\_range, uup\_return & 0.000000 & 0.000000 & Options-risk diagnostic \\
calendar\_controls & event\_calendar & 7 & event\_boj\_same\_ose\_session, event\_cpi\_same\_us\_session, event\_days\_since\_previous\_major & 0.000000 & 0.000000 & Supporting control \\
fx\_core & fx\_core & 4 & fx\_observation\_age\_days, fx\_release\_age\_days, fx\_usdjpy\_level & 0.000000 & 0.000000 & Supporting control \\
US core & massive\_daily & 40 & dia\_range, dia\_return, gld\_range & 0.000015 & 0.000581 & U.S. close core \\
US core & cross\_market\_derived & 2 & xmarket\_us\_core\_return\_mean\_1d, xmarket\_us\_sector\_return\_dispersion\_1d & 0.000000 & 0.000000 & U.S. close core \\
fred\_core & cboe\_volatility & 2 & cboe\_vix\_close, cboe\_vix\_range & 0.000000 & 0.000000 & U.S. close core \\
fred\_core & fred\_core & 9 & fred\_dgs10\_diff, fred\_dgs10\_level, fred\_dgs2\_diff & 0.000000 & 0.000000 & U.S. close core \\
fred\_core & cross\_market\_derived & 2 & xmarket\_vix\_shock\_20d, xmarket\_vix\_shock\_zscore\_60d & 0.000000 & 0.000000 & U.S. close core \\
US late session & massive\_minute & 84 & dia\_final\_window\_momentum, dia\_late\_30m\_return, dia\_late\_60m\_down\_semivar & 0.000000 & 0.000000 & U.S. late-session timing \\
\midrule
\multicolumn{7}{l}{\footnotesize Visible notes: predictor-block coverage is an information-transparency summary, not feature admissibility. Timestamp availability and feature-matrix gates are applied before each refit.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>tailrisk_model_inventory_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_model_inventory_table.tex</code>.  
**ARS reading:** Model inventory and construction summary; use for method definitions, not performance claims.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: model_inventory_forecast_construction
\begin{tabular}{llllll}
\toprule
family & examples & information & VaR & ES & role \\
\midrule
Historical & historical quantile; rolling quantile & target history & empirical quantile & empirical tail mean & benchmark floor \\
GARCH/GJR & GARCH-t; GJR-GARCH-t & target history & parametric t & parametric t & econometric floor \\
GARCH-EVT & GJR-GARCH-EVT & target history & filtered POT-GPD & GPD ES & tail benchmark \\
Advanced econometric & CAViaR; CARE; GAS & target history & recursive/score & varies by family & nonblocking benchmark \\
Direct LightGBM & LGBM direct quantile & nested information sets & quantile regression & empirical companion & information ladder \\
LightGBM location-scale & LGBM location-scale empirical & nested information sets & standardized empirical tail & standardized empirical tail & filtered candidate \\
LightGBM POT-GPD & standardized, median/MAD, median/IQR POT-GPD & nested information sets & standardized POT-GPD & GPD ES & filtered EVT candidate \\
\midrule
\multicolumn{6}{l}{\footnotesize Visible notes: inventory table explains forecast construction and paper role. Performance belongs in selected-performance and result-matrix tables.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>benchmark_metrics_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_metrics_table.tex</code>.  
**ARS reading:** Benchmark floor calibration and loss table for the main benchmark comparison.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_level: research_candidate
% loss convention: realized_loss is positive loss for selected tail_side; lower FZ loss is better
\begin{tabular}{lllrrrrr}
\toprule
model & info & side & tail & rows & breach & q_loss & fz_loss \\
\midrule
ewma\_vol\_scaled & Target history & left\_tail & 0.950 & 722 & 0.052632 & 0.001409 & -3.647462 \\
ewma\_vol\_scaled & Target history & right\_tail & 0.950 & 722 & 0.045706 & 0.001342 & -3.656615 \\
garch\_t & Target history & left\_tail & 0.950 & 722 & 0.060942 & 0.001368 & -3.701083 \\
garch\_t & Target history & right\_tail & 0.950 & 722 & 0.041551 & 0.001278 & -3.703374 \\
gas\_t\_location\_scale & Target history & left\_tail & 0.950 & 722 & 0.063712 & 0.001352 & -3.693506 \\
gas\_t\_location\_scale & Target history & right\_tail & 0.950 & 722 & 0.049861 & 0.001307 & -3.668339 \\
gjr\_garch\_evt & Target history & left\_tail & 0.950 & 722 & 0.060942 & 0.001330 & -3.746233 \\
gjr\_garch\_evt & Target history & right\_tail & 0.950 & 722 & 0.058172 & 0.001233 & -3.708574 \\
gjr\_garch\_t & Target history & left\_tail & 0.950 & 722 & 0.070637 & 0.001338 & -3.723459 \\
gjr\_garch\_t & Target history & right\_tail & 0.950 & 722 & 0.042936 & 0.001222 & -3.739711 \\
historical\_quantile & Target history & left\_tail & 0.950 & 722 & 0.055402 & 0.001476 & -3.540661 \\
historical\_quantile & Target history & right\_tail & 0.950 & 722 & 0.069252 & 0.001502 & -3.406776 \\
rolling\_quantile & Target history & left\_tail & 0.950 & 722 & 0.058172 & 0.001481 & -3.524684 \\
rolling\_quantile & Target history & right\_tail & 0.950 & 722 & 0.072022 & 0.001496 & -3.427318 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: candidate artifact; lower FZ loss is better; inference artifacts use block-bootstrap DM; common-sample status is recorded in metrics metadata.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>benchmark_left_tail_risk_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_left_tail_risk_table.tex</code>.  
**ARS reading:** Left-tail benchmark rows.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_level: research_candidate
% loss convention: realized_loss is positive loss for selected tail_side; lower FZ loss is better
\begin{tabular}{lllrrrrr}
\toprule
model & info & side & tail & rows & breach & q_loss & fz_loss \\
\midrule
ewma\_vol\_scaled & Target history & left\_tail & 0.950 & 722 & 0.052632 & 0.001409 & -3.647462 \\
garch\_t & Target history & left\_tail & 0.950 & 722 & 0.060942 & 0.001368 & -3.701083 \\
gas\_t\_location\_scale & Target history & left\_tail & 0.950 & 722 & 0.063712 & 0.001352 & -3.693506 \\
gjr\_garch\_evt & Target history & left\_tail & 0.950 & 722 & 0.060942 & 0.001330 & -3.746233 \\
gjr\_garch\_t & Target history & left\_tail & 0.950 & 722 & 0.070637 & 0.001338 & -3.723459 \\
historical\_quantile & Target history & left\_tail & 0.950 & 722 & 0.055402 & 0.001476 & -3.540661 \\
rolling\_quantile & Target history & left\_tail & 0.950 & 722 & 0.058172 & 0.001481 & -3.524684 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: candidate artifact; lower FZ loss is better; inference artifacts use block-bootstrap DM; common-sample status is recorded in metrics metadata.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>benchmark_right_tail_risk_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/benchmark_right_tail_risk_table.tex</code>.  
**ARS reading:** Right-tail benchmark rows.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_level: research_candidate
% loss convention: realized_loss is positive loss for selected tail_side; lower FZ loss is better
\begin{tabular}{lllrrrrr}
\toprule
model & info & side & tail & rows & breach & q_loss & fz_loss \\
\midrule
ewma\_vol\_scaled & Target history & right\_tail & 0.950 & 722 & 0.045706 & 0.001342 & -3.656615 \\
garch\_t & Target history & right\_tail & 0.950 & 722 & 0.041551 & 0.001278 & -3.703374 \\
gas\_t\_location\_scale & Target history & right\_tail & 0.950 & 722 & 0.049861 & 0.001307 & -3.668339 \\
gjr\_garch\_evt & Target history & right\_tail & 0.950 & 722 & 0.058172 & 0.001233 & -3.708574 \\
gjr\_garch\_t & Target history & right\_tail & 0.950 & 722 & 0.042936 & 0.001222 & -3.739711 \\
historical\_quantile & Target history & right\_tail & 0.950 & 722 & 0.069252 & 0.001502 & -3.406776 \\
rolling\_quantile & Target history & right\_tail & 0.950 & 722 & 0.072022 & 0.001496 & -3.427318 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: candidate artifact; lower FZ loss is better; inference artifacts use block-bootstrap DM; common-sample status is recorded in metrics metadata.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>ml_tail_metrics_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_metrics_table.tex</code>.  
**ARS reading:** Direct LightGBM information-set ladder; read loss changes together with coverage.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_level: research_candidate
% loss convention: realized_loss is positive loss for selected tail_side; lower FZ loss is better
\begin{tabular}{lllrrrrr}
\toprule
model & info & side & tail & rows & breach & q_loss & fz_loss \\
\midrule
LGBM direct quantile & JP only & left\_tail & 0.950 & 527 & 0.081594 & 0.001412 & -3.489349 \\
LGBM direct quantile & JP + US close core & left\_tail & 0.950 & 527 & 0.111954 & 0.001158 & -3.668401 \\
LGBM direct quantile & JP + US close core + JP proxy & left\_tail & 0.950 & 527 & 0.117647 & 0.001114 & -3.868878 \\
LGBM direct quantile & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950 & 527 & 0.117647 & 0.001119 & -3.807595 \\
LGBM direct quantile & JP only & right\_tail & 0.950 & 527 & 0.096774 & 0.001310 & -3.487426 \\
LGBM direct quantile & JP + US close core & right\_tail & 0.950 & 527 & 0.119545 & 0.001252 & -3.486236 \\
LGBM direct quantile & JP + US close core + JP proxy & right\_tail & 0.950 & 527 & 0.115750 & 0.001211 & -3.557463 \\
LGBM direct quantile & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950 & 527 & 0.129032 & 0.001222 & -3.559147 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: candidate artifact; lower FZ loss is better; inference artifacts use block-bootstrap DM; common-sample status is recorded in metrics metadata.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>ml_tail_left_tail_risk_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_left_tail_risk_table.tex</code>.  
**ARS reading:** Left-tail direct LightGBM rows.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_level: research_candidate
% loss convention: realized_loss is positive loss for selected tail_side; lower FZ loss is better
\begin{tabular}{lllrrrrr}
\toprule
model & info & side & tail & rows & breach & q_loss & fz_loss \\
\midrule
LGBM direct quantile & JP only & left\_tail & 0.950 & 527 & 0.081594 & 0.001412 & -3.489349 \\
LGBM direct quantile & JP + US close core & left\_tail & 0.950 & 527 & 0.111954 & 0.001158 & -3.668401 \\
LGBM direct quantile & JP + US close core + JP proxy & left\_tail & 0.950 & 527 & 0.117647 & 0.001114 & -3.868878 \\
LGBM direct quantile & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950 & 527 & 0.117647 & 0.001119 & -3.807595 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: candidate artifact; lower FZ loss is better; inference artifacts use block-bootstrap DM; common-sample status is recorded in metrics metadata.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>ml_tail_right_tail_risk_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_right_tail_risk_table.tex</code>.  
**ARS reading:** Right-tail direct LightGBM rows.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_level: research_candidate
% loss convention: realized_loss is positive loss for selected tail_side; lower FZ loss is better
\begin{tabular}{lllrrrrr}
\toprule
model & info & side & tail & rows & breach & q_loss & fz_loss \\
\midrule
LGBM direct quantile & JP only & right\_tail & 0.950 & 527 & 0.096774 & 0.001310 & -3.487426 \\
LGBM direct quantile & JP + US close core & right\_tail & 0.950 & 527 & 0.119545 & 0.001252 & -3.486236 \\
LGBM direct quantile & JP + US close core + JP proxy & right\_tail & 0.950 & 527 & 0.115750 & 0.001211 & -3.557463 \\
LGBM direct quantile & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950 & 527 & 0.129032 & 0.001222 & -3.559147 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: candidate artifact; lower FZ loss is better; inference artifacts use block-bootstrap DM; common-sample status is recorded in metrics metadata.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>ml_tail_promoted_tail_models_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_promoted_tail_models_table.tex</code>.  
**ARS reading:** Side-specific promoted filtered-tail rows; gated candidates, not a universal ranking.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: side_specific_ml_tail_promotion_gate
\begin{tabular}{lll lrrrrll}
\toprule
role & model & info & side & N & breach & q_loss & fz_loss & DM q & DM FZ \\
\midrule
left promoted & LGBM median/IQR POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & left\_tail & 527 & 0.058824 & 0.000917 & -4.222471 & -0.000236; p=0.028; rej10 & -0.489; p=0.049; rej10 \\
right promoted & LGBM location-scale empirical & JP + US close core + JP proxy & right\_tail & 493 & 0.060852 & 0.001023 & -4.027288 & -0.000239; p=0.026; rej10 & -0.53; p=0.003; rej10 \\
\midrule
\multicolumn{10}{l}{\footnotesize Visible notes: side-specific promotion rows must pass N and VaR-coverage gates and are read with restricted common-sample DM evidence versus the direct-quantile anchor. Negative DM loss differences favor the promoted candidate. This is not a universal model-family ranking.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>tailrisk_selected_model_performance_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_selected_model_performance_table.tex</code>.  
**ARS reading:** Compact selected-row support after gates.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: selected_benchmark_vs_lgbm_main_figure_rows
\begin{tabular}{ll ll lrrrr}
\toprule
group & rank & model & info & side & N & breach & q_loss & fz_loss \\
\midrule
Benchmark & 1 & gjr\_garch\_evt & Target history & left\_tail & 722 & 0.060942 & 0.001330 & -3.746233 \\
Benchmark & 2 & gjr\_garch\_t & Target history & left\_tail & 722 & 0.070637 & 0.001338 & -3.723459 \\
Benchmark & 3 & garch\_t & Target history & left\_tail & 722 & 0.060942 & 0.001368 & -3.701083 \\
LGBM & 1 & LGBM median/MAD POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 474 & 0.067511 & 0.000966 & -4.310340 \\
LGBM & 2 & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 474 & 0.073840 & 0.000980 & -4.281130 \\
LGBM & 3 & LGBM median/MAD POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & left\_tail & 474 & 0.065401 & 0.000993 & -4.269625 \\
Benchmark & 1 & gjr\_garch\_t & Target history & right\_tail & 722 & 0.042936 & 0.001222 & -3.739711 \\
Benchmark & 2 & gjr\_garch\_evt & Target history & right\_tail & 722 & 0.058172 & 0.001233 & -3.708574 \\
Benchmark & 3 & garch\_t & Target history & right\_tail & 722 & 0.041551 & 0.001278 & -3.703374 \\
LGBM & 1 & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001034 & -4.029703 \\
LGBM & 2 & LGBM location-scale empirical & JP + US close core + JP proxy & right\_tail & 493 & 0.060852 & 0.001023 & -4.027288 \\
LGBM & 3 & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001032 & -4.020205 \\
\midrule
\multicolumn{9}{l}{\footnotesize Visible notes: selected rows use the deterministic main-figure rule: N >= 450, absolute VaR coverage error <= 0.025, then rank by FZ loss and quantile loss within each broad group and tail side. Full per-model results are exported separately for appendix use.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>appendix_benchmark_all_models_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_benchmark_all_models_table.tex</code>.  
**ARS reading:** Full benchmark scan for auditability.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: full_per_model_appendix
\begin{tabular}{lll lrrrrr}
\toprule
group & model & info & side & N & breach & q_loss & fz_loss & severity \\
\midrule
Benchmark & care\_expectile\_asymmetric\_slope & Target history & left\_tail & 627 & 0.078150 & 0.001440 & -3.621661 & 0.007879 \\
Benchmark & care\_expectile\_sav & Target history & left\_tail & 620 & 0.067742 & 0.001456 & -3.607506 & 0.008946 \\
Benchmark & caviar\_asymmetric\_slope & Target history & left\_tail & 508 & 0.070866 & 0.001564 & -3.532426 & 0.009410 \\
Benchmark & caviar\_sav & Target history & left\_tail & 498 & 0.058233 & 0.001568 & -3.540070 & 0.011676 \\
Benchmark & ewma\_vol\_scaled & Target history & left\_tail & 722 & 0.052632 & 0.001409 & -3.647462 & 0.008636 \\
Benchmark & garch\_t & Target history & left\_tail & 722 & 0.060942 & 0.001368 & -3.701083 & 0.008609 \\
Benchmark & gas\_t\_location\_scale & Target history & left\_tail & 722 & 0.063712 & 0.001352 & -3.693506 & 0.008670 \\
Benchmark & gas\_t\_pot\_gpd & Target history & left\_tail & 223 & 0.044843 & 0.001277 & -3.789288 & 0.006754 \\
Benchmark & gjr\_garch\_evt & Target history & left\_tail & 722 & 0.060942 & 0.001330 & -3.746233 & 0.007631 \\
Benchmark & gjr\_garch\_t & Target history & left\_tail & 722 & 0.070637 & 0.001338 & -3.723459 & 0.007359 \\
Benchmark & historical\_quantile & Target history & left\_tail & 722 & 0.055402 & 0.001476 & -3.540661 & 0.012140 \\
Benchmark & rolling\_quantile & Target history & left\_tail & 722 & 0.058172 & 0.001481 & -3.524684 & 0.011683 \\
Benchmark & care\_expectile\_asymmetric\_slope & Target history & right\_tail & 679 & 0.079529 & 0.001327 & -3.531389 & 0.008670 \\
Benchmark & care\_expectile\_sav & Target history & right\_tail & 679 & 0.085420 & 0.001372 & -3.474738 & 0.008198 \\
Benchmark & caviar\_asymmetric\_slope & Target history & right\_tail & 504 & 0.067460 & 0.001494 & -3.466189 & 0.010720 \\
Benchmark & caviar\_sav & Target history & right\_tail & 504 & 0.063492 & 0.001558 & -3.407822 & 0.011629 \\
Benchmark & ewma\_vol\_scaled & Target history & right\_tail & 722 & 0.045706 & 0.001342 & -3.656615 & 0.009787 \\
Benchmark & garch\_t & Target history & right\_tail & 722 & 0.041551 & 0.001278 & -3.703374 & 0.010888 \\
Benchmark & gas\_t\_location\_scale & Target history & right\_tail & 722 & 0.049861 & 0.001307 & -3.668339 & 0.010514 \\
Benchmark & gas\_t\_pot\_gpd & Target history & right\_tail & 223 & 0.085202 & 0.001785 & -3.033734 & 0.012794 \\
Benchmark & gjr\_garch\_evt & Target history & right\_tail & 722 & 0.058172 & 0.001233 & -3.708574 & 0.008988 \\
Benchmark & gjr\_garch\_t & Target history & right\_tail & 722 & 0.042936 & 0.001222 & -3.739711 & 0.010272 \\
Benchmark & historical\_quantile & Target history & right\_tail & 722 & 0.069252 & 0.001502 & -3.406776 & 0.012003 \\
Benchmark & rolling\_quantile & Target history & right\_tail & 722 & 0.072022 & 0.001496 & -3.427318 & 0.011480 \\
\midrule
\multicolumn{9}{l}{\footnotesize Visible notes: appendix table; lower quantile/FZ loss and lower exceedance severity are better, while VaR breach should be read relative to the nominal 5\% exception rate.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>appendix_lgbm_all_models_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_lgbm_all_models_table.tex</code>.  
**ARS reading:** Full LightGBM candidate scan for auditability; not a leaderboard.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: full_per_model_appendix
\begin{tabular}{lll lrrrrr}
\toprule
group & model & info & side & N & breach & q_loss & fz_loss & severity \\
\midrule
LGBM & LGBM direct quantile & JP only & left\_tail & 554 & 0.079422 & 0.001404 & -3.475021 & 0.008940 \\
LGBM & LGBM direct quantile & JP + US close core & left\_tail & 554 & 0.108303 & 0.001150 & -3.678881 & 0.006263 \\
LGBM & LGBM direct quantile & JP + US close core + JP proxy & left\_tail & 527 & 0.117647 & 0.001114 & -3.868878 & 0.005511 \\
LGBM & LGBM direct quantile & JP + US close core + JP proxy + Asia proxy & left\_tail & 527 & 0.117647 & 0.001119 & -3.807595 & 0.005581 \\
LGBM & LGBM location-scale empirical & JP only & left\_tail & 508 & 0.053150 & 0.001487 & -3.554176 & 0.009866 \\
LGBM & LGBM location-scale empirical & JP + US close core & left\_tail & 506 & 0.061265 & 0.000988 & -4.050495 & 0.005722 \\
LGBM & LGBM location-scale empirical & JP + US close core + JP proxy & left\_tail & 492 & 0.065041 & 0.000988 & -4.142323 & 0.005532 \\
LGBM & LGBM location-scale empirical & JP + US close core + JP proxy + Asia proxy & left\_tail & 492 & 0.071138 & 0.000986 & -4.058506 & 0.004820 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP only & left\_tail & 554 & 0.036101 & 0.001383 & -3.679215 & 0.010818 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP + US close core & left\_tail & 553 & 0.052441 & 0.000965 & -4.141200 & 0.006841 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 526 & 0.047529 & 0.000904 & -4.198353 & 0.006541 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & left\_tail & 527 & 0.058824 & 0.000917 & -4.222471 & 0.005493 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP only & left\_tail & 554 & 0.036101 & 0.001383 & -3.684175 & 0.010625 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP + US close core & left\_tail & 553 & 0.052441 & 0.000960 & -4.113223 & 0.006824 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 527 & 0.047438 & 0.000907 & -4.261671 & 0.006703 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy + Asia proxy & left\_tail & 527 & 0.058824 & 0.000914 & -4.213620 & 0.005463 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP only & left\_tail & 484 & 0.051653 & 0.001490 & -3.597317 & 0.011229 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP + US close core & left\_tail & 484 & 0.064050 & 0.001067 & -4.119314 & 0.008183 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 474 & 0.067511 & 0.000966 & -4.310340 & 0.006367 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & left\_tail & 474 & 0.065401 & 0.000993 & -4.269625 & 0.006902 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP only & left\_tail & 484 & 0.051653 & 0.001491 & -3.598519 & 0.011303 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core & left\_tail & 484 & 0.066116 & 0.001071 & -4.146720 & 0.008140 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 474 & 0.073840 & 0.000980 & -4.281130 & 0.006233 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy + Asia proxy & left\_tail & 474 & 0.073840 & 0.001005 & -4.259353 & 0.006443 \\
LGBM & LGBM POT-GPD plain MLE & JP only & left\_tail & 484 & 0.055785 & 0.001520 & -3.525293 & 0.009821 \\
LGBM & LGBM POT-GPD plain MLE & JP + US close core & left\_tail & 482 & 0.058091 & 0.000997 & -4.080408 & 0.005945 \\
LGBM & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 473 & 0.059197 & 0.000990 & -4.151901 & 0.005868 \\
LGBM & LGBM POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & left\_tail & 473 & 0.065539 & 0.000987 & -4.090892 & 0.005035 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP only & left\_tail & 484 & 0.055785 & 0.001516 & -3.511702 & 0.009658 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP + US close core & left\_tail & 483 & 0.064182 & 0.000998 & -4.074074 & 0.005680 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 473 & 0.063425 & 0.000998 & -4.131158 & 0.005952 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy + Asia proxy & left\_tail & 473 & 0.065539 & 0.000998 & -4.056911 & 0.005497 \\
LGBM & LGBM direct quantile & JP only & right\_tail & 554 & 0.093863 & 0.001273 & -3.530485 & 0.007334 \\
LGBM & LGBM direct quantile & JP + US close core & right\_tail & 554 & 0.113718 & 0.001211 & -3.548401 & 0.006614 \\
LGBM & LGBM direct quantile & JP + US close core + JP proxy & right\_tail & 527 & 0.115750 & 0.001211 & -3.557463 & 0.006448 \\
LGBM & LGBM direct quantile & JP + US close core + JP proxy + Asia proxy & right\_tail & 527 & 0.129032 & 0.001222 & -3.559147 & 0.005853 \\
LGBM & LGBM location-scale empirical & JP only & right\_tail & 508 & 0.043307 & 0.001346 & -3.573913 & 0.010108 \\
LGBM & LGBM location-scale empirical & JP + US close core & right\_tail & 505 & 0.061386 & 0.001047 & -3.971715 & 0.006370 \\
LGBM & LGBM location-scale empirical & JP + US close core + JP proxy & right\_tail & 493 & 0.060852 & 0.001023 & -4.027288 & 0.006287 \\
LGBM & LGBM location-scale empirical & JP + US close core + JP proxy + Asia proxy & right\_tail & 492 & 0.063008 & 0.001085 & -3.910528 & 0.006984 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP only & right\_tail & 554 & 0.030686 & 0.001211 & -3.756111 & 0.010127 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP + US close core & right\_tail & 554 & 0.054152 & 0.001048 & -3.975248 & 0.006710 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 526 & 0.047529 & 0.001041 & -3.929021 & 0.007819 \\
LGBM & LGBM median/IQR POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & right\_tail & 527 & 0.060721 & 0.001046 & -3.923889 & 0.006409 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP only & right\_tail & 554 & 0.032491 & 0.001201 & -3.762414 & 0.010154 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP + US close core & right\_tail & 554 & 0.055957 & 0.001050 & -3.963747 & 0.006783 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 527 & 0.051233 & 0.001048 & -3.882784 & 0.007748 \\
LGBM & LGBM median/IQR POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy + Asia proxy & right\_tail & 527 & 0.058824 & 0.001050 & -3.942804 & 0.006886 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP only & right\_tail & 484 & 0.051653 & 0.001330 & -3.610920 & 0.009792 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP + US close core & right\_tail & 484 & 0.072314 & 0.001120 & -3.998127 & 0.007624 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 473 & 0.078224 & 0.001082 & -4.085941 & 0.006835 \\
LGBM & LGBM median/MAD POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & right\_tail & 473 & 0.076110 & 0.001125 & -3.923032 & 0.007709 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP only & right\_tail & 484 & 0.059917 & 0.001334 & -3.613854 & 0.008934 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core & right\_tail & 484 & 0.072314 & 0.001119 & -3.989896 & 0.007703 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 473 & 0.078224 & 0.001085 & -4.057930 & 0.006973 \\
LGBM & LGBM median/MAD POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy + Asia proxy & right\_tail & 473 & 0.076110 & 0.001126 & -3.921147 & 0.007786 \\
LGBM & LGBM POT-GPD plain MLE & JP only & right\_tail & 484 & 0.037190 & 0.001369 & -3.576374 & 0.011399 \\
LGBM & LGBM POT-GPD plain MLE & JP + US close core & right\_tail & 482 & 0.051867 & 0.001052 & -3.982679 & 0.007128 \\
LGBM & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001034 & -4.029703 & 0.006603 \\
LGBM & LGBM POT-GPD plain MLE & JP + US close core + JP proxy + Asia proxy & right\_tail & 473 & 0.057082 & 0.001090 & -3.924620 & 0.007419 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP only & right\_tail & 484 & 0.041322 & 0.001363 & -3.583150 & 0.010602 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP + US close core & right\_tail & 483 & 0.053830 & 0.001047 & -3.983169 & 0.006934 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001032 & -4.020205 & 0.006702 \\
LGBM & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy + Asia proxy & right\_tail & 474 & 0.056962 & 0.001085 & -3.929750 & 0.007375 \\
\midrule
\multicolumn{9}{l}{\footnotesize Visible notes: appendix table; lower quantile/FZ loss and lower exceedance severity are better, while VaR breach should be read relative to the nominal 5\% exception rate.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>ml_tail_result_matrix_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_result_matrix_table.tex</code>.  
**ARS reading:** Restricted common-sample result matrix.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% claim_scope: restricted_model_comparison_not_primary unless stated otherwise
\begin{tabular}{lllllrrr}
\toprule
family & axis & loss & info/model & side & tail & N & exc & metric \\
\midrule
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 527 & 51 & 0.046774 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 527 & 43 & 0.031594 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 490 & 22 & 0.005102 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 490 & 26 & 0.003061 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 526 & 19 & 0.013878 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 526 & 17 & 0.017681 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 526 & 19 & 0.013878 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 527 & 18 & 0.015844 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 474 & 24 & 0.000633 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 472 & 25 & 0.002966 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 472 & 29 & 0.011441 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 474 & 24 & 0.000633 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 471 & 18 & 0.011783 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 472 & 26 & 0.005085 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & right\_tail & 0.950000 & 473 & 20 & 0.007717 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP only & left\_tail & 0.950000 & 472 & 26 & 0.005085 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 527 & 59 & 0.061954 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 527 & 63 & 0.069545 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 490 & 31 & 0.013265 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 490 & 30 & 0.011224 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 526 & 28 & 0.003232 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 526 & 30 & 0.007034 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 527 & 31 & 0.008824 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 526 & 28 & 0.003232 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 472 & 35 & 0.024153 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 474 & 30 & 0.013291 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 472 & 35 & 0.024153 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 474 & 31 & 0.015401 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 471 & 25 & 0.003079 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 472 & 27 & 0.007203 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & right\_tail & 0.950000 & 473 & 26 & 0.004968 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core & left\_tail & 0.950000 & 472 & 29 & 0.011441 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 527 & 62 & 0.067647 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 527 & 61 & 0.065750 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 490 & 32 & 0.015306 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 490 & 30 & 0.011224 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 526 & 25 & 0.002471 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 526 & 25 & 0.002471 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 526 & 25 & 0.002471 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 527 & 27 & 0.001233 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 472 & 37 & 0.028390 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 474 & 32 & 0.017511 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 474 & 35 & 0.023840 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 472 & 37 & 0.028390 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 471 & 27 & 0.007325 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 472 & 28 & 0.009322 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy & left\_tail & 0.950000 & 472 & 30 & 0.013559 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 527 & 62 & 0.067647 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 527 & 68 & 0.079032 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 490 & 35 & 0.021429 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 490 & 31 & 0.013265 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 526 & 31 & 0.008935 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 526 & 31 & 0.008935 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 527 & 31 & 0.008824 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 526 & 31 & 0.008935 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 472 & 36 & 0.026271 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 474 & 31 & 0.015401 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 472 & 36 & 0.026271 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 474 & 35 & 0.023840 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 472 & 31 & 0.015678 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 471 & 27 & 0.007325 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 472 & 31 & 0.015678 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 527 & 51 & -3.487426 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 527 & 43 & -3.489349 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 490 & 22 & -3.549508 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 490 & 26 & -3.550527 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 526 & 19 & -3.672430 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 526 & 17 & -3.729774 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 526 & 19 & -3.678126 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 527 & 18 & -3.737113 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 472 & 25 & -3.597774 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 474 & 24 & -3.619079 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 472 & 29 & -3.601361 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 474 & 24 & -3.620220 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 471 & 18 & -3.562014 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 472 & 26 & -3.528654 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & left\_tail & 0.950000 & 472 & 26 & -3.514928 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP only & right\_tail & 0.950000 & 473 & 20 & -3.571813 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 527 & 59 & -3.668401 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 527 & 63 & -3.486236 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 490 & 30 & -4.024023 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 490 & 31 & -3.949447 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 526 & 30 & -3.948353 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 526 & 28 & -4.135784 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 526 & 28 & -4.108180 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 527 & 31 & -3.941738 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 474 & 30 & -4.130611 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 472 & 35 & -3.966238 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 472 & 35 & -3.959736 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 474 & 31 & -4.159081 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 471 & 25 & -3.967524 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 472 & 27 & -4.085769 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & right\_tail & 0.950000 & 473 & 26 & -3.972914 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core & left\_tail & 0.950000 & 472 & 29 & -4.078464 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 527 & 61 & -3.557463 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 527 & 62 & -3.868878 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 490 & 30 & -4.008295 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 490 & 32 & -4.128110 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 526 & 25 & -4.198353 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 526 & 25 & -3.929021 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 527 & 27 & -3.882784 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 526 & 25 & -4.252013 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 472 & 37 & -4.060044 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 474 & 32 & -4.310340 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 474 & 35 & -4.281130 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 472 & 37 & -4.041000 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 471 & 27 & -4.010399 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 472 & 28 & -4.146660 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 472 & 30 & -4.126075 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 473 & 27 & -4.018646 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 527 & 68 & -3.559147 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 527 & 62 & -3.807595 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 490 & 35 & -4.044514 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 490 & 31 & -3.898080 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 526 & 31 & -3.956723 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 526 & 31 & -4.205621 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 527 & 31 & -3.942804 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 526 & 31 & -4.188953 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 472 & 36 & -3.909397 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 474 & 31 & -4.269625 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 472 & 36 & -3.911851 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 474 & 35 & -4.259353 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 471 & 27 & -3.912137 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 472 & 31 & -4.082321 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 472 & 31 & -4.050321 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 473 & 27 & -3.925779 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 527 & 43 & 0.001412 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 527 & 51 & 0.001310 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 490 & 26 & 0.001488 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 490 & 22 & 0.001362 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 526 & 17 & 0.001239 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 526 & 19 & 0.001393 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 526 & 19 & 0.001393 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 527 & 18 & 0.001229 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 472 & 25 & 0.001337 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 474 & 24 & 0.001478 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 474 & 24 & 0.001479 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 472 & 29 & 0.001342 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 472 & 26 & 0.001516 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 471 & 18 & 0.001376 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & left\_tail & 0.950000 & 472 & 26 & 0.001513 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP only & right\_tail & 0.950000 & 473 & 20 & 0.001372 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 527 & 63 & 0.001252 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 527 & 59 & 0.001158 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 490 & 31 & 0.001061 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 490 & 30 & 0.000990 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 526 & 30 & 0.001074 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 526 & 28 & 0.000965 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 526 & 28 & 0.000960 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 527 & 31 & 0.001076 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 472 & 35 & 0.001131 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 474 & 30 & 0.001059 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 474 & 31 & 0.001063 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 472 & 35 & 0.001130 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 471 & 25 & 0.001059 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 472 & 27 & 0.000992 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & right\_tail & 0.950000 & 473 & 26 & 0.001054 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core & left\_tail & 0.950000 & 472 & 29 & 0.000994 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 527 & 62 & 0.001114 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 527 & 61 & 0.001211 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 490 & 30 & 0.001024 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 490 & 32 & 0.000990 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 526 & 25 & 0.000904 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 526 & 25 & 0.001041 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 527 & 27 & 0.001048 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 526 & 25 & 0.000908 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 474 & 32 & 0.000966 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 472 & 37 & 0.001082 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 474 & 35 & 0.000980 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 472 & 37 & 0.001085 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 472 & 28 & 0.000991 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 471 & 27 & 0.001034 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & right\_tail & 0.950000 & 473 & 27 & 0.001032 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy & left\_tail & 0.950000 & 472 & 30 & 0.000998 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 527 & 62 & 0.001119 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 527 & 68 & 0.001222 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 490 & 31 & 0.001086 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 490 & 35 & 0.000988 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 526 & 31 & 0.000918 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 526 & 31 & 0.001045 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 527 & 31 & 0.001050 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 526 & 31 & 0.000915 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 472 & 36 & 0.001126 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 474 & 31 & 0.000993 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 474 & 35 & 0.001005 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 472 & 36 & 0.001127 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 472 & 31 & 0.000989 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 471 & 27 & 0.001091 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & left\_tail & 0.950000 & 472 & 31 & 0.001000 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & JP + US close core + JP proxy + Asia proxy & right\_tail & 0.950000 & 473 & 27 & 0.001086 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & right\_tail & 0.950000 & 484 & 46 & 0.045041 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & left\_tail & 0.950000 & 484 & 43 & 0.038843 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & right\_tail & 0.950000 & 484 & 20 & 0.008678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & left\_tail & 0.950000 & 484 & 27 & 0.005785 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 14 & 0.021074 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 20 & 0.008678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 15 & 0.019008 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 20 & 0.008678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 25 & 0.001653 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 25 & 0.001653 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 25 & 0.001653 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 29 & 0.009917 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 27 & 0.005785 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 18 & 0.012810 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 27 & 0.005785 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 20 & 0.008678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & left\_tail & 0.950000 & 481 & 58 & 0.070582 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & right\_tail & 0.950000 & 482 & 58 & 0.070332 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & left\_tail & 0.950000 & 481 & 29 & 0.010291 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & right\_tail & 0.950000 & 482 & 26 & 0.003942 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 27 & 0.006133 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 28 & 0.008091 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 29 & 0.010166 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 27 & 0.006133 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 31 & 0.014449 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 35 & 0.022614 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 32 & 0.016528 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 35 & 0.022614 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 28 & 0.008212 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 25 & 0.001867 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 30 & 0.012370 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 26 & 0.003942 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & left\_tail & 0.950000 & 472 & 60 & 0.077119 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & right\_tail & 0.950000 & 473 & 56 & 0.068393 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & left\_tail & 0.950000 & 472 & 30 & 0.013559 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 23 & 0.001271 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 23 & 0.001374 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 23 & 0.001271 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 23 & 0.001374 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 37 & 0.028224 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 32 & 0.017797 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 35 & 0.024153 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 37 & 0.028224 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 28 & 0.009322 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 30 & 0.013559 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & right\_tail & 0.950000 & 473 & 63 & 0.083192 \\
tail\_model\_family & model\_family & var\_coverage & LGBM direct quantile & left\_tail & 0.950000 & 472 & 60 & 0.077119 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
tail\_model\_family & model\_family & var\_coverage & LGBM location-scale empirical & left\_tail & 0.950000 & 472 & 33 & 0.019915 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 29 & 0.011441 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 29 & 0.011311 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 29 & 0.011441 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 28 & 0.009197 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 36 & 0.026110 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 31 & 0.015678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 35 & 0.024153 \\
tail\_model\_family & model\_family & var\_coverage & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 36 & 0.026110 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 31 & 0.015678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 31 & 0.015678 \\
tail\_model\_family & model\_family & var\_coverage & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 27 & 0.007082 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & left\_tail & 0.950000 & 484 & 43 & -3.335044 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & right\_tail & 0.950000 & 484 & 46 & -3.474154 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 484 & 27 & -3.522673 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 484 & 20 & -3.582125 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 20 & -3.615098 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 14 & -3.698376 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 20 & -3.623840 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 15 & -3.705671 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 25 & -3.597317 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 25 & -3.610920 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 29 & -3.613854 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 25 & -3.598519 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 27 & -3.525293 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 18 & -3.576374 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 20 & -3.583150 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 27 & -3.511702 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & left\_tail & 0.950000 & 481 & 58 & -3.494609 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & right\_tail & 0.950000 & 482 & 58 & -3.431213 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 481 & 29 & -4.055239 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 482 & 26 & -3.986638 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 27 & -4.048051 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 28 & -3.918221 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 27 & -4.018116 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 29 & -3.906149 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 31 & -4.100194 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 35 & -3.986650 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 35 & -3.978676 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 32 & -4.130774 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 25 & -3.982679 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 28 & -4.073659 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 26 & -3.967533 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 30 & -4.065686 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & right\_tail & 0.950000 & 473 & 56 & -3.494095 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & left\_tail & 0.950000 & 472 & 60 & -3.755112 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 473 & 27 & -4.023826 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 472 & 30 & -4.139523 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 23 & -3.873403 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 23 & -4.169985 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 23 & -3.876862 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 23 & -4.222181 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 32 & -4.301425 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 37 & -4.085941 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 37 & -4.057930 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 35 & -4.272297 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 28 & -4.148175 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 27 & -4.018017 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 27 & -4.012614 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 30 & -4.128311 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & right\_tail & 0.950000 & 473 & 63 & -3.484112 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM direct quantile & left\_tail & 0.950000 & 472 & 60 & -3.680038 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 472 & 33 & -4.042856 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 473 & 27 & -3.932419 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 29 & -4.168704 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 29 & -3.926450 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 29 & -4.158739 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 28 & -3.926228 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 31 & -4.260317 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 36 & -3.923032 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 36 & -3.921147 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 35 & -4.251191 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 31 & -4.082373 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 27 & -3.924620 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 31 & -4.048355 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 27 & -3.912173 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & left\_tail & 0.950000 & 484 & 43 & 0.001509 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & right\_tail & 0.950000 & 484 & 46 & 0.001344 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 484 & 20 & 0.001358 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 484 & 27 & 0.001516 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 20 & 0.001463 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 14 & 0.001279 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 20 & 0.001463 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 15 & 0.001268 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 25 & 0.001490 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 25 & 0.001330 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 25 & 0.001491 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 29 & 0.001334 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 484 & 27 & 0.001520 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 484 & 18 & 0.001369 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 484 & 27 & 0.001516 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 484 & 20 & 0.001363 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & right\_tail & 0.950000 & 482 & 58 & 0.001301 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & left\_tail & 0.950000 & 481 & 58 & 0.001246 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 482 & 26 & 0.001052 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 481 & 29 & 0.001002 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 28 & 0.001106 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 27 & 0.001028 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 29 & 0.001110 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 27 & 0.001022 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 35 & 0.001121 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 31 & 0.001070 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 35 & 0.001121 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 32 & 0.001074 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 482 & 25 & 0.001052 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 481 & 28 & 0.000998 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 482 & 26 & 0.001048 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 481 & 30 & 0.001000 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & left\_tail & 0.950000 & 472 & 60 & 0.001186 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & right\_tail & 0.950000 & 473 & 56 & 0.001267 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 472 & 30 & 0.000999 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 473 & 27 & 0.001028 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 23 & 0.001078 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 23 & 0.000942 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 23 & 0.000944 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 23 & 0.001078 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 37 & 0.001082 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 32 & 0.000968 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 37 & 0.001085 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 35 & 0.000982 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 28 & 0.000991 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 27 & 0.001035 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 27 & 0.001033 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 30 & 0.000998 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & left\_tail & 0.950000 & 472 & 60 & 0.001194 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM direct quantile & right\_tail & 0.950000 & 473 & 63 & 0.001283 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & left\_tail & 0.950000 & 472 & 33 & 0.000999 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM location-scale empirical & right\_tail & 0.950000 & 473 & 27 & 0.001089 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 29 & 0.001077 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 29 & 0.000958 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 28 & 0.001080 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 29 & 0.000954 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 31 & 0.000995 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 36 & 0.001125 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 35 & 0.001007 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 36 & 0.001126 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & left\_tail & 0.950000 & 472 & 31 & 0.000989 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD plain MLE & right\_tail & 0.950000 & 473 & 27 & 0.001090 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & left\_tail & 0.950000 & 472 & 31 & 0.001000 \\
tail\_model\_family & model\_family & var\_quantile\_loss & LGBM POT-GPD UniBM block-maxima shape & right\_tail & 0.950000 & 473 & 27 & 0.001086 \\
\midrule
\multicolumn{9}{l}{\footnotesize Visible notes: restricted result matrix; lower metric is better for quantile loss, FZ loss, and absolute coverage error; block-bootstrap DM appears only when registered sample and exception gates pass; these rows do not replace the primary ML table.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>ml_tail_result_matrix_summary_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/ml_tail_result_matrix_summary_table.tex</code>.  
**ARS reading:** Gate summary for the restricted result matrix.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: result_matrix_sample_and_inference_gate_summary
\begin{tabular}{lllllrrrr}
\toprule
family & axis & loss & side & sample & N & joint exc & DM \\
\midrule
information\_set\_ladder & information\_set\_increment & var\_coverage & right\_tail & restricted\_tail\_model\_common\_sample & 471--527 & 34--80 & 0/24 \\
information\_set\_ladder & information\_set\_increment & var\_coverage & left\_tail & restricted\_tail\_model\_common\_sample & 472--527 & 46--80 & 0/24 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & right\_tail & restricted\_tail\_model\_common\_sample & 471--527 & 34--80 & 24/24 \\
information\_set\_ladder & information\_set\_increment & var\_es\_fz\_loss & left\_tail & restricted\_tail\_model\_common\_sample & 472--527 & 46--80 & 24/24 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & right\_tail & restricted\_tail\_model\_common\_sample & 471--527 & 34--80 & 24/24 \\
information\_set\_ladder & information\_set\_increment & var\_quantile\_loss & left\_tail & restricted\_tail\_model\_common\_sample & 472--527 & 46--80 & 24/24 \\
tail\_model\_family & model\_family & var\_coverage & right\_tail & restricted\_tail\_model\_common\_sample & 473--484 & 49--69 & 0/28 \\
tail\_model\_family & model\_family & var\_coverage & left\_tail & restricted\_tail\_model\_common\_sample & 472--484 & 47--70 & 0/28 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & right\_tail & restricted\_tail\_model\_common\_sample & 473--484 & 49--69 & 28/28 \\
tail\_model\_family & model\_family & var\_es\_fz\_loss & left\_tail & restricted\_tail\_model\_common\_sample & 472--484 & 47--70 & 28/28 \\
tail\_model\_family & model\_family & var\_quantile\_loss & right\_tail & restricted\_tail\_model\_common\_sample & 473--484 & 49--69 & 28/28 \\
tail\_model\_family & model\_family & var\_quantile\_loss & left\_tail & restricted\_tail\_model\_common\_sample & 472--484 & 47--70 & 28/28 \\
\midrule
\multicolumn{8}{l}{\footnotesize Visible notes: VaR-only and VaR-ES loss families are separated. Restricted samples are not primary evidence. DM counts show how many registered inference records passed their sample and exception gates.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>tailrisk_dm_summary_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_dm_summary_table.tex</code>.  
**ARS reading:** Compact paired DM summary; negative loss differences favor the candidate.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: headline_dm_paired_inference_summary
\begin{tabular}{lllrrl}
\toprule
comparison & side & loss & diff & DM p & status \\
\midrule
JP only -> +US close & left\_tail & var\_es\_fz\_loss & -0.179052 & 0.194000 & ok\_block\_bootstrap\_dm \\
Direct quantile -> promoted ML-tail & left\_tail & var\_es\_fz\_loss & -0.488666 & 0.049000 & ok\_block\_bootstrap\_dm \\
Benchmark floor -> promoted ML-tail & left\_tail & var\_es\_fz\_loss &  &  & unavailable\_no\_registered\_cross\_suite\_dm \\
JP only -> +US close & right\_tail & var\_es\_fz\_loss & 0.001190 & 0.510000 & ok\_block\_bootstrap\_dm \\
Direct quantile -> promoted ML-tail & right\_tail & var\_es\_fz\_loss & -0.529731 & 0.003000 & ok\_block\_bootstrap\_dm \\
Benchmark floor -> promoted ML-tail & right\_tail & var\_es\_fz\_loss &  &  & unavailable\_no\_registered\_cross\_suite\_dm \\
\midrule
\multicolumn{6}{l}{\footnotesize Visible notes: negative loss differences favor the candidate. Benchmark-vs-ML cross-suite inference is reported as unavailable unless a registered cross-suite DM artifact exists.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>tailrisk_es_severity_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_es_severity_table.tex</code>.  
**ARS reading:** Conditional-on-exception ES severity diagnostic.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: exceedance_severity_diagnostic
\begin{tabular}{lllllrrrr}
\toprule
suite & scope & model & side & info & N & exc & severity & delta \\
\midrule
benchmark & primary & ewma\_vol\_scaled & left\_tail & Target history & 722 & 38 & 0.008636 & 0.000000 \\
benchmark & primary & ewma\_vol\_scaled & right\_tail & Target history & 722 & 33 & 0.009787 & 0.000000 \\
benchmark & primary & garch\_t & left\_tail & Target history & 722 & 44 & 0.008609 & 0.000000 \\
benchmark & primary & garch\_t & right\_tail & Target history & 722 & 30 & 0.010888 & 0.000000 \\
benchmark & primary & gas\_t\_location\_scale & left\_tail & Target history & 722 & 46 & 0.008670 & 0.000000 \\
benchmark & primary & gas\_t\_location\_scale & right\_tail & Target history & 722 & 36 & 0.010514 & 0.000000 \\
benchmark & primary & gjr\_garch\_evt & left\_tail & Target history & 722 & 44 & 0.007631 & 0.000000 \\
benchmark & primary & gjr\_garch\_evt & right\_tail & Target history & 722 & 42 & 0.008988 & 0.000000 \\
benchmark & primary & gjr\_garch\_t & left\_tail & Target history & 722 & 51 & 0.007359 & 0.000000 \\
benchmark & primary & gjr\_garch\_t & right\_tail & Target history & 722 & 31 & 0.010272 & 0.000000 \\
benchmark & primary & historical\_quantile & left\_tail & Target history & 722 & 40 & 0.012140 & 0.000000 \\
benchmark & primary & historical\_quantile & right\_tail & Target history & 722 & 50 & 0.012003 & 0.000000 \\
benchmark & primary & rolling\_quantile & left\_tail & Target history & 722 & 42 & 0.011683 & 0.000000 \\
benchmark & primary & rolling\_quantile & right\_tail & Target history & 722 & 52 & 0.011480 & 0.000000 \\
ml\_tail & primary & LGBM direct quantile & left\_tail & JP only & 527 & 43 & 0.008741 & 0.000000 \\
ml\_tail & primary & LGBM direct quantile & left\_tail & JP + US close core & 527 & 59 & 0.006086 & 0.002655 \\
ml\_tail & primary & LGBM direct quantile & left\_tail & JP + US close core + JP proxy & 527 & 62 & 0.005511 & 0.003230 \\
ml\_tail & primary & LGBM direct quantile & left\_tail & JP + US close core + JP proxy + Asia proxy & 527 & 62 & 0.005581 & 0.003160 \\
ml\_tail & primary & LGBM direct quantile & right\_tail & JP only & 527 & 51 & 0.007417 & 0.000000 \\
ml\_tail & primary & LGBM direct quantile & right\_tail & JP + US close core & 527 & 63 & 0.006614 & 0.000803 \\
ml\_tail & primary & LGBM direct quantile & right\_tail & JP + US close core + JP proxy & 527 & 61 & 0.006448 & 0.000968 \\
ml\_tail & primary & LGBM direct quantile & right\_tail & JP + US close core + JP proxy + Asia proxy & 527 & 68 & 0.005853 & 0.001564 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & left\_tail & JP only & 508 & 27 & 0.009866 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & left\_tail & JP + US close core & 506 & 31 & 0.005722 & 0.004144 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & left\_tail & JP + US close core + JP proxy & 492 & 32 & 0.005532 & 0.004333 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & left\_tail & JP + US close core + JP proxy + Asia proxy & 492 & 35 & 0.004820 & 0.005045 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & right\_tail & JP only & 508 & 22 & 0.010108 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & right\_tail & JP + US close core & 505 & 31 & 0.006370 & 0.003738 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & right\_tail & JP + US close core + JP proxy & 493 & 30 & 0.006287 & 0.003821 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM location-scale empirical & right\_tail & JP + US close core + JP proxy + Asia proxy & 492 & 31 & 0.006984 & 0.003124 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & left\_tail & JP only & 554 & 20 & 0.010818 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & left\_tail & JP + US close core & 553 & 29 & 0.006841 & 0.003977 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & left\_tail & JP + US close core + JP proxy & 526 & 25 & 0.006541 & 0.004277 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & left\_tail & JP + US close core + JP proxy + Asia proxy & 527 & 31 & 0.005493 & 0.005325 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & right\_tail & JP only & 554 & 17 & 0.010127 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & right\_tail & JP + US close core & 554 & 30 & 0.006710 & 0.003416 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & right\_tail & JP + US close core + JP proxy & 526 & 25 & 0.007819 & 0.002308 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD plain MLE & right\_tail & JP + US close core + JP proxy + Asia proxy & 527 & 32 & 0.006409 & 0.003718 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & JP only & 554 & 20 & 0.010625 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core & 553 & 29 & 0.006824 & 0.003801 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core + JP proxy & 527 & 25 & 0.006703 & 0.003922 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core + JP proxy + Asia proxy & 527 & 31 & 0.005463 & 0.005162 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & JP only & 554 & 18 & 0.010154 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core & 554 & 31 & 0.006783 & 0.003371 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core + JP proxy & 527 & 27 & 0.007748 & 0.002406 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/IQR POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core + JP proxy + Asia proxy & 527 & 31 & 0.006886 & 0.003268 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & left\_tail & JP only & 484 & 25 & 0.011229 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & left\_tail & JP + US close core & 484 & 31 & 0.008183 & 0.003046 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & left\_tail & JP + US close core + JP proxy & 474 & 32 & 0.006367 & 0.004862 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & left\_tail & JP + US close core + JP proxy + Asia proxy & 474 & 31 & 0.006902 & 0.004326 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & right\_tail & JP only & 484 & 25 & 0.009792 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & right\_tail & JP + US close core & 484 & 35 & 0.007624 & 0.002168 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & right\_tail & JP + US close core + JP proxy & 473 & 37 & 0.006835 & 0.002957 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD plain MLE & right\_tail & JP + US close core + JP proxy + Asia proxy & 473 & 36 & 0.007709 & 0.002083 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & JP only & 484 & 25 & 0.011303 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core & 484 & 32 & 0.008140 & 0.003163 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core + JP proxy & 474 & 35 & 0.006233 & 0.005070 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core + JP proxy + Asia proxy & 474 & 35 & 0.006443 & 0.004860 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & JP only & 484 & 29 & 0.008934 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core & 484 & 35 & 0.007703 & 0.001231 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core + JP proxy & 473 & 37 & 0.006973 & 0.001962 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM median/MAD POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core + JP proxy + Asia proxy & 473 & 36 & 0.007786 & 0.001149 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & left\_tail & JP only & 484 & 27 & 0.009821 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & left\_tail & JP + US close core & 482 & 28 & 0.005945 & 0.003876 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & left\_tail & JP + US close core + JP proxy & 473 & 28 & 0.005868 & 0.003952 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & left\_tail & JP + US close core + JP proxy + Asia proxy & 473 & 31 & 0.005035 & 0.004785 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & right\_tail & JP only & 484 & 18 & 0.011399 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & right\_tail & JP + US close core & 482 & 25 & 0.007128 & 0.004271 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & right\_tail & JP + US close core + JP proxy & 474 & 27 & 0.006603 & 0.004796 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD plain MLE & right\_tail & JP + US close core + JP proxy + Asia proxy & 473 & 27 & 0.007419 & 0.003980 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & left\_tail & JP only & 484 & 27 & 0.009658 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core & 483 & 31 & 0.005680 & 0.003978 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core + JP proxy & 473 & 30 & 0.005952 & 0.003706 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & left\_tail & JP + US close core + JP proxy + Asia proxy & 473 & 31 & 0.005497 & 0.004160 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & right\_tail & JP only & 484 & 20 & 0.010602 & 0.000000 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core & 483 & 26 & 0.006934 & 0.003668 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core + JP proxy & 474 & 27 & 0.006702 & 0.003900 \\
ml\_tail\_per\_model & restricted\_diagnostic & LGBM POT-GPD UniBM block-maxima shape & right\_tail & JP + US close core + JP proxy + Asia proxy & 474 & 27 & 0.007375 & 0.003226 \\
\midrule
\multicolumn{9}{l}{\footnotesize Visible notes: severity is conditional on VaR exceptions; positive delta means lower mean exceedance severity than the same-model anchor information set. This is an ES severity diagnostic, not a model-win claim.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>tailrisk_claim_scope_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/tailrisk_claim_scope_table.tex</code>.  
**ARS reading:** Claim-scope reference table separating headline, restricted, diagnostic, and sensitivity evidence.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: claim_governance_map
\begin{tabular}{lll}
\toprule
artifact & role & allowed claim \\
\midrule
benchmark\_metrics.parquet & baseline benchmarks & yes after clean-run author review \\
ml\_tail\_metrics.parquet & primary ML nested information sets & yes; current primary comparison is direct quantile \\
ml\_tail\_metrics\_per\_model.parquet & per-model OOS diagnostics & no; not a cross-model common-sample table \\
ml\_tail\_result\_matrix*.parquet & restricted model-family and increment comparisons & no; restricted sample evidence only \\
\midrule
\multicolumn{3}{l}{\footnotesize Visible notes: this map governs table placement. Restricted and diagnostic artifacts may support discussion, but they do not replace primary common-sample evidence.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>model_metrics_breach_audit.md</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/model_metrics_breach_audit.md</code>.  
**ARS reading:** Plain-text coverage audit for breach rates and exception discipline.

````markdown
# Model Metrics and Breach-Pass Audit

Run: `tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4`

Generated by `scripts/export_model_metrics_breach_audit.py`. Breach pass criterion: `abs(breach - 0.05) <= 0.025`; gate pass additionally requires `N >= 450`.

## LGBM/EVT Breach-Pass Counts Across 8 Scenarios

| Model | Breach-pass scenarios / 8 | Gate-pass scenarios / 8 |
| --- | ---: | ---: |
| LGBM POT-GPD UniBM block-maxima shape | 8/8 | 8/8 |
| LGBM POT-GPD plain MLE | 8/8 | 8/8 |
| LGBM direct quantile | 0/8 | 0/8 |
| LGBM location-scale empirical | 8/8 | 8/8 |
| LGBM median/IQR POT-GPD UniBM block-maxima shape | 8/8 | 8/8 |
| LGBM median/IQR POT-GPD plain MLE | 8/8 | 8/8 |
| LGBM median/MAD POT-GPD UniBM block-maxima shape | 6/8 | 6/8 |
| LGBM median/MAD POT-GPD plain MLE | 6/8 | 6/8 |

## Benchmark Breach-Pass Counts

| Tail | Breach-pass models | Gate-pass models | Total models |
| --- | ---: | ---: | ---: |
| Left | 11 | 10 | 12 |
| Right | 9 | 9 | 12 |
| Total | 20 | 19 | 24 |

## Best LGBM/EVT Model in Each Scenario

Best-by-FZ is selected among gate-pass rows only. QL-best is shown separately because it sometimes disagrees with FZ-best.

| Tail | Info set | Gate-pass rows | Best by FZ | Breach | QL | FZ | Severity | Best by QL | QL |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |
| Left | JP only | 7 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 3.6% | 0.001383 | -3.684175 | 0.010625 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 0.001383 |
| Left | JP + US close core | 7 | LGBM median/MAD POT-GPD UniBM block-maxima shape | 6.6% | 0.001071 | -4.146720 | 0.008140 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 0.000960 |
| Left | JP + US close core + JP proxy | 7 | LGBM median/MAD POT-GPD plain MLE | 6.8% | 0.000966 | -4.310340 | 0.006367 | LGBM median/IQR POT-GPD plain MLE | 0.000904 |
| Left | JP + US close core + JP proxy + Asia proxy | 7 | LGBM median/MAD POT-GPD plain MLE | 6.5% | 0.000993 | -4.269625 | 0.006902 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 0.000914 |
| Right | JP only | 7 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 3.2% | 0.001201 | -3.762414 | 0.010154 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 0.001201 |
| Right | JP + US close core | 7 | LGBM median/MAD POT-GPD plain MLE | 7.2% | 0.001120 | -3.998127 | 0.007624 | LGBM POT-GPD UniBM block-maxima shape | 0.001047 |
| Right | JP + US close core + JP proxy | 5 | LGBM POT-GPD plain MLE | 5.7% | 0.001034 | -4.029703 | 0.006603 | LGBM location-scale empirical | 0.001023 |
| Right | JP + US close core + JP proxy + Asia proxy | 5 | LGBM median/IQR POT-GPD UniBM block-maxima shape | 5.9% | 0.001050 | -3.942804 | 0.006886 | LGBM median/IQR POT-GPD plain MLE | 0.001046 |

## Best Benchmark Models

| Tail | Gate-pass rows | Best by FZ | Breach | QL | FZ | Best by QL | QL |
| --- | ---: | --- | ---: | ---: | ---: | --- | ---: |
| Left | 10 | gjr_garch_evt | 6.1% | 0.001330 | -3.746233 | gjr_garch_evt | 0.001330 |
| Right | 9 | gjr_garch_t | 4.3% | 0.001222 | -3.739711 | gjr_garch_t | 0.001222 |

## Slide-Promoted Rows

These are the locked, pre-specified promoted rows used in the current slides, not a universal best-FZ ranking.

| Tail | Model | Info set | Side | N | Breach | Pass | QL | FZ | Severity |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| left promoted | LGBM median/IQR POT-GPD plain MLE | JP + US close core + JP proxy + Asia proxy | Left | 527 | 5.9% | Y | 0.000917 | -4.222471 | 0.005493 |
| right promoted | LGBM location-scale empirical | JP + US close core + JP proxy | Right | 493 | 6.1% | Y | 0.001023 | -4.027288 | 0.006287 |

## Full Benchmark Metrics

| Tail | Model | N | Breach | Pass | QL | FZ | Severity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Left | gjr_garch_evt | 722 | 6.1% | Y | 0.001330 | -3.746233 | 0.007631 |
| Left | gjr_garch_t | 722 | 7.1% | Y | 0.001338 | -3.723459 | 0.007359 |
| Left | garch_t | 722 | 6.1% | Y | 0.001368 | -3.701083 | 0.008609 |
| Left | gas_t_location_scale | 722 | 6.4% | Y | 0.001352 | -3.693506 | 0.008670 |
| Left | ewma_vol_scaled | 722 | 5.3% | Y | 0.001409 | -3.647462 | 0.008636 |
| Left | care_expectile_sav | 620 | 6.8% | Y | 0.001456 | -3.607506 | 0.008946 |
| Left | historical_quantile | 722 | 5.5% | Y | 0.001476 | -3.540661 | 0.012140 |
| Left | caviar_sav | 498 | 5.8% | Y | 0.001568 | -3.540070 | 0.011676 |
| Left | caviar_asymmetric_slope | 508 | 7.1% | Y | 0.001564 | -3.532426 | 0.009410 |
| Left | rolling_quantile | 722 | 5.8% | Y | 0.001481 | -3.524684 | 0.011683 |
| Left | gas_t_pot_gpd | 223 | 4.5% | N | 0.001277 | -3.789288 | 0.006754 |
| Left | care_expectile_asymmetric_slope | 627 | 7.8% | N | 0.001440 | -3.621661 | 0.007879 |
| Right | gjr_garch_t | 722 | 4.3% | Y | 0.001222 | -3.739711 | 0.010272 |
| Right | gjr_garch_evt | 722 | 5.8% | Y | 0.001233 | -3.708574 | 0.008988 |
| Right | garch_t | 722 | 4.2% | Y | 0.001278 | -3.703374 | 0.010888 |
| Right | gas_t_location_scale | 722 | 5.0% | Y | 0.001307 | -3.668339 | 0.010514 |
| Right | ewma_vol_scaled | 722 | 4.6% | Y | 0.001342 | -3.656615 | 0.009787 |
| Right | caviar_asymmetric_slope | 504 | 6.7% | Y | 0.001494 | -3.466189 | 0.010720 |
| Right | rolling_quantile | 722 | 7.2% | Y | 0.001496 | -3.427318 | 0.011480 |
| Right | caviar_sav | 504 | 6.3% | Y | 0.001558 | -3.407822 | 0.011629 |
| Right | historical_quantile | 722 | 6.9% | Y | 0.001502 | -3.406776 | 0.012003 |
| Right | care_expectile_asymmetric_slope | 679 | 8.0% | N | 0.001327 | -3.531389 | 0.008670 |
| Right | care_expectile_sav | 679 | 8.5% | N | 0.001372 | -3.474738 | 0.008198 |
| Right | gas_t_pot_gpd | 223 | 8.5% | N | 0.001785 | -3.033734 | 0.012794 |

## Full LGBM/EVT Metrics

| Tail | Info set | Model | N | Breach | Pass | QL | FZ | Severity |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Left | JP only | LGBM median/IQR POT-GPD UniBM block-maxima shape | 554 | 3.6% | Y | 0.001383 | -3.684175 | 0.010625 |
| Left | JP only | LGBM median/IQR POT-GPD plain MLE | 554 | 3.6% | Y | 0.001383 | -3.679215 | 0.010818 |
| Left | JP only | LGBM median/MAD POT-GPD UniBM block-maxima shape | 484 | 5.2% | Y | 0.001491 | -3.598519 | 0.011303 |
| Left | JP only | LGBM median/MAD POT-GPD plain MLE | 484 | 5.2% | Y | 0.001490 | -3.597317 | 0.011229 |
| Left | JP only | LGBM location-scale empirical | 508 | 5.3% | Y | 0.001487 | -3.554176 | 0.009866 |
| Left | JP only | LGBM POT-GPD plain MLE | 484 | 5.6% | Y | 0.001520 | -3.525293 | 0.009821 |
| Left | JP only | LGBM POT-GPD UniBM block-maxima shape | 484 | 5.6% | Y | 0.001516 | -3.511702 | 0.009658 |
| Left | JP only | LGBM direct quantile | 554 | 7.9% | N | 0.001404 | -3.475021 | 0.008940 |
| Left | JP + US close core | LGBM median/MAD POT-GPD UniBM block-maxima shape | 484 | 6.6% | Y | 0.001071 | -4.146720 | 0.008140 |
| Left | JP + US close core | LGBM median/IQR POT-GPD plain MLE | 553 | 5.2% | Y | 0.000965 | -4.141200 | 0.006841 |
| Left | JP + US close core | LGBM median/MAD POT-GPD plain MLE | 484 | 6.4% | Y | 0.001067 | -4.119314 | 0.008183 |
| Left | JP + US close core | LGBM median/IQR POT-GPD UniBM block-maxima shape | 553 | 5.2% | Y | 0.000960 | -4.113223 | 0.006824 |
| Left | JP + US close core | LGBM POT-GPD plain MLE | 482 | 5.8% | Y | 0.000997 | -4.080408 | 0.005945 |
| Left | JP + US close core | LGBM POT-GPD UniBM block-maxima shape | 483 | 6.4% | Y | 0.000998 | -4.074074 | 0.005680 |
| Left | JP + US close core | LGBM location-scale empirical | 506 | 6.1% | Y | 0.000988 | -4.050495 | 0.005722 |
| Left | JP + US close core | LGBM direct quantile | 554 | 10.8% | N | 0.001150 | -3.678881 | 0.006263 |
| Left | JP + US close core + JP proxy | LGBM median/MAD POT-GPD plain MLE | 474 | 6.8% | Y | 0.000966 | -4.310340 | 0.006367 |
| Left | JP + US close core + JP proxy | LGBM median/MAD POT-GPD UniBM block-maxima shape | 474 | 7.4% | Y | 0.000980 | -4.281130 | 0.006233 |
| Left | JP + US close core + JP proxy | LGBM median/IQR POT-GPD UniBM block-maxima shape | 527 | 4.7% | Y | 0.000907 | -4.261671 | 0.006703 |
| Left | JP + US close core + JP proxy | LGBM median/IQR POT-GPD plain MLE | 526 | 4.8% | Y | 0.000904 | -4.198353 | 0.006541 |
| Left | JP + US close core + JP proxy | LGBM POT-GPD plain MLE | 473 | 5.9% | Y | 0.000990 | -4.151901 | 0.005868 |
| Left | JP + US close core + JP proxy | LGBM location-scale empirical | 492 | 6.5% | Y | 0.000988 | -4.142323 | 0.005532 |
| Left | JP + US close core + JP proxy | LGBM POT-GPD UniBM block-maxima shape | 473 | 6.3% | Y | 0.000998 | -4.131158 | 0.005952 |
| Left | JP + US close core + JP proxy | LGBM direct quantile | 527 | 11.8% | N | 0.001114 | -3.868878 | 0.005511 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM median/MAD POT-GPD plain MLE | 474 | 6.5% | Y | 0.000993 | -4.269625 | 0.006902 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM median/MAD POT-GPD UniBM block-maxima shape | 474 | 7.4% | Y | 0.001005 | -4.259353 | 0.006443 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM median/IQR POT-GPD plain MLE | 527 | 5.9% | Y | 0.000917 | -4.222471 | 0.005493 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM median/IQR POT-GPD UniBM block-maxima shape | 527 | 5.9% | Y | 0.000914 | -4.213620 | 0.005463 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM POT-GPD plain MLE | 473 | 6.6% | Y | 0.000987 | -4.090892 | 0.005035 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM location-scale empirical | 492 | 7.1% | Y | 0.000986 | -4.058506 | 0.004820 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM POT-GPD UniBM block-maxima shape | 473 | 6.6% | Y | 0.000998 | -4.056911 | 0.005497 |
| Left | JP + US close core + JP proxy + Asia proxy | LGBM direct quantile | 527 | 11.8% | N | 0.001119 | -3.807595 | 0.005581 |
| Right | JP only | LGBM median/IQR POT-GPD UniBM block-maxima shape | 554 | 3.2% | Y | 0.001201 | -3.762414 | 0.010154 |
| Right | JP only | LGBM median/IQR POT-GPD plain MLE | 554 | 3.1% | Y | 0.001211 | -3.756111 | 0.010127 |
| Right | JP only | LGBM median/MAD POT-GPD UniBM block-maxima shape | 484 | 6.0% | Y | 0.001334 | -3.613854 | 0.008934 |
| Right | JP only | LGBM median/MAD POT-GPD plain MLE | 484 | 5.2% | Y | 0.001330 | -3.610920 | 0.009792 |
| Right | JP only | LGBM POT-GPD UniBM block-maxima shape | 484 | 4.1% | Y | 0.001363 | -3.583150 | 0.010602 |
| Right | JP only | LGBM POT-GPD plain MLE | 484 | 3.7% | Y | 0.001369 | -3.576374 | 0.011399 |
| Right | JP only | LGBM location-scale empirical | 508 | 4.3% | Y | 0.001346 | -3.573913 | 0.010108 |
| Right | JP only | LGBM direct quantile | 554 | 9.4% | N | 0.001273 | -3.530485 | 0.007334 |
| Right | JP + US close core | LGBM median/MAD POT-GPD plain MLE | 484 | 7.2% | Y | 0.001120 | -3.998127 | 0.007624 |
| Right | JP + US close core | LGBM median/MAD POT-GPD UniBM block-maxima shape | 484 | 7.2% | Y | 0.001119 | -3.989896 | 0.007703 |
| Right | JP + US close core | LGBM POT-GPD UniBM block-maxima shape | 483 | 5.4% | Y | 0.001047 | -3.983169 | 0.006934 |
| Right | JP + US close core | LGBM POT-GPD plain MLE | 482 | 5.2% | Y | 0.001052 | -3.982679 | 0.007128 |
| Right | JP + US close core | LGBM median/IQR POT-GPD plain MLE | 554 | 5.4% | Y | 0.001048 | -3.975248 | 0.006710 |
| Right | JP + US close core | LGBM location-scale empirical | 505 | 6.1% | Y | 0.001047 | -3.971715 | 0.006370 |
| Right | JP + US close core | LGBM median/IQR POT-GPD UniBM block-maxima shape | 554 | 5.6% | Y | 0.001050 | -3.963747 | 0.006783 |
| Right | JP + US close core | LGBM direct quantile | 554 | 11.4% | N | 0.001211 | -3.548401 | 0.006614 |
| Right | JP + US close core + JP proxy | LGBM POT-GPD plain MLE | 474 | 5.7% | Y | 0.001034 | -4.029703 | 0.006603 |
| Right | JP + US close core + JP proxy | LGBM location-scale empirical | 493 | 6.1% | Y | 0.001023 | -4.027288 | 0.006287 |
| Right | JP + US close core + JP proxy | LGBM POT-GPD UniBM block-maxima shape | 474 | 5.7% | Y | 0.001032 | -4.020205 | 0.006702 |
| Right | JP + US close core + JP proxy | LGBM median/IQR POT-GPD plain MLE | 526 | 4.8% | Y | 0.001041 | -3.929021 | 0.007819 |
| Right | JP + US close core + JP proxy | LGBM median/IQR POT-GPD UniBM block-maxima shape | 527 | 5.1% | Y | 0.001048 | -3.882784 | 0.007748 |
| Right | JP + US close core + JP proxy | LGBM median/MAD POT-GPD plain MLE | 473 | 7.8% | N | 0.001082 | -4.085941 | 0.006835 |
| Right | JP + US close core + JP proxy | LGBM median/MAD POT-GPD UniBM block-maxima shape | 473 | 7.8% | N | 0.001085 | -4.057930 | 0.006973 |
| Right | JP + US close core + JP proxy | LGBM direct quantile | 527 | 11.6% | N | 0.001211 | -3.557463 | 0.006448 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM median/IQR POT-GPD UniBM block-maxima shape | 527 | 5.9% | Y | 0.001050 | -3.942804 | 0.006886 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM POT-GPD UniBM block-maxima shape | 474 | 5.7% | Y | 0.001085 | -3.929750 | 0.007375 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM POT-GPD plain MLE | 473 | 5.7% | Y | 0.001090 | -3.924620 | 0.007419 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM median/IQR POT-GPD plain MLE | 527 | 6.1% | Y | 0.001046 | -3.923889 | 0.006409 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM location-scale empirical | 492 | 6.3% | Y | 0.001085 | -3.910528 | 0.006984 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM median/MAD POT-GPD plain MLE | 473 | 7.6% | N | 0.001125 | -3.923032 | 0.007709 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM median/MAD POT-GPD UniBM block-maxima shape | 473 | 7.6% | N | 0.001126 | -3.921147 | 0.007786 |
| Right | JP + US close core + JP proxy + Asia proxy | LGBM direct quantile | 527 | 12.9% | N | 0.001222 | -3.559147 | 0.005853 |
````

</details>

<details markdown="1">
<summary><code>model_metrics_full_rows.csv</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/model_metrics_full_rows.csv</code>.  
**ARS reading:** Machine-readable full row export for verification.

````csv
group,tail,info,model,N,breach,breach_pass,gate_pass,q_loss,fz_loss,severity
Benchmark,Left,Target history,care_expectile_asymmetric_slope,627,0.07815,False,False,0.00144,-3.621661,0.007879
Benchmark,Left,Target history,care_expectile_sav,620,0.067742,True,True,0.001456,-3.607506,0.008946
Benchmark,Left,Target history,caviar_asymmetric_slope,508,0.070866,True,True,0.001564,-3.532426,0.00941
Benchmark,Left,Target history,caviar_sav,498,0.058233,True,True,0.001568,-3.54007,0.011676
Benchmark,Left,Target history,ewma_vol_scaled,722,0.052632,True,True,0.001409,-3.647462,0.008636
Benchmark,Left,Target history,garch_t,722,0.060942,True,True,0.001368,-3.701083,0.008609
Benchmark,Left,Target history,gas_t_location_scale,722,0.063712,True,True,0.001352,-3.693506,0.00867
Benchmark,Left,Target history,gas_t_pot_gpd,223,0.044843,True,False,0.001277,-3.789288,0.006754
Benchmark,Left,Target history,gjr_garch_evt,722,0.060942,True,True,0.00133,-3.746233,0.007631
Benchmark,Left,Target history,gjr_garch_t,722,0.070637,True,True,0.001338,-3.723459,0.007359
Benchmark,Left,Target history,historical_quantile,722,0.055402,True,True,0.001476,-3.540661,0.01214
Benchmark,Left,Target history,rolling_quantile,722,0.058172,True,True,0.001481,-3.524684,0.011683
Benchmark,Right,Target history,care_expectile_asymmetric_slope,679,0.079529,False,False,0.001327,-3.531389,0.00867
Benchmark,Right,Target history,care_expectile_sav,679,0.08542,False,False,0.001372,-3.474738,0.008198
Benchmark,Right,Target history,caviar_asymmetric_slope,504,0.06746,True,True,0.001494,-3.466189,0.01072
Benchmark,Right,Target history,caviar_sav,504,0.063492,True,True,0.001558,-3.407822,0.011629
Benchmark,Right,Target history,ewma_vol_scaled,722,0.045706,True,True,0.001342,-3.656615,0.009787
Benchmark,Right,Target history,garch_t,722,0.041551,True,True,0.001278,-3.703374,0.010888
Benchmark,Right,Target history,gas_t_location_scale,722,0.049861,True,True,0.001307,-3.668339,0.010514
Benchmark,Right,Target history,gas_t_pot_gpd,223,0.085202,False,False,0.001785,-3.033734,0.012794
Benchmark,Right,Target history,gjr_garch_evt,722,0.058172,True,True,0.001233,-3.708574,0.008988
Benchmark,Right,Target history,gjr_garch_t,722,0.042936,True,True,0.001222,-3.739711,0.010272
Benchmark,Right,Target history,historical_quantile,722,0.069252,True,True,0.001502,-3.406776,0.012003
Benchmark,Right,Target history,rolling_quantile,722,0.072022,True,True,0.001496,-3.427318,0.01148
LGBM,Left,JP only,LGBM direct quantile,554,0.079422,False,False,0.001404,-3.475021,0.00894
LGBM,Left,JP + US close core,LGBM direct quantile,554,0.108303,False,False,0.00115,-3.678881,0.006263
LGBM,Left,JP + US close core + JP proxy,LGBM direct quantile,527,0.117647,False,False,0.001114,-3.868878,0.005511
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM direct quantile,527,0.117647,False,False,0.001119,-3.807595,0.005581
LGBM,Left,JP only,LGBM location-scale empirical,508,0.05315,True,True,0.001487,-3.554176,0.009866
LGBM,Left,JP + US close core,LGBM location-scale empirical,506,0.061265,True,True,0.000988,-4.050495,0.005722
LGBM,Left,JP + US close core + JP proxy,LGBM location-scale empirical,492,0.065041,True,True,0.000988,-4.142323,0.005532
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM location-scale empirical,492,0.071138,True,True,0.000986,-4.058506,0.00482
LGBM,Left,JP only,LGBM median/IQR POT-GPD plain MLE,554,0.036101,True,True,0.001383,-3.679215,0.010818
LGBM,Left,JP + US close core,LGBM median/IQR POT-GPD plain MLE,553,0.052441,True,True,0.000965,-4.1412,0.006841
LGBM,Left,JP + US close core + JP proxy,LGBM median/IQR POT-GPD plain MLE,526,0.047529,True,True,0.000904,-4.198353,0.006541
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM median/IQR POT-GPD plain MLE,527,0.058824,True,True,0.000917,-4.222471,0.005493
LGBM,Left,JP only,LGBM median/IQR POT-GPD UniBM block-maxima shape,554,0.036101,True,True,0.001383,-3.684175,0.010625
LGBM,Left,JP + US close core,LGBM median/IQR POT-GPD UniBM block-maxima shape,553,0.052441,True,True,0.00096,-4.113223,0.006824
LGBM,Left,JP + US close core + JP proxy,LGBM median/IQR POT-GPD UniBM block-maxima shape,527,0.047438,True,True,0.000907,-4.261671,0.006703
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM median/IQR POT-GPD UniBM block-maxima shape,527,0.058824,True,True,0.000914,-4.21362,0.005463
LGBM,Left,JP only,LGBM median/MAD POT-GPD plain MLE,484,0.051653,True,True,0.00149,-3.597317,0.011229
LGBM,Left,JP + US close core,LGBM median/MAD POT-GPD plain MLE,484,0.06405,True,True,0.001067,-4.119314,0.008183
LGBM,Left,JP + US close core + JP proxy,LGBM median/MAD POT-GPD plain MLE,474,0.067511,True,True,0.000966,-4.31034,0.006367
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM median/MAD POT-GPD plain MLE,474,0.065401,True,True,0.000993,-4.269625,0.006902
LGBM,Left,JP only,LGBM median/MAD POT-GPD UniBM block-maxima shape,484,0.051653,True,True,0.001491,-3.598519,0.011303
LGBM,Left,JP + US close core,LGBM median/MAD POT-GPD UniBM block-maxima shape,484,0.066116,True,True,0.001071,-4.14672,0.00814
LGBM,Left,JP + US close core + JP proxy,LGBM median/MAD POT-GPD UniBM block-maxima shape,474,0.07384,True,True,0.00098,-4.28113,0.006233
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM median/MAD POT-GPD UniBM block-maxima shape,474,0.07384,True,True,0.001005,-4.259353,0.006443
LGBM,Left,JP only,LGBM POT-GPD plain MLE,484,0.055785,True,True,0.00152,-3.525293,0.009821
LGBM,Left,JP + US close core,LGBM POT-GPD plain MLE,482,0.058091,True,True,0.000997,-4.080408,0.005945
LGBM,Left,JP + US close core + JP proxy,LGBM POT-GPD plain MLE,473,0.059197,True,True,0.00099,-4.151901,0.005868
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM POT-GPD plain MLE,473,0.065539,True,True,0.000987,-4.090892,0.005035
LGBM,Left,JP only,LGBM POT-GPD UniBM block-maxima shape,484,0.055785,True,True,0.001516,-3.511702,0.009658
LGBM,Left,JP + US close core,LGBM POT-GPD UniBM block-maxima shape,483,0.064182,True,True,0.000998,-4.074074,0.00568
LGBM,Left,JP + US close core + JP proxy,LGBM POT-GPD UniBM block-maxima shape,473,0.063425,True,True,0.000998,-4.131158,0.005952
LGBM,Left,JP + US close core + JP proxy + Asia proxy,LGBM POT-GPD UniBM block-maxima shape,473,0.065539,True,True,0.000998,-4.056911,0.005497
LGBM,Right,JP only,LGBM direct quantile,554,0.093863,False,False,0.001273,-3.530485,0.007334
LGBM,Right,JP + US close core,LGBM direct quantile,554,0.113718,False,False,0.001211,-3.548401,0.006614
LGBM,Right,JP + US close core + JP proxy,LGBM direct quantile,527,0.11575,False,False,0.001211,-3.557463,0.006448
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM direct quantile,527,0.129032,False,False,0.001222,-3.559147,0.005853
LGBM,Right,JP only,LGBM location-scale empirical,508,0.043307,True,True,0.001346,-3.573913,0.010108
LGBM,Right,JP + US close core,LGBM location-scale empirical,505,0.061386,True,True,0.001047,-3.971715,0.00637
LGBM,Right,JP + US close core + JP proxy,LGBM location-scale empirical,493,0.060852,True,True,0.001023,-4.027288,0.006287
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM location-scale empirical,492,0.063008,True,True,0.001085,-3.910528,0.006984
LGBM,Right,JP only,LGBM median/IQR POT-GPD plain MLE,554,0.030686,True,True,0.001211,-3.756111,0.010127
LGBM,Right,JP + US close core,LGBM median/IQR POT-GPD plain MLE,554,0.054152,True,True,0.001048,-3.975248,0.00671
LGBM,Right,JP + US close core + JP proxy,LGBM median/IQR POT-GPD plain MLE,526,0.047529,True,True,0.001041,-3.929021,0.007819
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM median/IQR POT-GPD plain MLE,527,0.060721,True,True,0.001046,-3.923889,0.006409
LGBM,Right,JP only,LGBM median/IQR POT-GPD UniBM block-maxima shape,554,0.032491,True,True,0.001201,-3.762414,0.010154
LGBM,Right,JP + US close core,LGBM median/IQR POT-GPD UniBM block-maxima shape,554,0.055957,True,True,0.00105,-3.963747,0.006783
LGBM,Right,JP + US close core + JP proxy,LGBM median/IQR POT-GPD UniBM block-maxima shape,527,0.051233,True,True,0.001048,-3.882784,0.007748
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM median/IQR POT-GPD UniBM block-maxima shape,527,0.058824,True,True,0.00105,-3.942804,0.006886
LGBM,Right,JP only,LGBM median/MAD POT-GPD plain MLE,484,0.051653,True,True,0.00133,-3.61092,0.009792
LGBM,Right,JP + US close core,LGBM median/MAD POT-GPD plain MLE,484,0.072314,True,True,0.00112,-3.998127,0.007624
LGBM,Right,JP + US close core + JP proxy,LGBM median/MAD POT-GPD plain MLE,473,0.078224,False,False,0.001082,-4.085941,0.006835
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM median/MAD POT-GPD plain MLE,473,0.07611,False,False,0.001125,-3.923032,0.007709
LGBM,Right,JP only,LGBM median/MAD POT-GPD UniBM block-maxima shape,484,0.059917,True,True,0.001334,-3.613854,0.008934
LGBM,Right,JP + US close core,LGBM median/MAD POT-GPD UniBM block-maxima shape,484,0.072314,True,True,0.001119,-3.989896,0.007703
LGBM,Right,JP + US close core + JP proxy,LGBM median/MAD POT-GPD UniBM block-maxima shape,473,0.078224,False,False,0.001085,-4.05793,0.006973
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM median/MAD POT-GPD UniBM block-maxima shape,473,0.07611,False,False,0.001126,-3.921147,0.007786
LGBM,Right,JP only,LGBM POT-GPD plain MLE,484,0.03719,True,True,0.001369,-3.576374,0.011399
LGBM,Right,JP + US close core,LGBM POT-GPD plain MLE,482,0.051867,True,True,0.001052,-3.982679,0.007128
LGBM,Right,JP + US close core + JP proxy,LGBM POT-GPD plain MLE,474,0.056962,True,True,0.001034,-4.029703,0.006603
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM POT-GPD plain MLE,473,0.057082,True,True,0.00109,-3.92462,0.007419
LGBM,Right,JP only,LGBM POT-GPD UniBM block-maxima shape,484,0.041322,True,True,0.001363,-3.58315,0.010602
LGBM,Right,JP + US close core,LGBM POT-GPD UniBM block-maxima shape,483,0.05383,True,True,0.001047,-3.983169,0.006934
LGBM,Right,JP + US close core + JP proxy,LGBM POT-GPD UniBM block-maxima shape,474,0.056962,True,True,0.001032,-4.020205,0.006702
LGBM,Right,JP + US close core + JP proxy + Asia proxy,LGBM POT-GPD UniBM block-maxima shape,474,0.056962,True,True,0.001085,-3.92975,0.007375
````

</details>

<details markdown="1">
<summary><code>appendix_evt_threshold_sensitivity_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_evt_threshold_sensitivity_table.tex</code>.  
**ARS reading:** EVT-threshold sensitivity; robustness only, not primary claim evidence.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: appendix_configuration_robustness_evt_threshold
% primary_claim_allowed: false
\begin{tabular}{lll l lrrrrl}
\toprule
family & config & model & info & side & N & breach & q_loss & fz_loss & class \\
\midrule
evt\_threshold & u\_0\_875 & gjr\_garch\_evt & Target history & left\_tail & 722 & 0.060942 & 0.001329 & -3.747775 & robust \\
evt\_threshold & u\_0\_875 & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 473 & 0.061311 & 0.000991 & -4.149781 & robust \\
evt\_threshold & u\_0\_875 & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 473 & 0.063425 & 0.000998 & -4.127510 & robust \\
evt\_threshold & u\_0\_875 & gjr\_garch\_evt & Target history & right\_tail & 722 & 0.056787 & 0.001231 & -3.712077 & robust \\
evt\_threshold & u\_0\_875 & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001032 & -4.031106 & robust \\
evt\_threshold & u\_0\_875 & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001032 & -4.017355 & robust \\
evt\_threshold & u\_0\_925 & gjr\_garch\_evt & Target history & left\_tail & 722 & 0.060942 & 0.001330 & -3.746794 & robust \\
evt\_threshold & u\_0\_925 & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 473 & 0.054968 & 0.000990 & -4.152200 & robust \\
evt\_threshold & u\_0\_925 & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 473 & 0.061311 & 0.000998 & -4.134696 & robust \\
evt\_threshold & u\_0\_925 & gjr\_garch\_evt & Target history & right\_tail & 722 & 0.058172 & 0.001233 & -3.708617 & robust \\
evt\_threshold & u\_0\_925 & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001034 & -4.031751 & robust \\
evt\_threshold & u\_0\_925 & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 474 & 0.056962 & 0.001033 & -4.028096 & robust \\
evt\_threshold & u\_0\_950\_boundary & gjr\_garch\_evt & Target history & left\_tail & 0 &  &  &  & boundary\_diagnostic \\
evt\_threshold & u\_0\_950\_boundary & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 0 &  &  &  & boundary\_diagnostic \\
evt\_threshold & u\_0\_950\_boundary & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 0 &  &  &  & boundary\_diagnostic \\
evt\_threshold & u\_0\_950\_boundary & gjr\_garch\_evt & Target history & right\_tail & 0 &  &  &  & boundary\_diagnostic \\
evt\_threshold & u\_0\_950\_boundary & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 0 &  &  &  & boundary\_diagnostic \\
evt\_threshold & u\_0\_950\_boundary & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 0 &  &  &  & boundary\_diagnostic \\
\midrule
\multicolumn{10}{l}{\footnotesize Visible notes: appendix-only post-24-check configuration robustness diagnostics. Rows carry primary\_claim\_allowed=false and are not used to select primary selections, promoted rows, DM gates, the cross-suite FZ DM heatmap, or selected-model figures. Lower quantile/FZ loss is better; breach should be read against the 5\% nominal exception rate. Boundary EVT rows at u=0.95 are diagnostics at the 95\% VaR level, not alternative forecasts.} \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>appendix_lgbm_configuration_sensitivity_table.tex</code></summary>

**Repository layer:** Docs bundle.  
**Artifact path:** <code>docs/tables/tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4/appendix_lgbm_configuration_sensitivity_table.tex</code>.  
**ARS reading:** LightGBM-capacity sensitivity; robustness only, not primary claim evidence.

````tex
% run_id: tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
% git_commit: 7f628ff4f66258a36314f492b652cdf7ef594b7e
% config_hash: 874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
% table_scope: appendix_configuration_robustness_lgbm
% primary_claim_allowed: false
\begin{tabular}{lll l lrrrrl}
\toprule
family & config & model & info & side & N & breach & q_loss & fz_loss & class \\
\midrule
lgbm\_capacity & near\_high & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 474 & 0.052743 & 0.001016 & -4.140681 & robust \\
lgbm\_capacity & near\_high & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 474 & 0.059072 & 0.001016 & -4.096580 & robust \\
lgbm\_capacity & near\_high & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 472 & 0.055085 & 0.001035 & -4.107486 & robust \\
lgbm\_capacity & near\_high & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 472 & 0.055085 & 0.001034 & -3.943110 & robust \\
lgbm\_capacity & near\_low & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & left\_tail & 473 & 0.065539 & 0.000967 & -4.142152 & robust \\
lgbm\_capacity & near\_low & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & left\_tail & 473 & 0.071882 & 0.000977 & -4.151440 & robust \\
lgbm\_capacity & near\_low & LGBM POT-GPD plain MLE & JP + US close core + JP proxy & right\_tail & 473 & 0.059197 & 0.001055 & -4.014885 & robust \\
lgbm\_capacity & near\_low & LGBM POT-GPD UniBM block-maxima shape & JP + US close core + JP proxy & right\_tail & 474 & 0.061181 & 0.001054 & -4.003208 & robust \\
\midrule
\multicolumn{10}{l}{\footnotesize Visible notes: appendix-only post-24-check configuration robustness diagnostics. Rows carry primary\_claim\_allowed=false and are not used to select primary selections, promoted rows, DM gates, the cross-suite FZ DM heatmap, or selected-model figures. Lower quantile/FZ loss is better; breach should be read against the 5\% nominal exception rate. Boundary EVT rows at u=0.95 are diagnostics at the 95\% VaR level, not alternative forecasts.} \\
\bottomrule
\end{tabular}
````

</details>

### 9.2 Manuscript-Local Compact Tables

These manuscript-side tables are compact wrappers or summary tables built from the same locked artifacts. They are included here because they appear in the manuscript table directory even when their content repackages docs-bundle evidence.

<details markdown="1">
<summary><code>table1_design.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/table1_design.tex</code>.  
**ARS reading:** Main-text market timing and forecast-origin design table.

````tex
\small
\begin{tabularx}{\textwidth}{p{0.25\textwidth}X}
\toprule
Design element & Manuscript value \\
\midrule
Market & OSE Nikkei 225 Futures day-session opening risk after the U.S. cash-market close and the intervening OSE night-session window. \\
Forecast origin & Matched U.S. cash-market close plus pre-specified vendor-data availability lag. \\
Opening-gap measure & \(g_t=\log(\mathrm{day\ session\ open}_t)-\log(\mathrm{previous\ settlement}_{t-1})\). \\
Futures exposure measures & Downside loss \(L_t^-=-g_t\) and upside loss \(L_t^+=g_t\); a VaR exception is realized loss above forecast VaR. \\
Risk level & 95\% VaR and valid VaR-ES pairs; nominal exception rate is 5\%. \\
Clean forecast sample & 2018-06-20 to 2026-05-22; 1,722 forecast observations. \\
Information sets & Japan only; U.S.-close core; U.S.-close plus Japan proxy; U.S.-close plus Japan and Asia proxies. \\
Point-in-time rule & \(\texttt{feature\_available\_ts\_utc}\leq\texttt{model\_cutoff\_ts\_utc}<\texttt{target\_open\_ts\_utc}\). \\
Timing audit & 783,378 audited rows, zero hard failures, 611,790 warnings retained under documented conservative-lag, source-coverage, and timestamp-granularity rules. \\
Evidence status & Locked forecast-evaluation evidence package; no model, feature block, or sample window is reselected after observing the results. \\
\bottomrule
\end{tabularx}
````

</details>

<details markdown="1">
<summary><code>table2_benchmark_summary.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/table2_benchmark_summary.tex</code>.  
**ARS reading:** Manuscript compact benchmark floor table.

````tex
\small
\begin{tabular}{llrrrr}
\toprule
Model & Side & \(N\) & Breach & Q loss & FZ loss \\
\midrule
EWMA vol-scaled & Downside & 722 & 5.263\% & 0.001409 & -3.647462 \\
GARCH-\(t\) & Downside & 722 & 6.094\% & 0.001368 & -3.701083 \\
GJR-GARCH-\(t\) & Downside & 722 & 7.064\% & 0.001338 & -3.723459 \\
GJR-GARCH-EVT & Downside & 722 & 6.094\% & 0.001330 & -3.746233 \\
Historical quantile & Downside & 722 & 5.540\% & 0.001476 & -3.540661 \\
Rolling quantile & Downside & 722 & 5.817\% & 0.001481 & -3.524684 \\
\midrule
EWMA vol-scaled & Upside & 722 & 4.571\% & 0.001342 & -3.656615 \\
GARCH-\(t\) & Upside & 722 & 4.155\% & 0.001278 & -3.703374 \\
GJR-GARCH-\(t\) & Upside & 722 & 4.294\% & 0.001222 & -3.739711 \\
GJR-GARCH-EVT & Upside & 722 & 5.817\% & 0.001233 & -3.708574 \\
Historical quantile & Upside & 722 & 6.925\% & 0.001502 & -3.406776 \\
Rolling quantile & Upside & 722 & 7.202\% & 0.001496 & -3.427318 \\
\bottomrule
\end{tabular}

\vspace{0.4em}
\footnotesize Notes: The table summarizes selected benchmark rows on the common sample. Lower Q loss and FZ loss are better; breach rates should be read relative to the nominal 5\% exception rate.
````

</details>

<details markdown="1">
<summary><code>table3_ml_information_promoted.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/table3_ml_information_promoted.tex</code>.  
**ARS reading:** Manuscript nested information-set and promoted-row table.

````tex
\begin{minipage}{\textwidth}
\centering
\resizebox{\textwidth}{!}{%
\begin{tabular}{lllrrrrrl}
\toprule
Role & Information/model & Side & \(N\) & Exc. & Breach & Q loss & FZ loss & Inference note \\
\midrule
Direct & Japan only & Down & 527 & 43 & 8.159\% & 0.001412 & -3.489349 & anchor \\
Direct & +U.S.-close & Down & 527 & 59 & 11.195\% & 0.001158 & -3.668401 & diff -0.179; \(p=0.194\) \\
Direct & +Japan proxy & Down & 527 & 62 & 11.765\% & 0.001114 & -3.868878 & FZ gain vs prior \\
Direct & +Asia proxy & Down & 527 & 62 & 11.765\% & 0.001119 & -3.807595 & FZ gives back \\
\midrule
Direct & Japan only & Up & 527 & 51 & 9.677\% & 0.001310 & -3.487426 & anchor \\
Direct & +U.S.-close & Up & 527 & 63 & 11.954\% & 0.001252 & -3.486236 & diff 0.001; \(p=0.510\) \\
Direct & +Japan proxy & Up & 527 & 61 & 11.575\% & 0.001211 & -3.557463 & FZ gain vs prior \\
Direct & +Asia proxy & Up & 527 & 68 & 12.903\% & 0.001222 & -3.559147 & small FZ gain \\
\midrule
Filtered & Med/IQR POT-GPD, all & Down & 527 & 31 & 5.882\% & 0.000917 & -4.222471 & diff -0.489; \(p=0.049\) \\
Filtered & Loc-scale empirical, JP & Up & 493 & 30 & 6.085\% & 0.001023 & -4.027288 & diff -0.530; \(p=0.003\) \\
\bottomrule
\end{tabular}
}

\vspace{0.4em}
\parbox{\textwidth}{\footnotesize Notes: Direct quantile rows define the primary nested information-set comparison. Exc. is the VaR exception count. Med/IQR denotes the median/interquartile-range body filter; Loc-scale denotes location-scale empirical calibration; JP denotes the U.S.-traded Japan-proxy information set; all denotes U.S.-close core plus Japan-proxy and Asia-proxy blocks. Lower Q loss and FZ loss are better. For rows with reported paired inference, diff is candidate-minus-anchor FZ loss, so negative values favor the candidate. Promoted filtered-tail rows pass the pre-specified \(N\), coverage, and restricted-inference checks against the direct-quantile anchor; their Kupiec and Christoffersen \(p\)-values are 0.365 and 0.481 for the downside row and 0.284 and 0.393 for the upside row. These screened comparisons are not multiplicity-adjusted evidence for a universal model-family ranking.}
\end{minipage}
````

</details>

<details markdown="1">
<summary><code>table4_compact_exception_support.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/table4_compact_exception_support.tex</code>.  
**ARS reading:** Headline exception-count support for coverage interpretation.

````tex
\small
\begin{tabular}{lllrrr}
\toprule
Role & Row & Side & \(N\) & Exceptions & Breach \\
\midrule
Benchmark & GJR-GARCH-EVT & Down & 722 & 44 & 6.094\% \\
Benchmark & GJR-GARCH-\(t\) & Up & 722 & 31 & 4.294\% \\
\midrule
Direct & Japan only & Down & 527 & 43 & 8.159\% \\
Direct & +U.S.-close & Down & 527 & 59 & 11.195\% \\
Direct & +Japan proxy & Down & 527 & 62 & 11.765\% \\
Direct & +Asia proxy & Down & 527 & 62 & 11.765\% \\
\midrule
Direct & Japan only & Up & 527 & 51 & 9.677\% \\
Direct & +U.S.-close & Up & 527 & 63 & 11.954\% \\
Direct & +Japan proxy & Up & 527 & 61 & 11.575\% \\
Direct & +Asia proxy & Up & 527 & 68 & 12.903\% \\
\midrule
Promoted filtered-tail & Med/IQR POT-GPD, all & Down & 527 & 31 & 5.882\% \\
Promoted filtered-tail & Loc-scale empirical, JP & Up & 493 & 30 & 6.085\% \\
\bottomrule
\end{tabular}

\vspace{0.4em}
\footnotesize Notes: The table reports the headline exception counts behind the main coverage discussion. Direct rows use the 527-date direct-quantile common sample. Benchmark rows use the benchmark common sample. Promoted filtered-tail rows use their locked matched samples. Med/IQR denotes the median/interquartile-range body filter, Loc-scale denotes location-scale empirical calibration, JP denotes Japan-proxy information, and all denotes the full nested information set.
````

</details>

<details markdown="1">
<summary><code>promoted_screening_audit.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/promoted_screening_audit.tex</code>.  
**ARS reading:** Candidate-count audit for the promoted-row gates.

````tex
\begin{tabular}{lrr}
\toprule
Screening stage & Downside & Upside \\
\midrule
Initial LightGBM row universe & 32 & 32 \\
Valid VaR/ES and FZ loss & 32 & 32 \\
\(N \geq 450\) & 32 & 32 \\
Within 2.5 pp breach-rate band & 28 & 24 \\
Kupiec and Christoffersen screens & 25 & 20 \\
Side-specific promoted row & 1 & 1 \\
\bottomrule
\end{tabular}

\vspace{0.4em}
\footnotesize Notes: The initial universe is \(8\) LightGBM forecast families \(\times\) \(4\) information sets for each tail side. The Kupiec and Christoffersen screens require both coverage-test \(p\)-values to remain above the 5\% screen. The final promoted row is selected under the registered side-specific rule and read with restricted direct-anchor DM evidence; the counts are not a multiplicity-adjusted model-selection procedure.
````

</details>

<details markdown="1">
<summary><code>filtered_tail_diagnostics.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/filtered_tail_diagnostics.tex</code>.  
**ARS reading:** Compact filtered-tail diagnostic support for promoted rows.

````tex
\begin{tabularx}{\textwidth}{@{}p{0.24\textwidth}XX@{}}
\toprule
Metric & Downside promoted row & Upside promoted row \\
\midrule
Forecast family & Median/IQR POT-GPD plain MLE & Location-scale empirical \\
Information set & All blocks & +Japan proxy \\
\(N\) / exceptions & 527 / 31 & 493 / 30 \\
Breach rate & 5.882\% & 6.085\% \\
Kupiec / Christoffersen \(p\) & 0.365 / 0.481 & 0.284 / 0.393 \\
Tail diagnostics & 41 monthly POT refits; median exceedances 111 (IQR 92--128); median \(\hat{\xi}=0.238\) (IQR 0.163--0.292); ES-valid fraction 100\%. & POT diagnostics are not applicable because the promoted row uses empirical tail calibration rather than a fitted GPD tail. \\
\bottomrule
\end{tabularx}

\vspace{0.4em}
\footnotesize Notes: POT-GPD denotes peaks-over-threshold generalized Pareto distribution. K/C \(p\) reports Kupiec unconditional coverage and Christoffersen conditional coverage \(p\)-values. The downside POT diagnostics come from the locked filtered-tail diagnostic artifact for the promoted model and information set. Threshold and capacity sensitivity tables below refer to the fixed coverage-admissible comparison set, labelled post-24-check in the provenance files, not to a new promoted-row search.
````

</details>

<details markdown="1">
<summary><code>sensitivity_family_summary_table.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/generated/sensitivity_family_summary_table.tex</code>.  
**ARS reading:** Manuscript compact sensitivity family summary.

````tex
\begin{tabular}{p{0.14\textwidth}p{0.23\textwidth}rrrrrrrp{0.12\textwidth}}
\toprule
Family & Configs & Rows & Robust & Mixed & Sensitive & Boundary & Near & Warn & Claim use \\
\midrule
EVT threshold & u\_0\_875, u\_0\_925, u\_0\_950\_boundary & 18 & 12 & 0 & 0 & 6 & 12 & 0 & diagnostic only \\
LightGBM capacity & near\_high, near\_low & 8 & 8 & 0 & 0 & 0 & 8 & 0 & diagnostic only \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>sensitivity_evt_threshold_summary_table.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/generated/sensitivity_evt_threshold_summary_table.tex</code>.  
**ARS reading:** Manuscript compact EVT-threshold sensitivity summary.

````tex
\begin{tabular}{lrrrrrrrr}
\toprule
Threshold & Rows & Robust & Mixed & Boundary & Near & Warn & Max breach & Mean FZ delta \\
\midrule
u\_0\_875 & 6 & 6 & 0 & 0 & 6 & 0 & 6.3\% & +0.0\% \\
u\_0\_925 & 6 & 6 & 0 & 0 & 6 & 0 & 6.1\% & -0.1\% \\
u\_0\_950\_boundary & 6 & 0 & 0 & 6 & 0 & 0 & -- & -- \\
\bottomrule
\end{tabular}
````

</details>

<details markdown="1">
<summary><code>sensitivity_lgbm_capacity_summary_table.tex</code></summary>

**Repository layer:** Manuscript wrapper.  
**Artifact path:** <code>tables/generated/sensitivity_lgbm_capacity_summary_table.tex</code>.  
**ARS reading:** Manuscript compact LightGBM-capacity sensitivity summary.

````tex
\begin{tabular}{p{0.28\textwidth}lrrrrrrr}
\toprule
Model family & Config & Rows & Robust & Mixed & Sensitive & Warn & Max breach & Mean FZ delta \\
\midrule
LGBM POT-GPD plain MLE & near\_high & 2 & 2 & 0 & 0 & 0 & 5.5\% & -0.8\% \\
LGBM POT-GPD plain MLE & near\_low & 2 & 2 & 0 & 0 & 0 & 6.6\% & +0.3\% \\
LGBM POT-GPD UniBM & near\_high & 2 & 2 & 0 & 0 & 0 & 5.9\% & +1.4\% \\
LGBM POT-GPD UniBM & near\_low & 2 & 2 & 0 & 0 & 0 & 7.2\% & -0.0\% \\
\bottomrule
\end{tabular}
````

</details>
