# Paper Plan

## Working Title

**Forecasting Pre-Open Tail Risk in Nikkei 225 Futures Using U.S. Close Information: A Session-Aligned LightGBM-EVT Framework**

## Core Thesis

This paper studies whether information frozen at the U.S. cash-market close improves timestamp-safe forecasts of the lower-tail risk of the next Osaka Exchange (OSE) Nikkei 225 Futures day-session open. The empirical object is not a conventional non-trading overnight return: OSE Nikkei 225 Futures trade through an extended night session that overlaps the U.S. trading day and closes shortly before the Japanese day session.

The central identification issue is therefore session alignment. U.S. close information may help explain the full opening level relative to the previous settlement or day-session close, but it may already be partly reflected in the OSE night session. The paper must distinguish full opening-gap risk from residual pre-open risk measured relative to a U.S.-close or night-session reference mark.

LightGBM is used as a flexible conditional-learning layer for nonlinear cross-market signals. EVT is used as a disciplined tail-extrapolation layer for downside losses. The contribution is not "LightGBM plus EVT" as a generic model combination; it is a timestamp-safe, session-aware test of whether U.S. close-side information has incremental lower-tail forecasting content for OSE Nikkei 225 Futures.

## Research Question

Can information frozen at the U.S. cash-market close improve timestamp-safe forecasts of the lower-tail risk of the next OSE Nikkei 225 Futures day-session opening level, relative to prior-settlement, prior-day-close, and night-session reference prices?

Secondary questions:

- Does U.S. close information improve full opening-gap VaR and ES calibration relative to Japan-only and historical baselines?
- After controlling for OSE night-session information, does the U.S. close vector retain incremental content for residual pre-open downside risk?
- Does the LightGBM layer mainly improve tail-event ranking, conditional scale, conditional quantiles, or VaR/ES calibration?
- Does the POT-EVT layer improve extreme quantile extrapolation and ES severity calibration beyond LightGBM-only forecasts?
- Are the results stable across roll windows, SQ windows, holiday-adjacent sessions, DST transitions, and stress regimes?

Upper-tail modeling is optional robustness or appendix work. The first implementation and main manuscript line should focus on downside tail risk.

## Contributions

1. **Session-aligned target construction**
   - Construct OSE day-session opening targets while explicitly handling night sessions, roll windows, SQ windows, Japan holidays, U.S. holidays, U.S. early closes, DST, and OSE holiday trading.

2. **Incremental U.S. close information test**
   - Compare Japan-only, U.S.-only, combined, FX/risk-proxy-augmented, and night-session-controlled specifications to test whether U.S. close-side variables add lower-tail forecasting content.

3. **Conditional EVT design**
   - Use LightGBM to learn nonlinear conditional structure and use POT-GPD on filtered or standardized downside losses for tail extrapolation.

4. **Risk-management evaluation**
   - Evaluate VaR coverage, joint VaR-ES scores, ES severity diagnostics, tail-event ranking, and fixed-rule hedge-trigger diagnostics without presenting the results as standalone trading-alpha claims.

## Forecast Origins

| Forecast origin | Nominal timestamp | Known information | Target open | Main use |
| --- | ---: | --- | --- | --- |
| `US_CASH_CLOSE` | 16:00 ET | U.S. ETF/index/FX/risk proxies available at the U.S. cash close | OSE day open at 8:45 JST | Main pre-open risk forecast origin |
| `OSE_NIGHT_CLOSE` | 6:00 JST | OSE night close if a live or historical session field is available | OSE day open at 8:45 JST | Opening-auction residual robustness |
| `PREV_OSE_DAY_CLOSE` | 15:45 JST | Previous OSE day-session close and settlement context | Next OSE day open | Full overnight inventory or margin-risk target |

J-Quants daily futures OHLC is appropriate for reproducible historical target construction. It must not be described as a live pre-open production feed because futures OHLC is updated after the fact and update timing is not guaranteed. A live pre-open hedge trigger would require a live OSE, CME, SGX, or equivalent Nikkei futures reference feed.

## Data Design

The target side should come from J-Quants, with OSE Nikkei 225 Futures large contract as the default main contract. Mini or micro contracts should be used only for liquidity checks or robustness unless the research design is explicitly changed.

Required J-Quants fields:

- Trading date, contract code, derivative product category, contract month, central contract flag.
- Day-session open, high, low, close.
- Night-session open, high, low, close where available.
- Whole-day open, high, low, close.
- Settlement price, volume, open interest, last trading day, and special quotation day.

Massive.com should be used for U.S. close-side predictors:

- Broad equity ETFs and indexes: SPY, QQQ, DIA, IWM, and major index proxies where licensed.
- Sector and cross-market dispersion signals, including sector ETFs and semiconductor or global-risk proxies where available.
- Implied-risk proxies such as VIX, VVIX, SKEW, or VIX futures where licensed.
- FX, rates, and commodity proxies, especially USD/JPY and U.S. rates proxies where available.
- U.S. futures only where the subscribed Massive.com plan supports the required instruments and history.

Each row must distinguish observation time, bar end time, vendor availability time, research download time, model cutoff time, and target open time. Massive.com timestamps are UTC and must be explicitly converted to exchange-local time before session alignment.

## Target Hierarchy

Primary empirical target if only J-Quants daily/session data is available:

- `full_gap_settle_to_open = log(day_open_t) - log(prev_settlement_{t-1})`

Secondary full-gap target:

- `full_gap_close_to_open = log(day_open_t) - log(prev_day_close_{t-1})`

Residual robustness target:

- `residual_nightclose_to_day_open = log(day_open_t) - log(night_close_t)`

Ideal pre-open residual target, only if a licensed intraday Nikkei futures reference mark exists:

- `residual_usclosemark_to_open = log(day_open_t) - log(nikkei_futures_mark_at_us_cash_close_t)`

Lower-tail labels:

- Loss: `L_t = -gap_t`.
- Downside exceedance: `L_t` above a training-window threshold.
- Downside severity: exceedance magnitude beyond the threshold.
- Conditional risk outputs: lower-tail probability, VaR, and ES.

The paper should report which forecast origin, reference price, and target family each empirical table uses.

## Feature Design

U.S. close-side features:

- U.S. broad market returns and intraday close-to-close or open-to-close signals.
- Sector ETF returns and cross-sector dispersion.
- Volatility and implied-risk proxy changes.
- FX, rates, and commodity proxy moves.
- U.S. market calendar flags, including regular close, early close, holiday-adjacent sessions, and DST regime.

Lagged Japanese futures variables:

- Prior full opening gap and lagged target values.
- Lagged OSE day-session returns.
- Lagged OSE night-session returns where available.
- Volume and open-interest changes.
- Roll-window and SQ-window indicators.
- Japan holiday-adjacent, U.S. holiday-adjacent, and OSE holiday-trading flags.

All features must satisfy `availability_ts <= model_cutoff_ts < target_open_ts`.

## Empirical Design

Use chronological evaluation only. Random splits are not acceptable.

Recommended validation structure:

- Initial training window, validation window, and final untouched test window.
- Rolling or expanding retraining for final evaluation.
- Thresholds and transformations estimated only inside each training window.
- Feature availability and target-open ordering checked for every row.

Incremental information specifications:

- Japan-only baseline.
- U.S.-only model.
- Japan plus U.S. close model.
- Japan plus U.S. plus FX model.
- Japan plus U.S. plus risk-indicator model.
- Night-session-controlled model where a night close or U.S.-close Nikkei futures mark is available.
- Full LightGBM-EVT model.

Baseline stack:

- Historical unconditional quantile.
- Rolling historical quantile.
- EWMA or volatility-scaled historical quantile.
- Linear or penalized quantile or location/scale baseline.
- GARCH-t or GJR-GARCH-t where feasible.
- GARCH-EVT on standardized residuals.
- CAViaR or a documented deferred CAViaR gate.
- ALD or Taylor-style semiparametric VaR-ES benchmark where feasible.
- LightGBM-only quantile and exceedance-probability variants.

Main LightGBM-EVT variants:

- `conditional_location_model`: LightGBM predicts conditional location; EVT fits residual losses.
- `conditional_scale_model`: LightGBM predicts scale proxy; EVT fits standardized losses.
- `quantile_model`: LightGBM quantile objective at alpha in `{0.05, 0.025, 0.01}`.
- `exceedance_probability_model`: LightGBM predicts rolling-threshold exceedance probability.
- `severity_model`: optional model for exceedance magnitudes.

## EVT Protocol

- Model downside losses `L_t = -gap_t`.
- Fit POT-GPD using training-window exceedances only.
- Store threshold grid diagnostics: exceedance count, mean-excess behavior, shape stability, and scale stability.
- Enforce a minimum exceedance count before reporting any extreme tail level.
- Report empirical tail levels such as 5%, 2.5%, and 1% separately from extrapolated levels.
- Do not claim 0.1% performance unless the sample size supports meaningful evaluation.
- Evaluate VaR and ES separately and jointly.

## Evaluation

Primary forecast evaluation:

- Quantile loss or pinball loss.
- Kupiec unconditional coverage test.
- Christoffersen independence and conditional coverage tests.
- Engle-Manganelli dynamic quantile test where feasible.
- Fissler-Ziegel joint VaR-ES score.
- ES exceedance severity diagnostics.
- Tail-event ranking: precision@k, recall@k, hit rate, and event concentration.

Model-comparison inference:

- Diebold-Mariano tests with block bootstrap where feasible.
- Model Confidence Set where feasible.

Risk-management diagnostic:

- Fixed hedge-trigger rule.
- Fixed cost assumptions.
- Loss avoided conditional on triggered hedge.
- False-positive rate, missed-event rate, and turnover.

The hedge-trigger analysis is a risk-management diagnostic, not a trading-profit claim.

## Manuscript Structure

1. **Introduction**
   - Motivate OSE Nikkei 225 Futures pre-open downside risk.
   - Explain why the night session changes the identification problem.
   - State the session-aligned LightGBM-EVT contribution without overclaiming model novelty.

2. **Market Structure, Data, and Target Construction**
   - Describe OSE day and night sessions, Massive.com U.S. close data, and J-Quants futures targets.
   - Define forecast origins, reference prices, target families, roll handling, and availability timestamps.
   - Present target distribution, tail counts, and extreme-event source tracebacks.

3. **Methodology**
   - Define the incremental information tests.
   - Define baselines, LightGBM conditional layers, and POT-EVT tail layer.
   - State rolling estimation, threshold selection, and leakage controls.

4. **Empirical Design**
   - Define train/validation/test periods.
   - Specify feature groups, model variants, and ablations.
   - Define VaR, ES, ranking, and hedge-trigger evaluation.

5. **Results**
   - Start with incremental information tables, not just a model leaderboard.
   - Compare Japan-only, U.S.-only, combined, night-controlled, and full LightGBM-EVT specifications.
   - Discuss calibration, ES severity, tail ranking, and feature interpretation.

6. **Robustness**
   - Alternative target families.
   - Alternative thresholds and tail levels.
   - Roll and SQ windows.
   - Holiday-adjacent and DST subsamples.
   - Crisis-period subsamples.
   - Upper-tail appendix only if it adds useful evidence.

7. **Conclusion**
   - Summarize whether U.S. close information has incremental timestamp-safe downside-tail content.
   - State limitations around data availability, live feeds, and market microstructure.
   - Identify extensions to intraday marks, options-implied measures, and real-time monitoring.

## Execution Gates

1. **Research Design Gate**
   - Forecast origins, target families, and reference-price rules are locked before ingestion or modeling.
   - Each empirical claim specifies forecast origin and target family.

2. **Data Audit Gate**
   - J-Quants target fields are parsed and checked against expected sessions and contract metadata.
   - Massive.com predictor rows have source, symbol, observation time, bar end time, vendor availability time, and download time.
   - Raw vendor data is never committed.

3. **Label Sanity Gate**
   - Full-gap and residual-gap definitions produce plausible distributions.
   - Roll windows, SQ windows, missing sessions, and holiday-adjacent sessions are flagged.
   - Extreme gaps are traceable to raw contract rows and session fields.

4. **Feature Leakage Gate**
   - Every feature has an availability timestamp.
   - `target_open_ts_utc > model_cutoff_ts_utc`.
   - No feature availability timestamp is later than `model_cutoff_ts_utc`.

5. **Baseline Gate**
   - Historical, volatility-scaled, econometric, and simple ML baselines are stored before LightGBM-EVT tuning.

6. **EVT Calibration Gate**
   - Threshold diagnostics precede VaR/ES claims.
   - Shape and scale stability are reviewed.
   - Weak calibration results are reported honestly.

7. **Manuscript Artifact Gate**
   - Tables and figures are reproducible from code.
   - Each reported result has a source artifact.
   - Smoke, schema, and real-data validation checks are labeled separately.

## Source Notes

- JPX trading hours: [Trading Hours | Derivatives | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/rules/trading-hours/index.html)
- J-Quants data timing: [Update Timing of Provided Data | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-update)
- Massive.com stock-market timestamp semantics: [Stocks Overview | Massive.com](https://massive.com/docs/rest/stocks/overview)
- LightGBM objectives, including quantile objective: [LightGBM Parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html)
