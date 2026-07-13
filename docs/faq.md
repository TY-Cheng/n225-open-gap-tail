---
hide:
  - navigation
---

# FAQ

This page gives the plain-language framing behind the generated results snapshot. It is a guide to the empirical design and the current evidence, not a substitute for the tables, figures, and registered diagnostics.

## What is the paper asking?

The paper asks whether information known by the U.S. cash-market close helps forecast the next OSE Nikkei 225 Futures day-session opening tail.

- The contract is the OSE large Nikkei 225 Futures contract.
- The target is opening-gap risk at the next OSE day-session open.
- The left and right tails of the opening-gap return are evaluated as downside and upside losses, respectively. Both matter for futures positions, but they need not have the same economic pattern.
- The main comparison is across nested information sets: Japan-only history, U.S.-close core variables, Japan proxy ETFs, and Asia proxy ETFs.
- The results are research-candidate evidence. They are not a model-selection statement by themselves.

## What is the target?

The primary target is the settlement-to-open gap:

`gap_t = log(OSE day-session open_t) - log(previous settlement_{t-1})`

- For downside models, loss is `-gap_t`.
- For upside models, loss is `gap_t`.
- A VaR exception occurs when `realized_loss > VaR forecast`.
- The primary risk level is 95% VaR/ES, so the nominal exception rate is 5%.
- Rows around roll and SQ windows are excluded from the clean primary sample.
- `full_gap_close_to_open` and `residual_nightclose_to_day_open` are kept for audit and diagnostic use, but they are not the primary target.
- A U.S.-close-mark-to-OSE-open residual target would need a licensed timestamped Nikkei futures mark at the U.S. close cutoff. That target is not active in this run.

## Why is the OSE open worth studying?

The open matters because it is the first OSE day-session mark after the U.S. close information set and after the Japanese night-session interval.

- In the current clean primary sample (`n=1722`), the settle-to-open gap ranges from `-0.087513 log (-8.38%)` on `2020-03-13` to `0.096937 log (+10.18%)` on `2025-04-10`.
- The largest absolute clean settle-to-open gap is `0.096937 log (+10.18%)` on `2025-04-10`; this is large enough to make opening-gap tail risk a substantive risk-management forecasting problem rather than a cosmetic return-prediction exercise.
- The clean 1% to 99% settle-to-open range is `-0.031145 log (-3.07%)` to `0.027508 log (+2.79%)`, so the extremes are far outside the usual daily opening-gap range.
- Even after the night-session close, the clean night-close-to-open residual ranges from `-0.038278 log (-3.76%)` to `0.042071 log (+4.30%)`, with maximum absolute residual `0.042071 log (+4.30%)`.
- These magnitudes make the empirical object an opening-tail risk problem, not only an average next-open return-forecasting problem.

- JPX defines the OSE large contract as the home-market Nikkei 225 Futures contract with JPX/OSE trading hours, SQ rules, and JSCC clearing and margin rules.
- JPX and JSCC documentation make the basic risk channel clear: adverse futures moves change mark-to-market PnL, account equity, collateral pressure, and risk limits. Formal margin calls follow exchange and clearing procedures; the paper does not assume a mechanical margin call exactly at 08:45 JST.
- OSE night trading is not ignored. J-Quants night-session fields, night-close residuals, and timing indicators are in the audit layer.
- CME and SGX Nikkei contracts are important offshore venues, but they are not the target in this run. A cross-venue residual study would be a separate design.
- SQ and open-based settlement are related market-structure motivation, but the clean primary sample is not an SQ event study.

## What data enter the forecasts?

All predictors must be available before the OSE target open under the point-in-time timing rule:

`feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`

- J-Quants supplies OSE Nikkei 225 Futures target data, contract metadata, and lagged domestic option-state fields where available.
- Massive supplies U.S. close-side ETF, sector, Japan proxy, Asia proxy, minute-bar, and optional U.S.-listed options-derived inputs.
- FRED supplies rates, H.10 USD/JPY, VIX, and credit-spread controls with conservative release lags. These are not ALFRED real-time vintages.
- CBOE supplies volatility-index data.
- Benchmarks use lagged opening-gap losses only.
- The ML information sets add predictors in a fixed order: Japan only, then U.S.-close core, then Japan proxies, then Asia proxies.
- U.S.-listed options features are audit-gated. They are not primary evidence unless source, coverage, liquidity, and timing checks pass.

## What models are compared?

The baseline benchmarks, advanced econometric benchmarks, and ML-tail suite are implemented and have completed artifacts in this run.

- Baseline benchmarks include historical quantiles, rolling quantiles, EWMA, GARCH-t, GJR-GARCH-t, and GJR-GARCH-EVT.
- Advanced econometric benchmark families such as CAViaR, CARE/expectile, and GAS produce nonblocking empirical forecast rows; their interpretation still follows the benchmark and restricted-sample gates.
- The ML suite includes direct-quantile LightGBM forecasts, empirical location-scale calibration, and LightGBM-EVT specifications with MLE or UniBM tail estimation.
- LightGBM is used as a fixed tabular learner. The paper does not claim a new machine-learning algorithm.
- Hyperparameters are held fixed across information sets and refit dates.
- Most models use expanding pre-forecast training histories. The rolling-quantile benchmark is the designed exception: it uses the most recent 1,000 clean observations.

## Are all models tuned to maximum individual performance?

No. The paper compares registered point-in-time forecast specifications, not a tuning contest.

- Benchmark distributional parameters are fitted inside each training window where the model requires MLE or numerical optimization.
- CARE, GAS, and related advanced benchmarks may use small pre-registered grids where that is part of the model specification.
- LightGBM hyperparameters are held fixed across information sets and refit dates so information-set comparisons are not contaminated by a separate tuning search.
- This design may leave some model-specific performance untapped, but it keeps the nested information-set experiment interpretable.
- Appendix configuration robustness varies nearby LightGBM capacity and POT threshold choices after the primary run.
- Those rows carry `primary_claim_allowed=false`: they answer reviewer concerns about sensitivity but do not alter coverage admissibility, canonical forecasts, or the post-screen FZ DM comparison.
- The primary design compares pre-specified point-in-time forecast specifications. Configuration sensitivity is appendix robustness evidence, not a model-selection stage.

## How do the LightGBM-EVT variants work?

The final VaR/ES level is 95%. POT-GPD variants use a 0.90 threshold only for
tail fitting; it is not the reported VaR level.

- Direct-quantile LightGBM estimates the 95% VaR level directly.
- The LightGBM empirical location-scale specification estimates a conditional center and scale, then calibrates the upper tail of standardized losses empirically.
- The LightGBM mean/scale POT-GPD specifications fit a generalized Pareto tail above the registered 0.90 threshold of out-of-fold standardized losses.
- Median/MAD and median/IQR routes use more robust body filters before the POT-GPD step.
- Plain MLE estimates the GPD tail directly; UniBM supplies the alternative block-maxima shape route.
- The mean/scale POT-GPD MLE and UniBM specifications satisfy the current eight-scenario coverage screen across both tails and all four information sets.

## How are forecasts judged?

The evaluation is built around tail-risk performance, not a single ranking.

- Coverage: VaR breach rate should be close to the nominal 5% level.
- Exception count: coverage evidence is weak when the number of tail events is too small.
- Kupiec: tests unconditional VaR coverage.
- Christoffersen: tests exception clustering.
- Quantile loss: evaluates VaR forecasts.
- Fissler-Ziegel loss: evaluates joint VaR/ES forecasts where ES is valid.
- Mean exceedance severity: reports how large exceptions are once they happen.
- DM is average-sample inference across the unconditional evaluation sample.
- Murphy diagrams, stress-window, and ES severity diagnostics are supporting evidence.

## What do the current results say?

The current evidence supports a coverage-first, loss-second comparison.

- Direct-quantile LightGBM fails the breach-rate band and Kupiec test in all eight tail-by-information-set scenarios, although its Christoffersen independence checks pass. Its lower loss in some rows is therefore not sufficient for a calibrated tail-risk claim.
- The mean/scale POT-GPD MLE and UniBM specifications each satisfy the eight-scenario coverage screen: two tails x four information sets, each assessed by the breach-rate band, Kupiec unconditional coverage, and Christoffersen independence.
- GJR-GARCH-EVT passes the fixed benchmark validation rows and is the traditional anchor for the post-screen comparison.
- On strict common samples, both C-information LightGBM-EVT variants have lower FZ loss than GJR-GARCH-EVT in both tails. The differences are -0.472 and -0.451 in the left tail and -0.360 and -0.350 in the right tail, with one-sided DM p-values no larger than 0.005.
- LightGBM mean/scale POT-GPD MLE (C) and LightGBM mean/scale POT-GPD UniBM (C) are close to each other: the pairwise differences are small and do not support a decisive estimator-level ranking. The defensible result is at the filtered-tail model-class level.

## What can the paper claim?

| Evidence layer | Can support primary claim? | How to read it |
| --- | --- | --- |
| Benchmark common-sample table | Yes, after review | External statistical/econometric benchmark based on lagged opening-gap losses and a shared sample. |
| ML-tail nested information sets | Yes, after review | Strict nested-information-set comparison; direct quantile is the information-set comparator, not the coverage-admissibility gate. |
| ML-tail per-model rows | No | Model-specific out-of-sample diagnostics; samples need not match across model families. |
| Restricted result matrix | No primary claim | Matched-date comparison for model families and within-model increments. |
| Eight-scenario VaR coverage screen and post-screen FZ DM | Yes, conditional on the screen | Primary coverage-first comparison among the fixed coverage-admissible set on one strict common sample per tail. |
| Timing, target, information-ladder, coverage figures | Supporting main-text evidence | Design/motivation/headline visualization; still read with tables and gates. |
| Stress, Murphy, and overlay figures | Diagnostic only | Useful for interpretation, not automatic model-selection evidence. |

- The paper can claim a point-in-time forecast evaluation of OSE Nikkei 225 Futures opening-gap tail risk.
- It can report that U.S. close information and proxy blocks change average loss and coverage patterns under registered information sets.
- It can report that direct-quantile LightGBM forecasts are too liberal in the current primary ML rows.
- It can report that the two mean/scale LightGBM-EVT specifications satisfy the coverage screen across all nested information sets and that their information set C forecasts have lower paired FZ loss than GJR-GARCH-EVT in both tails.
- It should not claim that one model is universally strongest.
- It should not average downside and upside evidence into one mechanism.
- It should not present trigger or feature-block diagnostics as causal proof or realized trading performance.
- The current bottom line: the pipeline now produces a clean evidence set from the durable gold layer; baseline benchmark, advanced econometric benchmark, and ML-tail suites completed with zero recorded advanced-forecast failures; advanced rows are implemented evidence but remain nonblocking until author-reviewed against the same sample and inference gates.
