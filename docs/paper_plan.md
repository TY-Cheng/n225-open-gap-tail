---
hide:
  - navigation
---

# Paper Plan

## Working Title

**Forecasting Pre-Open Tail Risk in Nikkei 225 Futures Using U.S. Close Information: A Session-Aligned LightGBM-EVT Framework**

This is a historical, session-aligned downside tail-risk forecasting study. The paper is not designed as a trading-system paper, and its contribution does not rest on presenting LightGBM-EVT as a new algorithm.

## Research Question and Contribution

The paper asks whether information available at the U.S. cash-market close helps forecast the lower tail of the next Osaka Exchange (OSE) Nikkei 225 Futures day-session open. The empirical object is the pre-open risk faced before the Japanese day session, not a generic Japanese equity overnight return.

The market structure matters. OSE Nikkei 225 Futures trade through an extended night session that overlaps the U.S. trading day and ends shortly before the Japanese day session. U.S. close information may therefore be partly incorporated into futures prices before the day-session open. The paper treats this as the central identification problem rather than as a technical calendar detail.

The empirical design separates full opening-gap risk from residual pre-open risk. Full gaps are measured relative to the previous settlement or previous day-session close; residual gaps are measured relative to a night-session or U.S.-close reference price when such a reference is available. This distinction determines whether U.S. close variables are interpreted as drivers of the full opening level or as incremental signals for unresolved pre-open risk.

The modeling framework has two roles. LightGBM is used as a flexible conditional layer for nonlinear cross-market predictors. Extreme value theory (EVT), implemented through a peaks-over-threshold tail model, is used to calibrate sparse downside losses and to support VaR and ES forecasts at lower-tail levels.

### Core Questions

- Can information frozen at the U.S. cash-market close improve timestamp-safe forecasts of lower-tail risk at the next OSE Nikkei 225 Futures day-session open?
- Does U.S. close information improve full opening-gap VaR and ES forecasts relative to Japan-only, historical, and econometric baselines?
- After accounting for OSE night-session information, does the U.S. close vector retain incremental content for residual pre-open downside risk?
- Does the LightGBM layer improve tail-event ranking, conditional scale, conditional quantiles, or VaR/ES calibration?
- Does the EVT layer improve extreme-tail extrapolation and ES severity calibration relative to LightGBM-only forecasts?
- Are results stable across roll windows, SQ windows, holiday-adjacent sessions, daylight-saving transitions, and stress regimes?

Upper-tail analysis is an optional appendix or robustness exercise. The main paper focuses on downside tail risk.

## Prior Literature and Positioning

Prior work supplies three things: the market-timing motivation, the correct peer model families, and the evaluation language expected by a tail-risk referee. This project combines those streams into a narrower object: one-step-ahead, session-aligned lower-tail forecasts for the next OSE Nikkei 225 Futures day-session open.

### U.S.-Japan Return and Volatility Transmission

| Stream / study | Research question | Data and forecast timing | Model or empirical design | Performance metrics or tests | Reported result | Conclusion and implication for this paper |
| --- | --- | --- | --- | --- | --- | --- |
| U.S.-Japan volatility spillovers: [Hamao, Masulis, and Ng (1990)](https://academic.oup.com/rfs/article/3/2/281/1595767) | Do major international equity markets transmit price and volatility shocks across opens and closes? | Daily opening and closing prices for Tokyo, London, and New York stock indexes around the pre-1987-crash period. | ARCH-family models for conditional means and volatility using open-to-close and close-to-open decompositions. | Sign and significance of return and volatility spillover parameters. | Reports volatility spillovers from New York to Tokyo and from London to Tokyo, with asymmetry across directions. | Establishes that Tokyo risk can respond to prior foreign-market information, but motivates careful session timing rather than close-to-close shortcuts. |
| U.S.-Japan intertemporal relation: [Becker, Finnerty, and Gupta (1990)](https://econpapers.repec.org/RePEc%3Abla%3Ajfinan%3Av%3A45%3Ay%3A1990%3Ai%3A4%3Ap%3A1297-1306) | Do U.S. stock returns predict the next Japanese market period, and are simple strategies profitable after frictions? | U.S. and Japanese equity-market open-to-close return timing. | Lead-lag return regressions and trading-simulation evidence. | Return correlation, simulated excess profits, and transaction-cost adjustment. | Finds high correlation between prior U.S. open-to-close returns and Japanese performance, but simulated profits vanish after costs and taxes. | Supports U.S. close information as a predictor candidate, while warning that predictability is not a trading-alpha claim. |
| As-the-world-turns spillovers: [Lin, Engle, and Ito (1991/1994)](https://www.nber.org/papers/w3911) | Are daytime and overnight returns and volatilities transmitted between Tokyo and New York? | Intraday data separating Tokyo daytime, Tokyo overnight, New York daytime, and New York overnight windows. | Intraday return and volatility spillover models with explicit market-hour ordering. | Lagged return and volatility coefficients, structural-break diagnostics around the 1987 crash. | Reports limited lagged spillovers except evidence of New York-to-Tokyo return spillover after the crash. | Reinforces that the forecast origin must be explicit; the paper should test U.S. close content after respecting OSE session structure. |
| Tokyo-New York volatility and volume: [Ito and Lin (1993/1994)](https://www.nber.org/papers/w4592) | Do volatility and trading volume explain cross-market return correlations between U.S. and Japanese markets? | Intraday U.S. and Japanese stock-market returns, volatility, and volume from 1985 to 1991. | Cross-market return, volatility, and volume interaction analysis. | Contemporaneous correlations, lagged volatility and volume spillover evidence, structural-change tests. | Finds significant contemporaneous correlations that rise in high-volatility periods, but little lagged volatility or volume spillover. | Suggests the paper should separate contemporaneous global-risk synchronization from useful ex ante tail forecasting. |

### Nikkei Futures and Cross-Venue Price Discovery

| Stream / study | Research question | Data and forecast timing | Model or empirical design | Performance metrics or tests | Reported result | Conclusion and implication for this paper |
| --- | --- | --- | --- | --- | --- | --- |
| Nikkei futures market competition: [Tse (2001)](https://www.sciencedirect.com/science/article/abs/pii/S0927539801000287) | How do margin changes and substitute Nikkei futures venues affect returns, volume, and volatility? | OSE, SIMEX, and CME Nikkei 225 futures market data around margin-policy changes. | Event-dummy econometric model with cross-market spillover terms. | Return, volume, volatility, and spillover responses around margin changes. | Reports dynamic responses across related Nikkei futures markets. | Motivates treating OSE Nikkei futures as part of a cross-venue information network rather than an isolated domestic contract. |
| Close-substitute futures dynamics: [Chou and Lee (2004)](https://www.sciencedirect.com/science/article/abs/pii/S1042444X04000052) | Does OSE margin policy affect trading dynamics and price discovery across OSE and SGX Nikkei 225 futures? | OSE and SGX Nikkei 225 futures, with attention to margin-policy spillovers. | Econometric analysis of close-substitute futures markets. | Price-discovery and volatility-spillover evidence. | Finds OSE margin policy influences both markets and reports SGX price-discovery evidence despite lower liquidity. | The paper should avoid assuming OSE day open is untouched by offshore or night-session information. |
| Multi-venue Nikkei price discovery: [Kao, Ho, and Fung (2015)](https://www.sciencedirect.com/science/article/pii/S1042443114001516) | Which venue contributes to Nikkei 225 price discovery across OSE, SGX, and CME futures? | Minute-level Nikkei 225 and S&P 500 futures data across exchanges. | Information share, component share, and Granger-causality style price-discovery analysis. | Price-discovery shares, causality tests, and cross-market adjustment measures. | Reports meaningful cross-venue information transmission in Nikkei futures markets. | U.S. close predictors may already be impounded through futures trading before OSE day open; night-session-controlled targets are essential. |
| Nonlinear spot-futures adjustment: [spot-futures Nikkei study (2023)](https://www.mdpi.com/1911-8074/16/2/117) | Are Nikkei spot-futures price adjustments linear, and which financial center leads? | Nikkei spot and futures prices across OSE, SGX, and CME. | Linear and smooth-transition price-adjustment analysis. | Adjustment coefficients, nonlinearity tests, and leadership evidence. | Studies whether price adjustment differs by venue, liquidity, and nonlinear dynamics. | Reinforces that simple linear spillover evidence is incomplete; the paper should present tail forecasts as predictive risk evidence, not structural price-discovery decomposition. |

### Japan-Specific Tail-Risk Predictability

| Stream / study | Research question | Data and forecast timing | Model or empirical design | Performance metrics or tests | Reported result | Conclusion and implication for this paper |
| --- | --- | --- | --- | --- | --- | --- |
| Japanese equity tail risk: [Andersen, Todorov, and Ubukata (2021)](https://ideas.repec.org/a/eee/econom/v222y2021i1p344-363.html) | Do option-implied volatility and tail-risk measures predict Japanese equity returns and FX-linked Japanese market performance? | U.S. and Japanese option-implied volatility and tail-risk measures for S&P 500, Nikkei 225, Japanese equity returns, and dollar-yen. | Predictive regressions with model-free volatility and tail-risk measures. | Regression significance and forecast-content evidence for Japanese excess returns and dollar-yen. | Reports weak Japan-only predictability but significant forecast power from U.S. option-implied tail risk, especially in U.S.-dollar terms. | Justifies U.S. risk indicators, volatility measures, USD/JPY, and global-risk variables as candidate predictors for Japanese downside risk. |
| U.S. option-implied global risk channel: [Andersen, Todorov, and Ubukata (2021)](https://www.sciencedirect.com/science/article/pii/S0304407620301950) | Is Japanese market predictability stronger when viewed through global-investor currency exposure? | Japanese equity and dollar-yen outcomes with U.S. and Japanese option-implied risk measures. | Cross-market predictive regression design. | Forecast-power and statistical-significance diagnostics. | Suggests the Japanese market is integrated with global risk channels even when domestic predictors look weak. | The empirical design should distinguish Japan-only baselines from U.S. close and FX/risk-augmented specifications. |

### Tail-Risk Forecasting Methods and Evaluation

| Stream / study | Research question | Data and forecast timing | Model or empirical design | Performance metrics or tests | Reported result | Conclusion and implication for this paper |
| --- | --- | --- | --- | --- | --- | --- |
| Conditional EVT: [McNeil and Frey (2000)](https://www.sciencedirect.com/science/article/pii/S0927539800000128) | How should tail-related risk measures be estimated for heteroscedastic financial returns? | Financial return series with time-varying volatility. | Two-stage conditional EVT: filter returns with GARCH-type volatility, then fit POT-GPD to standardized residual tails. | VaR and tail-risk backtesting evidence. | Establishes GARCH-EVT as a benchmark for heteroscedastic financial tail modeling. | LightGBM-EVT should be compared with GARCH-EVT and should apply EVT to filtered or standardized downside losses, not raw returns alone. |
| Direct VaR dynamics: [Engle and Manganelli (2004)](https://www.nber.org/papers/w7341) | Can conditional VaR be modeled directly without fully specifying the return distribution? | Financial return series for dynamic VaR estimation. | Conditional Autoregressive Value at Risk (CAViaR) via regression quantiles. | Dynamic quantile and VaR backtesting diagnostics. | Proposes direct conditional-quantile dynamics for VaR forecasting. | CAViaR is a natural peer baseline when the paper evaluates dynamic lower-tail quantiles. |
| VaR-ES scoring theory: [Fissler and Ziegel (2016)](https://arxiv.org/abs/1503.08123) | How can multi-dimensional functionals such as VaR and ES be evaluated with strictly consistent scoring functions? | Statistical decision-theory setting rather than one market dataset. | Elicitability and strictly consistent scoring-function theory. | Consistency conditions for scoring functions. | Shows how joint VaR-ES functionals can be evaluated coherently. | The paper should report joint VaR-ES scoring rather than treating ES as an informal severity statistic. |
| Dynamic ES and VaR: [Patton, Ziegel, and Chen (2019)](https://www.sciencedirect.com/science/article/pii/S030440761930048X) | Can dynamic semiparametric models jointly forecast ES and VaR? | Daily returns on international equity indices. | Dynamic semiparametric ES-VaR models using recent scoring-function theory. | Joint VaR-ES loss, simulation diagnostics, and out-of-sample forecast comparisons. | Reports that the proposed ES-VaR models can outperform GARCH and rolling-window forecasts in their application. | Provides the expected peer standard for ES modeling and joint evaluation. |
| ALD VaR-ES benchmark: [Taylor (2019)](https://www.tandfonline.com/doi/abs/10.1080/07350015.2017.1281815) | Can an asymmetric-Laplace likelihood be used to estimate and evaluate VaR and ES jointly? | Financial return forecasting setting for VaR and ES. | Semiparametric VaR-ES model based on asymmetric Laplace distribution. | AL log-likelihood and joint VaR-ES forecast evaluation. | Shows the AL log-likelihood is usable for strictly consistent joint VaR-ES evaluation. | A Taylor-style VaR-ES benchmark is desirable where implementation effort and sample size permit. |
| Covariate-conditioned EVT: [James et al. (2023)](https://www.sciencedirect.com/science/article/pii/S0927539823000026) | Can economic and financial covariates improve VaR and ES forecasts by affecting EVT tail scale? | U.S. equity-market data with a rich financial and economic information set. | Regularized extension of GARCH-EVT with sparse, time-varying covariates in the tail-risk model. | VaR and ES forecast accuracy against GARCH-EVT, GJR-GARCH, CAViaR, CARE, and Hawkes POT. | Reports improved VaR and ES forecasts during financial distress. | Supports the paper's conditional-learning plus EVT idea, but also requires disciplined comparison against non-ML tail-risk baselines. |
| ML tail-risk forecasting: [Gupta (2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5334625) | Can machine learning improve full-distribution, volatility, and tail-risk forecasts relative to GARCH-type models? | Fat-tailed asset price returns and multi-horizon distribution forecasts. | LightGBM and related ML distributional forecasting compared with GARCH-type models. | Log score, quantile loss, and volatility forecast error. | Reports better out-of-sample distributional, tail-risk, and volatility performance for LightGBM in that setting. | Motivates LightGBM as a conditional layer, while this paper still needs session-specific OSE evidence rather than borrowing ML superiority claims. |

### Positioning Against Prior Work

The paper is closest to the intersection of cross-market transmission and tail-risk forecasting, but it is not a direct replication of either literature. Transmission studies show that U.S. and Japanese markets are linked; they do not by themselves establish one-step-ahead lower-tail forecast value at the OSE day-session open. Tail-risk studies define the peer metrics and baselines; they do not solve the OSE session-alignment problem.

The paper makes four boundary choices explicit:

- The target is lower-tail OSE day-session opening-gap risk, not average return predictability.
- The forecast origin is the U.S. cash-market close, with timestamp-safe features only.
- J-Quants V2 futures daily data is a historical research target source, not a live pre-open production feed.
- Hedge-trigger and decision-usefulness diagnostics are risk-management diagnostics, not trading-profit or standalone alpha claims.

### Peer Models and Metric Comparability

The peer-comparable object is a one-step-ahead, session-aligned lower-tail forecast for the next OSE Nikkei 225 Futures day-session open. It is narrower than broad U.S.-Japan spillover work, which often studies mean or volatility transmission across equity indices, and narrower than high-frequency price-discovery work, which identifies where common price innovations are incorporated.

The model comparison should include forecasts that a tail-risk referee would expect:

- historical quantiles and rolling historical quantiles;
- volatility-scaled quantiles;
- simple linear or penalized specifications;
- GARCH-t and GJR-GARCH-t;
- GARCH-EVT;
- CAViaR where feasible;
- Taylor-style VaR-ES where feasible;
- LightGBM-only direct quantile, ranking, and exceedance-probability variants;
- LightGBM-EVT variants applied to raw, residual, or standardized downside losses.

Metrics should match the risk object. The main comparisons should use quantile loss, VaR coverage and independence tests, dynamic quantile diagnostics where feasible, joint VaR-ES scoring, ES exceedance-severity diagnostics, tail-event ranking metrics, and fixed-rule hedge-trigger diagnostics.

### Intended Contribution

The paper contributes a session-aligned target construction and evaluation design for OSE Nikkei 225 Futures pre-open downside risk. It tests whether U.S. close-side variables add lower-tail forecasting content beyond Japan-only and, where data permit, night-session-controlled benchmarks. It also evaluates a conditional-learning plus EVT calibration framework against peer econometric and machine-learning baselines.

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

The baseline layer should include historical quantiles, rolling historical quantiles, volatility-scaled quantiles, simple linear or penalized specifications, GARCH-t, GJR-GARCH-t, GARCH-EVT, CAViaR, and a Taylor-style VaR-ES model where feasible.

The LightGBM layer should be evaluated in more than one role: conditional location, conditional scale, direct quantile forecasting, tail-event ranking, and exceedance-probability forecasting. The EVT layer should then be applied to downside losses, filtered residual losses, standardized losses, or conditional exceedance severities. Thresholds and transformations are estimated inside the training window, and empirical tail levels should be distinguished from extrapolated tail levels.

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
| Literature-positioning matrix | Shows how the paper differs from transmission, price-discovery, and tail-risk forecasting studies. |
| Incremental information table | Compares Japan-only, U.S.-only, combined, FX/risk-augmented, night-controlled, and full models. |
| Baseline model comparison table | Compares historical, volatility-scaled, GARCH, GARCH-EVT, CAViaR, LightGBM-only, and LightGBM-EVT variants. |
| VaR-ES evaluation table | Reports quantile loss, coverage, independence, joint VaR-ES score, and ES severity diagnostics. |
| EVT threshold diagnostics figure | Shows threshold stability, exceedance counts, and tail-parameter behavior. |
| Hedge-trigger diagnostic table | Reports false positives, missed events, turnover, and loss avoided under fixed assumptions. |

## Evidence Gates

- **Target-data audit gate.** Before empirical claims, the project must download bounded J-Quants V2 futures daily/session samples, record schema and field coverage, verify contract and session semantics, and trace extreme opening gaps back to raw rows.
- **Timestamp-safety gate.** Every predictor row must have an availability timestamp strictly before the forecast target open. Features released after the U.S. close cannot enter the U.S.-close forecast origin.
- **Night-session gate.** Full opening-gap and residual pre-open targets must be separated. If OSE night-close or U.S.-close Nikkei futures marks are unavailable, residual targets must remain disabled or marked as extensions.
- **Baseline gate.** LightGBM-EVT results must be compared with historical, volatility-scaled, GARCH-family, GARCH-EVT, CAViaR, and feasible VaR-ES baselines before model-quality claims are made.
- **EVT gate.** Tail levels must satisfy minimum exceedance counts; thresholds, tail parameters, and extrapolated levels must be reported with diagnostics.
- **Manuscript-claim gate.** Hedge-trigger outputs are risk-management diagnostics only. They are not trading-alpha, causal, or live-deployment evidence.

## Boundaries and Readiness

Paper-grade empirical claims require completed OSE Nikkei 225 Futures target-data audit, not merely API access. J-Quants V2 futures daily data should be treated as an ex-post historical research source. It is not a live pre-open production feed, and it does not supply a U.S.-close intraday Nikkei futures reference mark unless a separate licensed timestamped feed exists.

`residual_usclosemark_to_open` remains an extension until a licensed intraday Nikkei futures reference mark is available at the U.S. cash close. A live pre-open deployment would require live OSE, CME, SGX, or equivalent futures feeds; J-Quants daily/session data is a historical research source.

Engineering gates, schema checks, and implementation order are maintained in [Development Audit](audit/development.md). The current implementation status is maintained in [Results Snapshot](results_snapshot.md).

## Source Notes

- JPX trading hours: [Trading Hours | Derivatives | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/rules/trading-hours/index.html)
- J-Quants data timing: [Update Timing of Provided Data | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-update)
- J-Quants MCP/API documentation is useful for endpoint and sample-code lookup, but it is not empirical evidence: [MCP Server - J-Quants API Reference](https://jpx-jquants.com/en/spec/mcp-server)
- Massive.com stock-market timestamp semantics: [Stocks Overview | Massive.com](https://massive.com/docs/rest/stocks/overview)
- LightGBM objectives, including quantile objective: [LightGBM Parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html)
