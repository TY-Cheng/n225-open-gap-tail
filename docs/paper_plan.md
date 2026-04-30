---
hide:
  - navigation
---

# Paper Plan

## Working Title

**U.S. Close Information and Pre-Open Tail Risk in OSE Nikkei 225 Futures**

- This paper asks whether information observed at the U.S. cash-market close helps forecast the tail risk of the next Osaka Exchange (OSE) Nikkei 225 Futures day-session open.
- The setting is not a standard overnight-return problem. OSE futures trade through an active night session, so part of the U.S. information may already be incorporated before the Japanese opening auction.
- The contribution is a point-in-time (PiT) out-of-sample forecast evaluation of VaR and Expected Shortfall (ES), not a new machine-learning algorithm.
- The forecast origin is the U.S. close plus a realistic data-availability lag; all predictors are subject to look-ahead-bias controls.

## Main Question

- Does U.S. close information improve out-of-sample forecasts of OSE Nikkei 225 Futures opening-gap tail risk beyond Japan-only history and established econometric benchmarks?
- Related questions:
  - Does the effect differ between downside and upside opening-gap risk?
  - Does most of the marginal information arrive with the core U.S. close variables, with limited additional contribution from Japan and Asia proxy ETFs?
  - Do ML tail models lower average VaR-ES loss mainly through less conservative VaR estimates, or do they improve conditional tail calibration?
  - Does an EVT layer improve VaR-ES performance relative to direct LightGBM quantile forecasts?
  - Do loss differentials vary with ex-ante observables such as VIX, EST/EDT timing, or calendar-based trading conditions?

## Institutional Setting

- OSE Nikkei 225 Futures have a Japanese day session and an extended night session.
- The U.S. cash close precedes the next OSE day-session open, but the amount of post-U.S.-close OSE night trading differs between EST and EDT.
- The PiT condition is:

  `feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`.

- FRED macro-financial predictors use conservative publication lags, but they do not use unrevised real-time ALFRED vintages. This is a data limitation, not a timing violation.
- DST comparisons are descriptive timing-regime tests. They do not identify a structural causal mechanism.

## Sample and Data

- Current clean evaluation window: `2018-06-20` to `2026-04-28`.
- Current forecast-sample size: `1660` trading-day observations.
- Current headline tail level: 95% VaR, corresponding to a nominal 5% exception rate.
- The design also supports 97.5% VaR/ES evaluation, but those results should be promoted only if common-sample size, exception counts, and EVT diagnostics are sufficient.
- Main data sources:
  - J-Quants Premium: Nikkei 225 Futures prices, settlement, volume, and open interest.
  - Massive: U.S. ETFs, Japan proxy ETFs, Asia proxy ETFs, and SPY intraday-derived predictors.
  - FRED: rates, FX, and macro-financial predictors with publication-lag controls.
  - CBOE: volatility-index predictors, including VIX.

## Risk Surfaces

- The paper treats both sides of futures risk as economically meaningful:
  - `left_tail`: downside opening-gap risk, with realized loss defined as `-gap_t`.
  - `right_tail`: upside opening-gap risk, with realized loss defined as `gap_t`.
- VaR and ES are expressed in positive loss units.
- For both sides, a VaR exception is defined as:

  `realized_loss > var_forecast`.

- Left and right tails are evaluated separately. They are not assumed to have the same economic mechanism.

## Targets

- **Settlement-to-open gap**: log day-session open minus log previous settlement.
  - Main target.
  - Measures full opening-level risk relative to the prior settlement.
- **Close-to-open gap**: log day-session open minus log previous day-session close.
  - Secondary target.
  - Provides an alternative opening-gap reference.
- **Night-close-to-open gap**: log day-session open minus log night-session close.
  - Absorption robustness target.
  - Available only when the night close is observed and PiT-valid.
- **U.S.-close-mark-to-open gap**: log day-session open minus a timestamped Nikkei futures mark at the U.S. cash close.
  - Deferred target.
  - Requires licensed intraday OSE, CME, SGX, or equivalent Nikkei futures marks.

## Nested Information Sets

- `japan_only`
  - Target history, lagged Japanese futures variables, rolling volatility, volume/open-interest information, and Japanese calendar variables.
- `japan_only_plus_us_close_core`
  - Adds U.S. close equity, volatility, FX, and rates predictors available before the OSE open.
- `japan_only_plus_us_close_core_plus_japan_proxy`
  - Adds U.S.-traded Japan proxy ETFs such as `EWJ` and `DXJ`.
- `japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy`
  - Adds Asia proxy ETFs such as `EWY`, `EWT`, and `EWH`.
- Interpretation:
  - The nested information sets test marginal predictive content.
  - Proxy ETF blocks are pre-specified robustness and mechanism checks, not an exhaustive variable search.

## Forecasting Models

- Benchmark floor:
  - Historical empirical quantile.
  - Rolling empirical quantile.
  - EWMA or volatility-scaled quantile.
  - GARCH and GJR-GARCH with Student-t innovations.
  - GJR-GARCH-EVT in the McNeil-Frey tradition.
- Advanced econometric benchmarks:
  - CAViaR.
  - CARE / expectile-based tail models.
  - Generalized Autoregressive Score (GAS) models.
  - Taylor-style asymmetric-Laplace VaR-ES specifications.
  - Joint VaR-ES estimation via Fissler-Ziegel (FZ) scoring-function minimization, subject to numerical convergence checks.
- ML tail specifications:
  - Flexible, tree-based direct quantile estimation via gradient boosting (LightGBM).
  - LightGBM location-scale models.
  - LightGBM standardized-loss Peaks-Over-Threshold Generalized Pareto Distribution (POT-GPD).
- Estimation protocol:
  - ML tail models are refit monthly using expanding training windows.
  - LightGBM hyperparameters are held fixed across information sets and refit dates to limit data-dependent tuning bias.

## EVT Protocol

- EVT is used for tail calibration and ES extrapolation, not as a standalone contribution.
- POT-GPD is fitted to training-window standardized losses after conditional filtering.
- VaR and ES forecasts are transformed back into the target loss units.
- The first comparison should focus on 95% direct LightGBM quantile forecasts versus 95% LightGBM POT-GPD forecasts on common out-of-sample dates.
- 97.5% results require:
  - enough common-sample observations;
  - enough out-of-sample exceptions;
  - stable POT-GPD shape and scale estimates;
  - threshold-sensitivity checks;
  - ES severity and coverage diagnostics.

## Evaluation and Inference

- VaR calibration:
  - empirical breach rate;
  - Kupiec unconditional coverage test;
  - Christoffersen independence or conditional coverage test where sample size permits.
- VaR loss:
  - quantile loss on paired out-of-sample observations.
- Joint VaR-ES evaluation:
  - Fissler-Ziegel joint loss for valid VaR-ES pairs;
  - Murphy diagrams to assess sensitivity to the scoring function within the relevant family;
  - ES exceedance severity, interpreted conditional on an exception.
- Model comparison:
  - block-bootstrap Diebold-Mariano tests on paired loss differentials;
  - Hansen-Lunde-Nason Model Confidence Set where common-sample and exception-count gates pass;
  - Conditional Predictive Ability (CPA) regressions, specified as loss-differential regressions on ex-ante observables.
- Supporting diagnostics:
  - DST attenuation;
  - stress-window performance;
  - pre-open VaR trigger summaries.
- Trigger summaries are risk-monitoring diagnostics. They are not hedge PnL, transaction-cost, or trading-alpha evidence.

## Preliminary Empirical Findings and Caveats

- PiT audit:
  - The current audit records zero hard look-ahead-bias failures.
  - Warnings remain visible and should be discussed rather than suppressed.
  - FRED predictors are lagged by publication timing but are not ALFRED real-time vintages.
- Benchmark calibration:
  - Benchmark floor models have breach rates closer to the nominal 5% level than the ML direct-quantile headline models.
  - In the current clean evaluation, the benchmark floor median breach rate is about 6.1%.
- ML tail coverage drift:
  - The ML direct-quantile nested information sets produce breach rates of about 9.1% to 12.6%, above the nominal 5% level.
  - Lower average loss across information sets must therefore be interpreted alongside the coverage drift.
- Nested information sets:
  - The largest reduction in quantile loss occurs when core U.S. close variables are added.
  - Japan proxy and Asia proxy blocks appear to add less marginal loss reduction after U.S. close core variables are included.
- Restricted model-family comparison:
  - Location-scale and POT-GPD specifications are implemented.
  - Their common out-of-sample comparison is shorter than the direct-quantile headline sample.
  - These results are useful for model-family evidence, but they should not replace the headline nested-information-set analysis.
- CPA:
  - CPA is an inference layer over loss differentials.
  - It does not generate VaR or ES forecasts.
  - It does not replace unconditional DM/MCS comparisons.

## Main Tables and Figures

- Main text candidates:
  - data and timing audit;
  - benchmark common-sample table;
  - ML direct-quantile nested-information-set table;
  - left-tail and right-tail coverage breach-rate figure;
  - ML tail Murphy diagrams, read together with coverage diagnostics.
- Appendix candidates:
  - full benchmark metrics;
  - restricted model-family result matrix;
  - result-matrix DM/MCS notes;
  - CPA tables;
  - DST attenuation figures;
  - ES severity figures;
  - trigger diagnostics;
  - stress-window diagnostics;
  - feature availability and PiT audit details.

## Manuscript Structure

- Introduction:
  - motivate pre-open tail risk in OSE Nikkei 225 Futures;
  - explain why the night session matters;
  - state the nested-information-set question.
- Institutional setting and data:
  - describe OSE day/night sessions, U.S. close timing, DST regimes, source availability, and target construction.
- Methodology:
  - define loss units, tail sides, information sets, benchmark models, ML tail models, and EVT calibration.
- Empirical design:
  - define OOS splits, refit schedule, common-sample rules, inference tests, and claim boundaries.
- Results:
  - begin with PiT and sample audit;
  - report benchmark calibration;
  - report ML direct-quantile nested information sets for left and right tails;
  - report restricted location-scale and POT-GPD comparisons;
  - discuss coverage, DM/MCS, CPA, DST, ES severity, and trigger diagnostics.
- Conclusion:
  - summarize the incremental information content of U.S. close variables;
  - distinguish downside and upside risk;
  - state limits from coverage drift, FRED vintages, EVT sample size, and missing U.S.-close Nikkei futures marks.

## Claim Boundaries

- No structural causal spillover claim.
- No price-discovery claim.
- No claim that left-tail and right-tail mechanisms are identical.
- No trading-alpha claim.
- No hedge PnL or transaction-cost claim.
- No live deployment claim from historical J-Quants OHLC data.
- No `residual_usclosemark_to_open` claim without licensed timestamped intraday Nikkei futures marks.
- No claim that LightGBM-EVT is a new ML algorithm.
- No model-family ranking claim from restricted short samples.
- No extreme-tail claim without sufficient exceptions and rolling out-of-sample diagnostics.

## Source Notes

- JPX Nikkei 225 Futures contract specifications: [Nikkei 225 Futures | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)
- JPX derivatives trading hours: [Trading Hours | Derivatives | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/rules/trading-hours/index.html)
- J-Quants plan coverage: [Available APIs and Data Periods per Plan | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-spec)
- J-Quants data timing: [Update Timing of Provided Data | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-update)
- Massive.com stock-market timestamp semantics: [Stocks Overview | Massive.com](https://massive.com/docs/rest/stocks/overview)
- NYSE trading hours and early closes: [Holidays and Trading Hours | NYSE](https://www.nyse.com/trade/hours-calendars)
- FRED observations API: [fred/series/observations | FRED](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- Cboe VIX historical data: [VIX Index Historical Data | Cboe](https://www.cboe.com/tradable_products/vix/vix_historical_data)
- CME Nikkei products: [Nikkei 225 futures | CME Group](https://www.cmegroup.com/nikkei)
- Patton, Ziegel, and Chen dynamic ES-VaR models: [Dynamic semiparametric models for expected shortfall](https://www.sciencedirect.com/science/article/abs/pii/S030440761930048X)
- Taylor asymmetric-Laplace VaR-ES benchmark: [Forecasting Value at Risk and Expected Shortfall](https://www.tandfonline.com/doi/abs/10.1080/07350015.2017.1281815)
- Creal, Koopman, and Lucas score-driven models: [Generalized autoregressive score models with applications](https://tinbergen.nl/publication/160131/general-autoregressive-score-models-with-applications)
- Hansen, Lunde, and Nason model comparison: [The Model Confidence Set](https://econpapers.repec.org/RePEc:ecm:emetrp:v:79:y:2011:i:2:p:453-497)
- Murphy-diagram evaluation: [Murphy Diagrams: Forecast Evaluation of Expected Shortfall](https://arxiv.org/abs/1705.04537)
