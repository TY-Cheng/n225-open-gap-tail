# Paper Plan

## Working Title

**Forecasting Pre-Open Tail Risk in Nikkei 225 Futures Using U.S. Close Information: A Session-Aligned LightGBM-EVT Framework**

This is a historical, session-aligned downside tail-risk forecasting study. The paper is not designed as a trading-system paper, and its contribution does not rest on presenting LightGBM-EVT as a new algorithm.

## Core Argument

The paper asks whether information available at the U.S. cash-market close helps forecast the lower tail of the next Osaka Exchange (OSE) Nikkei 225 Futures day-session open. The empirical object is the pre-open risk faced before the Japanese day session, not a generic Japanese equity overnight return.

The market structure matters. OSE Nikkei 225 Futures trade through an extended night session that overlaps the U.S. trading day and ends shortly before the Japanese day session. U.S. close information may therefore be partly incorporated into futures prices before the day-session open. The paper treats this as the central identification problem rather than as a technical calendar detail.

The empirical design separates full opening-gap risk from residual pre-open risk. Full gaps are measured relative to the previous settlement or previous day-session close; residual gaps are measured relative to a night-session or U.S.-close reference price when such a reference is available. This distinction determines whether U.S. close variables are interpreted as drivers of the full opening level or as incremental signals for unresolved pre-open risk.

The modeling framework has two roles. LightGBM is used as a flexible conditional layer for nonlinear cross-market predictors. Extreme value theory (EVT), implemented through a peaks-over-threshold tail model, is used to calibrate sparse downside losses and to support VaR and ES forecasts at lower-tail levels.

## Research Questions

The main research question is:

> Can information frozen at the U.S. cash-market close improve timestamp-safe forecasts of lower-tail risk at the next OSE Nikkei 225 Futures day-session open?

Secondary questions:

- Does U.S. close information improve full opening-gap VaR and ES forecasts relative to Japan-only, historical, and econometric baselines?
- After accounting for OSE night-session information, does the U.S. close vector retain incremental content for residual pre-open downside risk?
- Does the LightGBM layer improve tail-event ranking, conditional scale, conditional quantiles, or VaR/ES calibration?
- Does the EVT layer improve extreme-tail extrapolation and ES severity calibration relative to LightGBM-only forecasts?
- Are results stable across roll windows, SQ windows, holiday-adjacent sessions, daylight-saving transitions, and stress regimes?

Upper-tail analysis is an optional appendix or robustness exercise. The main paper focuses on downside tail risk.

## Prior Literature and Intended Contribution

This project sits between three literatures: international U.S.-Japan information transmission, futures price discovery across time zones, and conditional tail-risk forecasting. The paper's contribution is empirical and design-based: it studies U.S. close information as a timestamped predictor of OSE Nikkei 225 Futures day-session lower-tail opening risk, with explicit controls for market sessions and data availability.

### Closest Literature

| Literature stream | Representative studies | Data and question | Models and metrics | Main lesson for this paper |
| --- | --- | --- | --- | --- |
| U.S.-Japan return and volatility transmission | [Hamao, Masulis, and Ng (1990)](https://academic.oup.com/rfs/article/3/2/281/1595767), [Lin, Engle, and Ito (1991/1994)](https://www.nber.org/papers/w3911), [Becker, Finnerty, and Gupta (1990)](https://ideas.repec.org/a/bla/jfinan/v45y1990i4p1297-1306.html) | Open/close or intraday index returns across Tokyo, New York, and London. | ARCH-family models, daytime and overnight decompositions, lead-lag regressions, trading simulations. | Cross-market dependence is well documented, but its interpretation depends on session timing and trading frictions. |
| Futures price discovery across time zones | [Kao, Ho, and Fung (2015)](https://www.sciencedirect.com/science/article/pii/S1042443114001516) and related spot-futures linkage studies | Minute-level Nikkei 225 and S&P 500 futures across OSE, SGX, and CME. | Information shares, component shares, Granger causality. | Nikkei futures already incorporate information across time zones; the relevant question is incremental pre-open tail-risk content after the night session. |
| Japanese equity tail-risk predictability | [Andersen, Todorov, and Ubukata (2021)](https://www.sciencedirect.com/science/article/pii/S0304407620301950) | U.S. and Japanese option-implied volatility and tail-risk measures for Japanese equity and FX prediction. | Predictive regressions with model-free volatility and tail-risk measures. | U.S. risk measures and USD/JPY are natural predictors for Japanese market risk, especially from a global-investor perspective. |
| Conditional EVT and econometric tail-risk forecasting | [McNeil and Frey (2000)](https://www.sciencedirect.com/science/article/pii/S0927539800000128), [James et al. (2023)](https://www.sciencedirect.com/science/article/pii/S0927539823000026), [Engle and Manganelli (2004)](https://www.nber.org/papers/w7341) | Daily financial losses and one-step-ahead VaR/ES forecasting. | GARCH-EVT, covariate-conditioned EVT, CAViaR, GJR-GARCH, POT-GPD. | EVT is most persuasive when applied to filtered or standardized losses and compared with established tail-risk baselines. |
| VaR-ES evaluation and ML tail-risk forecasting | [Fissler and Ziegel (2016)](https://arxiv.org/abs/1503.08123), [Patton, Ziegel, and Chen (2019)](https://www.sciencedirect.com/science/article/pii/S030440761930048X), [Taylor (2019)](https://www.tandfonline.com/doi/full/10.1080/07350015.2017.1281815), [Barrera et al. (2022)](https://arxiv.org/abs/2209.06476), [Gupta (2025)](https://papers.ssrn.com/sol3/Delivery.cfm/5334625.pdf?abstractid=5334625&mirid=1) | Financial loss distributions, VaR/ES scoring, and machine-learning risk forecasts. | Joint VaR-ES scoring, ALD-based VaR-ES models, statistical learning, LightGBM forecasts. | LightGBM-EVT should be evaluated with the same tail-risk metrics used for econometric VaR/ES models. |

### Peer-Comparable Boundary

The peer-comparable object is a one-step-ahead, session-aligned lower-tail forecast for the next OSE Nikkei 225 Futures day-session open. It is narrower than broad U.S.-Japan spillover work, which often studies mean or volatility transmission across equity indices, and narrower than high-frequency price-discovery work, which identifies where common price innovations are incorporated.

The paper makes three boundary choices explicit: the target is downside opening-gap risk rather than average return predictability; the forecast origin is the U.S. cash-market close rather than an unrestricted overnight information set; and the claim is incremental historical risk-forecasting content rather than structural causality or deployable trading profitability.

### Peer Models and Metric Comparability

The model comparison should include forecasts that a tail-risk referee would expect: historical and rolling historical quantiles, volatility-scaled quantiles, GARCH-t or GJR-GARCH-t, GARCH-EVT, CAViaR where feasible, a Taylor-style VaR-ES benchmark where feasible, LightGBM-only quantile forecasts, and LightGBM-EVT variants.

Metrics should match the risk object. The main comparisons should use quantile loss, VaR coverage and independence tests, dynamic quantile diagnostics where feasible, joint VaR-ES scoring, ES exceedance-severity diagnostics, tail-event ranking metrics, and fixed-rule hedge-trigger diagnostics.

### Intended Contribution

The paper contributes a session-aligned target construction and evaluation design for OSE Nikkei 225 Futures pre-open downside risk. It tests whether U.S. close-side variables add lower-tail forecasting content beyond Japan-only and, where data permit, night-session-controlled benchmarks. It also evaluates a conditional-learning plus EVT calibration framework against peer econometric and machine-learning baselines.

### Expected Evidence and Contribution Boundaries

The strongest evidence would be a stable rolling out-of-sample improvement in lower-tail calibration and ES severity after adding U.S. close variables, especially relative to Japan-only, historical, GARCH-EVT, CAViaR, and LightGBM-only baselines. Feature importance summaries are secondary; the main evidence is incremental information, calibration, scoring, and robustness.

A positive result would support timestamp-safe historical risk forecasting for pre-open risk management. It would not establish a structural causal channel, standalone trading alpha, or live deployability. A negative or attenuated result after night-session controls would also be informative, because it would show that much of the U.S. close information is already absorbed before the day-session open.

## Data, Targets, and Forecast Origin

The canonical data contract is maintained in [Data Design and Contract](data.md). That page defines source roles, forecast origins, target hierarchy, timestamp fields, tail-risk labels, and feature families. The paper plan uses that contract without duplicating vendor fields or ticker lists.

The paper-facing target hierarchy is:

- Main target: `full_gap_settle_to_open`.
- Secondary full-gap target: `full_gap_close_to_open`.
- Robustness target: `residual_nightclose_to_day_open`.
- Extension target: `residual_usclosemark_to_open`, available only with a licensed intraday Nikkei futures reference mark at the U.S. cash close.

Empirical tables should state the forecast origin, target family, reference price, information cutoff, and data-source status. This is especially important when comparing full opening-gap forecasts with residual pre-open forecasts.

## Empirical Design

The empirical design uses chronological out-of-sample evaluation. Random train/test splits are inappropriate because the forecast object is explicitly time ordered. The preferred structure is an initial training window, a validation window, and a final test window, with rolling or expanding retraining for the final evaluation.

The main incremental-information sequence is:

1. Japan-only.
2. U.S.-only.
3. Japan plus U.S. close.
4. Japan plus U.S. close plus FX.
5. Japan plus U.S. close plus risk indicators.
6. Night-session-controlled model where a night close or U.S.-close Nikkei futures mark is available.
7. Full LightGBM-EVT specification.

The baseline layer should include historical quantiles, rolling historical quantiles, volatility-scaled quantiles, simple linear or penalized specifications, and econometric tail-risk models such as GARCH-t, GJR-GARCH-t, GARCH-EVT, and CAViaR where feasible.

The LightGBM layer should be evaluated in more than one role: conditional location, conditional scale, direct quantile forecasting, and exceedance-probability forecasting. The EVT layer should then be applied to downside losses, filtered residual losses, standardized losses, or conditional exceedance severities. Thresholds and transformations are estimated inside the training window, and empirical tail levels should be distinguished from extrapolated tail levels.

## Evaluation Strategy

Forecast calibration is the primary evaluation dimension. VaR forecasts should be assessed with quantile loss, unconditional coverage, independence or conditional coverage tests, and dynamic quantile diagnostics where feasible. ES forecasts should be assessed with joint VaR-ES scoring and exceedance-severity diagnostics.

Tail ranking is a complementary diagnostic. Precision at the top of the ranked risk distribution, recall among realized tail events, hit rates, and event concentration help distinguish models that rank dangerous openings well from models that merely match unconditional coverage.

Decision usefulness should be reported as a risk-management diagnostic. A fixed hedge-trigger rule can summarize false positives, missed events, turnover, and loss avoided under stated assumptions. These diagnostics should not be interpreted as a trading-alpha test.

Model-comparison inference should use Diebold-Mariano tests with block bootstrap or a Model Confidence Set where feasible. The inference target is forecast quality under chronological evaluation, not in-sample fit.

## Manuscript Structure

### 1. Introduction

- Motivate OSE Nikkei 225 Futures day-session pre-open downside risk.
- Explain why the OSE night session changes the interpretation of U.S. close information.
- State the session-aligned LightGBM-EVT contribution without presenting the model combination as a standalone novelty.

### 2. Market Structure, Data, and Target Construction

- Describe the OSE day and night sessions, U.S. close predictors, and J-Quants futures target source.
- Define forecast origins, reference prices, target families, roll handling, and information cutoffs.
- Present target coverage, distribution, tail counts, and extreme-event tracebacks.

### 3. Methodology

- Define the incremental information tests and baseline models.
- Describe the LightGBM conditional layer and the POT-EVT tail calibration layer.
- Explain rolling estimation, threshold selection, and timestamp controls.

### 4. Empirical Design

- Define train, validation, and test periods.
- Specify feature groups, model variants, and ablations.
- Define VaR, ES, tail-ranking, and hedge-trigger diagnostics.

### 5. Results

- Begin with incremental information results rather than a model leaderboard.
- Compare Japan-only, U.S.-only, combined, night-controlled, and full LightGBM-EVT specifications.
- Discuss calibration, ES severity, tail ranking, and feature interpretation.

### 6. Robustness

- Consider alternative target families, thresholds, and tail levels.
- Examine roll windows, SQ windows, holiday-adjacent sessions, daylight-saving regimes, and stress periods.
- Include upper-tail results only if they add evidence beyond the main downside analysis.

### 7. Conclusion

- Summarize whether U.S. close information contains timestamp-safe incremental downside-tail content.
- State the limits imposed by data availability, night-session absorption, and live-feed requirements.
- Identify natural extensions to intraday marks and options-implied tail-risk measures.

## Planned Tables and Figures

| Manuscript item | Purpose |
| --- | --- |
| Forecast-origin and target-definition table | Defines the information cutoff, reference price, and target family used in each empirical design. |
| Target audit and tail-count table | Reports coverage, missingness, tail counts, roll/SQ flags, holiday-adjacent sessions, and extreme-gap tracebacks. |
| Incremental information table | Compares Japan-only, U.S.-only, combined, FX/risk-augmented, night-controlled, and full models. |
| VaR-ES evaluation table | Reports quantile loss, coverage, independence, joint VaR-ES score, and ES severity diagnostics. |
| EVT threshold diagnostics figure | Shows threshold stability, exceedance counts, and tail-parameter behavior. |
| Hedge-trigger diagnostic table | Reports false positives, missed events, turnover, and loss avoided under fixed assumptions. |

## Boundaries and Readiness

Paper-grade empirical claims require OSE Nikkei 225 Futures target data. The current J-Quants free plan can support API smoke checks, but it cannot support final futures target evidence. The current implementation status is maintained in [Results Snapshot](results_snapshot.md).

`residual_usclosemark_to_open` remains an extension until a licensed intraday Nikkei futures reference mark is available at the U.S. cash close. A live pre-open deployment would require live OSE, CME, SGX, or equivalent futures feeds; J-Quants daily/session data is a historical research source.

Engineering gates, schema checks, and implementation order are maintained in [Development Audit](audit/development.md). This paper plan intentionally avoids duplicating those instructions.

## Source Notes

- JPX trading hours: [Trading Hours | Derivatives | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/rules/trading-hours/index.html)
- J-Quants data timing: [Update Timing of Provided Data | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-update)
- Massive.com stock-market timestamp semantics: [Stocks Overview | Massive.com](https://massive.com/docs/rest/stocks/overview)
- LightGBM objectives, including quantile objective: [LightGBM Parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html)
