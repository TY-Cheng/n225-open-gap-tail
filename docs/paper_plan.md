---
hide:
  - navigation
---

# Paper Plan

## Working Title

**The Incremental Content of U.S. Close Information for Pre-Open Downside Tail Risk: Evidence from OSE Nikkei 225 Futures**

This is a historical, session-aligned downside tail-risk forecasting study. LightGBM-EVT is treated as a conditional tail-forecasting specification, not as the paper's standalone contribution.

## Core Thesis

The paper studies whether information observable at the U.S. cash-market close contains timestamp-safe incremental forecasting content for the lower tail of the next Osaka Exchange (OSE) Nikkei 225 Futures day-session open. The setting is institutionally distinctive because OSE Nikkei 225 Futures trade through a night session that overlaps the U.S. trading day and ends shortly before the Japanese day-session opening auction.

The empirical object is therefore not a simple non-trading overnight return. It is a pre-open risk forecast under an extended night-session market structure. U.S. close information may influence the full opening level, but it may also be absorbed by night-session futures trading before the day open. The paper's identification design separates these two interpretations.

The main target is full opening-level downside risk relative to the previous settlement. The key robustness design asks whether any U.S.-close signal is attenuated after night-session information is included. A cleaner U.S.-close residual target is reserved for a licensed intraday Nikkei futures mark at the U.S. cash close; without that mark, it remains an extension rather than a core empirical claim.

The modeling contribution is disciplined forecast evaluation. LightGBM is used to learn nonlinear conditional structure in a pre-registered information set. EVT is used to calibrate sparse downside losses and VaR/ES forecasts. The paper's evidentiary contribution is the session-aligned information-set test, not the invention of a new algorithm.

## Frontier Positioning

The paper is positioned between, but distinct from, three adjacent literatures. Overnight-return anomaly papers study average return behavior across the close-to-open interval; this project studies the lower tail of a futures day-session opening gap. Cross-market spillover papers study lead-lag transmission between the U.S. and Japan; this project evaluates timestamp-safe incremental forecast content under the OSE night-session structure. Direct VaR-ES papers estimate tail risk through scoring-rule or semiparametric objectives; this project compares those approaches with a two-stage conditional-learning and EVT calibration design.

The frontier question is not whether U.S. markets and Japanese markets are related. The question is whether U.S. cash-close information still improves lower-tail VaR/ES forecasts after the OSE night session has had an opportunity to absorb that information, and whether the remaining signal is better captured by direct joint VaR-ES estimation, score-driven dynamics, or a LightGBM-EVT tail-calibration pipeline.

## Institutional Timing and Information Sets

OSE Nikkei 225 Futures large contracts have a Japanese day session and an extended night session. The U.S. cash-market close must be aligned to this schedule before any predictive claim is interpretable.

| Event | JST | ET during EST | ET during EDT | Research implication |
| --- | ---: | ---: | ---: | --- |
| OSE day-session open | 08:45 | 18:45 previous day | 19:45 previous day | Target open and opening-auction risk point. |
| OSE day-session close | 15:45 | 01:45 | 02:45 | Prior Japanese day-session information. |
| OSE night-session open | 17:00 | 03:00 | 04:00 | Start of night trading. |
| U.S. cash-market close | 06:00 next day in EST / 05:00 next day in EDT | 16:00 | 16:00 | Main forecast-origin information freeze. |
| OSE night-session close | 06:00 next day | 16:00 | 17:00 | Night-session absorption endpoint. |
| Forecast cutoff | At or after U.S. close, before OSE day open | After 16:00 | After 16:00 | Must use only timestamp-valid predictors. |

The EST/EDT distinction is part of the identification design. During U.S. standard time, the U.S. cash close coincides with the OSE night-session close. During U.S. daylight time, the OSE night session continues for roughly one hour after the U.S. cash close. If U.S. close information is absorbed during that final hour, incremental forecast gains should be smaller in EDT than in EST, all else equal.

This DST regime comparison is not a causal design by itself. It is a timestamp-safe way to test whether the predictive content of U.S. close information changes when the market has a different amount of post-close night-session trading time.

### DST Absorption Test

The DST absorption test is a headline empirical result, not only a calendar control. The design estimates U.S.-close incremental forecast gains separately in EST and EDT regimes and tests whether those gains are attenuated when the OSE night session has roughly one hour after the U.S. close to absorb information. The main estimand is an absorption pattern: whether the U.S.-close predictor block improves lower-tail loss functions less in EDT than in EST after common controls are held fixed.

### Absorption Coefficient

The headline summary statistic is an absorption coefficient:

`alpha_absorb = 1 - FZ_gain_EDT / FZ_gain_EST`.

`FZ_gain` is the reduction in pre-specified Fissler-Ziegel loss from adding the U.S.-close predictor block to the benchmark information set in a given DST regime. Values near zero indicate that the extra EDT hour does not materially reduce the U.S.-close forecast gain. Values near one indicate that the extra hour absorbs most of the signal measured in EST. If `FZ_gain_EST` is near zero or has the wrong sign, the ratio is not reported as a coefficient; the table reports the two regime-specific gains and confidence intervals instead. The coefficient is descriptive forecast evidence, not a structural absorption parameter.

## Research Questions

The main question is:

> Does information frozen at the U.S. cash-market close improve lower-tail VaR and ES forecasts for the next OSE Nikkei 225 Futures day-session open, relative to Japan-only, volatility-scaled, GARCH/GJR, and GARCH-EVT benchmarks?

Secondary questions are:

- Does U.S. close information improve full opening-gap VaR/ES calibration relative to Japan-only and historical baselines?
- How much of the U.S.-close signal is attenuated after night-session controls or a night-close residual target are introduced?
- Does the DST absorption regime change the measured incremental content of U.S. close predictors?
- Does LightGBM improve nonlinear tail-event ranking or conditional calibration relative to simpler models using the same information set?
- Does the EVT layer improve extreme-tail extrapolation and ES severity diagnostics relative to LightGBM-only forecasts?
- Are results stable around roll windows, SQ windows, U.S. early closes, Japan holidays, and stress periods?

Upper-tail analysis is optional appendix work. The main paper is a lower-tail risk study.

## Target Hierarchy

The target definitions use log gaps throughout. The detailed field contract and source-status rules are maintained in [Data Design and Contract](data.md).

| Target | Definition | Paper status | Interpretation |
| --- | --- | --- | --- |
| `full_gap_settle_to_open` | `log(day_open_t) - log(prev_settlement_{t-1})` | Main target | Reproducible full opening-level risk-management target when J-Quants futures session data are available. |
| `full_gap_close_to_open` | `log(day_open_t) - log(prev_day_close_{t-1})` | Secondary target | Alternative full opening-gap definition relative to the previous day-session close. |
| `residual_nightclose_to_day_open` | `log(day_open_t) - log(night_close_t)` | Absorption robustness | Measures risk remaining after night-session trading, conditional on audited night-close availability. |
| `residual_usclosemark_to_open` | `log(day_open_t) - log(nikkei_futures_mark_at_us_cash_close_t)` | Licensed-data extension only | Cleanest residual pre-open target, but unavailable without timestamped intraday OSE, CME, SGX, or equivalent Nikkei futures marks. |

`full_gap_settle_to_open` should not be interpreted as unresolved post-U.S.-close risk. It is the full opening-level risk faced relative to the previous settlement. Residual post-U.S.-close risk requires a timestamped U.S.-close Nikkei futures reference mark.

## Identification Design

The null hypothesis is:

> Conditional on Japan-only information and night-session information available before the OSE day-session open, U.S. cash-close predictors have no incremental forecasting content for the lower-tail distribution of the next OSE day-session opening gap.

The empirical design tests this null through nested information sets:

1. Japan-only historical and lagged futures variables.
2. Japan plus U.S. close-side equity, FX, volatility, and rates predictors.
3. Japan plus U.S. core plus U.S.-traded Japan proxy block (`EWJ`, `DXJ`).
4. Japan plus U.S. core plus Japan proxy plus Asia proxy block (`EWY`, `EWT`, `EWH`).

DST, early-close interactions, and night-session controls are added to the same nested ladder rather than treated as broader feature searches. The Japan and Asia proxy blocks are interpreted as mechanism and robustness layers, not as part of the broad U.S. core signal.

The primary comparison uses chronological rolling or expanding forecasts. The implemented default is a documented block-bootstrap Diebold-Mariano comparison on paired VaR/ES loss differentials, with common-sample loss matrices used for MCS and related diagnostics. A true instrumented Giacomini-White conditional predictive ability regression remains a future inference layer; it should only be reported after the rolling design, instrument set, and out-of-sample length are sufficient.

## Economic Mechanism

The motivating mechanism is opening-auction residual risk under asymmetric liquidity absorption. U.S. late-day information can shift Nikkei fair value while OSE night-session liquidity is thinner than day-session liquidity. In stressed conditions, market makers may reduce depth, widen spreads, or manage inventory more conservatively, leaving part of the downside risk to clear in the next day-session opening auction.

Volume and open interest are used as liquidity and contract-state proxies when the audited J-Quants fields support them. Session-specific volume is used only if it is available and semantically verified. These variables support the economic plausibility of the forecast design; they do not turn the paper into a market-microstructure or price-discovery study.

## Prior Literature and Intended Contribution

This section is a compressed planning placeholder. The manuscript version should expand it into a full literature review rather than leaving the three strands as a short summary.

The closest literature has three strands. U.S.-Japan transmission studies show that Japanese equity and futures markets can respond to foreign-market information, but they do not by themselves define a timestamp-safe OSE day-open tail forecast. Nikkei futures market-integration studies show that OSE, SGX, CME, and night-session trading form a cross-venue information network, which is exactly why the paper must separate full opening-level risk from residual pre-open risk. Tail-risk forecasting studies define the peer models and scoring language, especially conditional EVT, CAViaR, joint VaR-ES scoring, and semiparametric VaR-ES evaluation.

The manuscript literature review should expand three strands:

- U.S.-Japan transmission: Hamao, Masulis, and Ng; Lin, Engle, and Ito; Bae, Karolyi, and Stulz; and Dungey-style contagion and transmission work. These papers motivate cross-market information, but they do not construct a session-aligned lower-tail forecast.
- Nikkei futures market integration: CME/OSE/SGX Nikkei futures work, intraday futures studies, and opening-auction research. These papers motivate the separation between full opening-gap risk and residual pre-open risk.
- Tail-risk forecasting: McNeil-Frey GARCH-EVT, Engle-Manganelli CAViaR, Patton-Ziegel-Chen semiparametric ES, Taylor CARE/ALD VaR-ES, Dimitriadis-Bayer regression-based VaR/ES, and Creal-Koopman-Lucas GAS models.

The intended contribution is narrower than those literatures. The paper contributes a session-aligned target construction and forecast-evaluation design for OSE Nikkei 225 Futures pre-open downside risk. It asks whether U.S. close-side variables add lower-tail forecasting content beyond Japan-only and night-session-aware baselines, and whether conditional learning plus EVT calibration improves VaR/ES forecasts relative to credible risk-model peers.

The strongest positive evidence would be stable rolling out-of-sample improvement in lower-tail calibration, ES severity, and tail-event ranking after adding U.S. close predictors, especially when compared with historical, volatility-scaled, GARCH/GJR, GJR-GARCH-EVT, and LightGBM-only alternatives. A negative or attenuated result after night-session controls would also be informative, because it would indicate that night-session trading absorbs much of the U.S.-close information before the OSE day open.

### Comparison with Related Forecasting Approaches

Direct FZ-loss and semiparametric VaR-ES models provide the closest methodological challenge. They estimate VaR and ES jointly without a separate EVT layer, and they are the natural answer to the question: why not optimize the target score directly? The paper addresses this by including a direct FZ-loss or CARE-style VaR-ES benchmark in the main comparison when implementation and sample size support stable estimation.

Score-driven GAS models are another relevant benchmark family because they update tail-risk parameters through the score of the predictive density. A GAS-t or GAS VaR-ES specification is an advanced benchmark candidate. If the implementation is not stable on the audited sample, the paper should report this as a benchmark limitation rather than substituting an unvalidated implementation.

CAViaR and CARE models are included because they directly model conditional quantiles or expected shortfall dynamics. They help distinguish whether LightGBM-EVT adds value beyond established dynamic tail-risk models.

Deep learning is not the first-paper workhorse. The target is daily/session-level, the sample is likely measured in thousands rather than millions of observations, and the predictor set is tabular and economically pre-registered. Neural VaR/ES models can be discussed as future work, but they are not needed to answer the first paper's information-set question.

## Forecasting Benchmarks

The benchmark stack is pre-specified around forecast credibility and interpretability.

Required baseline floor:

- historical empirical quantile;
- rolling empirical quantile;
- volatility-scaled quantile;
- GARCH(1,1) with Gaussian or Student-t innovations;
- GJR-GARCH(1,1) with Gaussian or Student-t innovations;
- GJR-GARCH-EVT in the McNeil-Frey spirit, using a GARCH/GJR filter and POT-GPD tail calibration;
- LightGBM-only quantile, exceedance, or scale specification;
- LightGBM-EVT conditional tail specification.

Main advanced benchmarks, subject to stable implementation on the audited sample:

- direct FZ-loss or CARE-style VaR-ES estimation;
- CAViaR;
- Taylor-style semiparametric VaR-ES or asymmetric-Laplace VaR-ES models.

Appendix and fallback benchmarks may include:

- GAS-t or score-driven VaR-ES models;
- richer cross-venue or options-implied specifications when licensed data are available.

LightGBM and econometric models should use the same pre-registered core information set wherever possible. This keeps any LightGBM gain interpretable as nonlinear conditional learning rather than a feature-mining artifact.

## LightGBM to EVT Interface

The primary hybrid specification uses LightGBM as a conditional scaling layer. A baseline return or loss model produces one-step-ahead residual losses; LightGBM estimates conditional scale, or a location-scale pair, from the pre-registered information set. Losses are standardized by the predicted scale, and POT-GPD is fitted only to training-window standardized downside exceedances. VaR and ES forecasts are then transformed back to the target scale.

The first benchmark is a LightGBM direct quantile model at the relevant lower-tail levels, without EVT. This isolates whether EVT tail calibration adds value beyond a flexible conditional quantile learner.

An optional robustness specification uses LightGBM to predict rolling-threshold exceedance probability and applies GPD calibration to exceedance severity. This variant is reported only if exceedance counts are sufficient and probability calibration is stable on validation data.

## EVT Feasibility and Protocol

EVT claims are conditional on the target-data audit. POT-GPD is fitted only on training-window downside exceedances, with losses defined as `L_t = -gap_t`. The primary threshold-selection criterion is mean-excess linearity together with GPD shape and scale stability above the threshold. The threshold grid, exceedance count, mean-excess behavior, tail-index estimates, and shape/scale stability must be reported before VaR/ES claims at extreme levels are made.

Automated threshold checks, such as Danielsson-style double-bootstrap or Beirlant-Goegebeur style sequential diagnostics, are optional robustness tools. Threshold sensitivity is required: the main VaR/ES table should be accompanied by a robustness table or figure showing nearby threshold choices. The default rolling-window gate is a minimum of 30 training-window exceedances before reporting EVT-based ES from that window. If the audit shows that exceedance counts are too thin, EVT results should be restricted to less extreme tail levels, pooled/expanding windows, or diagnostic discussion. No 0.1% VaR/ES or extreme-tail superiority claim should be made without sufficient exceedances and rolling out-of-sample diagnostics.

## Evaluation Strategy

Evaluation is organized around forecast calibration, tail ranking, and risk-management diagnostics.

VaR evaluation:

- quantile loss;
- Kupiec unconditional coverage;
- Christoffersen independence or conditional coverage;
- Dynamic Quantile test where sample size permits.

ES and joint VaR-ES evaluation:

- Fissler-Ziegel joint VaR-ES score;
- Murphy diagrams for VaR-ES dominance checks across the relevant scoring-function family;
- ES exceedance-severity diagnostics;
- bootstrap or simulation-based ES checks where feasible.

Model comparison:

- block-bootstrap Diebold-Mariano paired loss comparisons as the implemented default;
- instrumented Giacomini-White conditional predictive ability only after a registered instrumented implementation exists and the rolling design is sufficiently long;
- Diebold-Mariano tests with HAC or block-bootstrap standard errors as a fallback;
- Model Confidence Set for the main model family when there are enough out-of-sample loss differentials;
- quantile-score calibration and sharpness decomposition where implementation is stable.

Tail ranking:

- precision among the highest predicted-risk observations;
- recall among realized lower-tail events;
- event concentration by predicted-risk decile.

Tail-weighted CRPS is used only if a model produces a full predictive distribution. It should not be reported for VaR/ES-only models as if they were distributional forecasts.

Risk-management diagnostics include a main ES severity reduction table. The table reports how much adding U.S. close information reduces realized exceedance severity at the 2.5% ES level, conditional on an exceedance. Fixed hedge-trigger summaries may also report missed events, false positives, turnover, and loss avoided under stated assumptions, but turnover and cost diagnostics remain secondary and are not trading-alpha evidence.

## Result Presentation Sequence

The empirical section should lead with evidence rather than a model leaderboard:

1. Target audit: availability, missingness, contract coverage, roll/SQ flags, distribution, autocorrelation, tail counts, and extreme-event tracebacks.
2. Incremental U.S.-close information: Japan-only versus Japan plus U.S. core predictors.
3. Proxy-block ladder: add Japan proxy (`EWJ`, `DXJ`) and then Asia proxy (`EWY`, `EWT`, `EWH`) to measure whether proxy trading absorbs or adds signal beyond U.S. core.
4. DST interaction: compare predictive gains across EST and EDT regimes.
5. Absorption coefficient: report EST and EDT gains, `alpha_absorb` where well-defined, and confidence intervals or bootstrap uncertainty.
6. Night-session attenuation: compare full-gap targets with night-close residual or night-session-controlled designs.
7. VaR/ES calibration and ES severity reduction: coverage, joint scoring, exceedance severity, and risk-management diagnostics.
8. Model-set comparison: direct FZ/CARE, GARCH/GJR-EVT, LightGBM-only, and LightGBM-EVT under common loss functions.
9. Robustness: alternative thresholds, windows, contract-roll treatment, holidays, early closes, and stress subperiods.

## Manuscript Structure

1. Introduction: motivate OSE pre-open downside risk and state the incremental-information question.
2. Institutional Timing and Data: explain OSE day/night sessions, U.S. close timing, DST regimes, source roles, and target construction.
3. Methodology: define information sets, benchmark models, LightGBM conditional specification, and EVT calibration.
4. Empirical Design: define chronological splits, rolling/expanding estimation, inference tests, and evaluation metrics.
5. Results: present target audit, incremental information, DST and night-session attenuation, VaR/ES calibration, and robustness.
6. Conclusion: summarize timestamp-safe predictive evidence and the limits imposed by target access, night-session absorption, and live-feed requirements.

## Scope and Claim Boundaries

The following boundaries are hard constraints:

- No causal spillover claim.
- No price discovery claim without audited timestamped intraday cross-venue data.
- No trading alpha claim.
- No live deployment claim from J-Quants futures OHLC.
- No `residual_usclosemark_to_open` claim without licensed timestamped intraday Nikkei futures marks.
- No claim that LightGBM-EVT is a novel algorithm.
- No extreme-tail superiority claim without enough exceedances and rolling out-of-sample diagnostics.

Paper-grade empirical claims require completed OSE Nikkei 225 Futures target-data audit and rolling out-of-sample evaluation. J-Quants Premium futures OHLC is now available locally for historical research snapshots, but it remains an ex-post target source, not a same-morning production feed.

Engineering gates, schema checks, and implementation order are maintained in [Development Audit](audit/development.md). The current implementation status is maintained in [Results Snapshot](results_snapshot.md).

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
