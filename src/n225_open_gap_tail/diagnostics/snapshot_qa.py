# ruff: noqa: E501
from __future__ import annotations


def discussion_qa_markdown(
    *,
    advanced_implementation_text: str,
    advanced_implementation_bullet: str,
    advanced_bottom_line_bullet: str,
    claim_scope_table: str,
    opening_gap_scale_text: str,
) -> str:
    return f"""## Discussion Q&A

### What is the empirical question?

The study asks whether information observable by the U.S. cash-market close improves point-in-time forecasts of OSE Nikkei 225 Futures opening-tail risk.

- The object is the next OSE day-session open of the large Nikkei 225 Futures contract.
- The study evaluates left-tail and right-tail risks separately because both are economically relevant for futures positions.
- The comparison is built around nested information sets: Japan-only history, U.S. close core variables, Japan proxy ETFs, Asia proxy ETFs, and an audit-gated options-risk layer that remains disabled unless historical options data pass source, coverage, liquidity, and timestamp checks.
- The snapshot reports research-candidate evidence. It is not a model-selection statement by itself.

### Why is this an economically meaningful risk problem?

Opening gaps matter because leveraged futures positions can face margin, liquidity, and risk-limit pressure before regular day-session liquidity is available.

{opening_gap_scale_text}

- JPX describes Nikkei 225 Futures as margin-based leveraged contracts and warns that leverage affects losses as well as profits; under market stress, additional cash margin can be needed and losses can exceed the deposited margin ([JPX Nikkei 225 Futures overview](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/)).
- JPX's margin overview gives the general mechanism: adverse futures and options price movements can create significant losses, and margin is posted to ensure payments when losses occur ([JPX margin overview](https://www.jpx.co.jp/english/derivatives/rules/margin/)).
- JSCC's futures/options margin rules make the channel operational: listed derivatives are margined through JSCC, customer positions require margin, and intraday/emergency margin calls can apply; the emergency margin-call list explicitly includes Nikkei 225 Futures ([JSCC Margin on Futures and Options](https://www.jpx.co.jp/jscc/en/cash/futures/marginsystem/margin.html)).
- JSCC also has margin add-ons for liquidity and concentration risk, including the index-futures group containing Nikkei 225 Futures ([JSCC Margin Add-on Rules](https://www.jpx.co.jp/jscc/en/cash/futures/marginsystem/addonim.html)).
- This does not mean every margin account is mechanically recalculated and called exactly at the 08:45 JST open. The opening price immediately changes mark-to-market PnL, account equity, risk limits, liquidity needs, and broker/internal margin pressure; formal JSCC margin calls follow scheduled or event-triggered procedures such as intraday and emergency margin calls.
- Optiver's discussion of Japan's open-based settlement methodology for Large Nikkei 225 Index Options is related market-structure motivation: it documents why opening-price formation and SQ methodology can have large derivatives PnL consequences. That is related opening-settlement evidence, not direct evidence for the current futures settle-to-open forecast target ([Optiver, 2024](https://optiver.com/insights/how-japans-settlement-price-methodology-impacts-option-expiry/)).
- Historical cases such as Barings motivate the channel, but they are not direct sample evidence ([GOV.UK Barings inquiry report](https://www.gov.uk/government/publications/report-into-the-collapse-of-barings-bank); [Steenbeek 1999, Bank of Japan edited volume metadata](https://pure.eur.nl/en/publications/price-discovery-during-periods-of-stress-barings-the-kobe-quake-a/)).

### What is forecast, and how is the target constructed?

The current headline target is the loss version of the settle-to-open gap: `gap_t = full_gap_settle_to_open`.

- For left-tail models, the positive loss is `-gap_t`; for right-tail models, it is `gap_t`.
- The target source is the OSE Nikkei 225 Futures large contract, not mini or micro contracts.
- J-Quants futures rows are filtered to central-contract-month observations, and the target audit requires the day-session open and the previous reference settlement or close to come from the same contract where possible.
- Observations are removed from clean target evidence when they cross a contract roll, last-trading-day boundary, SQ window, invalid reference price, or missing target field.
- The model sample pools clean observations across successive central quarterly contracts. This is an active-contract risk process, not a naive continuous-price splice.
- `full_gap_close_to_open` is carried for audit and alternative diagnostics. It is not the current headline target.
- `residual_nightclose_to_day_open` is used for residual and absorption diagnostics when the night close is available.
- A pure U.S.-close-mark-to-open target would require a licensed timestamped Nikkei futures mark at the U.S. close cutoff. That target is disabled in this run.

### Why use the OSE Nikkei 225 large contract rather than SGX or CME Nikkei contracts?

The target is the home-market OSE large-contract opening risk surface.

- The OSE large contract is the native JPX/OSE Nikkei 225 Futures contract with JPX/JSCC-published trading hours, contract size, SQ, margin, and clearing rules. JPX defines the large-contract unit as `Nikkei 225 x JPY 1,000` ([JPX contract specifications](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)).
- Optiver describes OSE Nikkei 225 Index futures as the largest, most international, and most liquid APAC futures market. That is market-structure motivation for using OSE as the benchmark venue, not a formal volume-ranking result estimated in this project ([Optiver, 2024](https://optiver.com/insights/how-japans-settlement-price-methodology-impacts-option-expiry/)).
- The settlement anchor is Japanese: JPX defines the final settlement price as Special Quotation, with SQ based on the opening prices of Nikkei 225 component stocks on the business day after the last trading day ([JPX contract specifications](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)).
- SGX and CME Nikkei contracts are important offshore venues, and the cross-market Nikkei futures literature explicitly studies price discovery across OSE, SGX, and CME. The current paper does not claim those venues are irrelevant ([Spot-Futures Price Adjustments in the Nikkei 225](https://www.mdpi.com/1911-8074/16/2/117)).
- They are not the headline target because the current audited target source is J-Quants OSE contract-level session data. The current run does not include licensed timestamped SGX/CME/OSE intraday marks at the U.S. close cutoff.
- A cross-venue extension could forecast CME/SGX-to-OSE-open residual risk or hedge-slippage risk. That is a useful but different target from the current OSE home-market opening-risk design.

### Why focus on the OSE open?

The open is where next Japanese day-session price formation, settlement mechanics, and risk control meet.

- The OSE day-session open is the first OSE day-session mark after the U.S.-close information cutoff and after the Japanese night-session interval.
- JPX's contract specifications make the open directly relevant for expiry mechanics because Nikkei 225 Futures final settlement uses SQ based on Nikkei component opening prices after the last trading day ([JPX contract specifications](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)).
- Optiver argues that Nikkei 225 index options are unusual in expiring at the cash-market open and that opening-price formation can be imbalance-sensitive. That is external market-structure support for studying open-based tail risk, even though the Optiver article is about index options rather than this futures forecast target ([Optiver, 2024](https://optiver.com/insights/how-japans-settlement-price-methodology-impacts-option-expiry/)).
- The current target diagnostics show that settle-to-open and night-close-to-open residual moves can be large enough to matter for VaR/ES forecasting.
- The margin link is indirect but operationally important: the open changes mark-to-market PnL, account equity, limits, and collateral pressure, while formal JSCC margin calls follow scheduled or event-triggered procedures ([JSCC Margin on Futures and Options](https://www.jpx.co.jp/jscc/en/cash/futures/marginsystem/margin.html)).
- This does not mean the open is the only economically relevant price. Close-to-open and night-close-to-open variants are carried as audit or diagnostic targets; the headline target is chosen because it is the cleanest home-market opening-risk object under the current data contract.

### Does the opening-gap target assume no CME or OSE night-session trading?

No. The empirical object is OSE day-session opening risk, not a claim that institutions cannot trade or hedge Nikkei exposure through CME, SGX, or OSE night-session products.

- The headline target is an OSE large-contract settle-to-open risk surface. CME and SGX Nikkei marks are not used in the current headline run.
- JPX lists Nikkei 225 Futures trading hours as `08:45-15:45` and `17:00-06:00`, so the OSE night session is part of the market structure rather than an omitted concept ([JPX contract specifications](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)).
- The OSE night session is not ignored in the audit layer: J-Quants night-session fields are carried, `residual_nightclose_to_day_open` is available as a diagnostic when the night close is present, and the timing map records the U.S.-close-to-OSE-night-close interval and absorption-regime indicators.
- What is not yet modeled is a continuously hedged cross-venue residual such as `log(OSE day open) - log(Nikkei futures mark at the U.S. close cutoff)`. That requires a licensed timestamped OSE, CME, SGX, or equivalent Nikkei futures mark at the cutoff.
- The correct manuscript claim is therefore opening-risk forecasting from information available by the U.S. close cutoff, not all Nikkei overnight risk and not realized hedging performance for a continuously managed global book.
- This is still a meaningful risk-management object for local opening-auction exposure, limit utilization, collateral planning, liquidity needs, and accounts that cannot or do not fully rebalance across venues before the OSE day open.

### Does settle-to-open include SQ final-settlement risk?

Only as audit history, not as headline clean evidence.

- `full_gap_settle_to_open` can be computed for rows that are later marked as roll/SQ-window rows, but the headline clean sample excludes those rows.
- The current target-audit rule excludes the roll/SQ window starting five JPX sessions before the last trading day through SQ day; excluded rows carry `missing_reason = roll_sq_excluded`.
- Therefore the headline target is mainly daily settlement-to-next-OSE-day-open risk. It is not an SQ expiry/final-settlement event study.
- SQ is economically related because JPX defines Nikkei 225 Futures final settlement price as Special Quotation, with SQ based on the Nikkei 225 component opening prices on the business day after the last trading day ([JPX contract specifications](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)). Optiver's Nikkei options note gives a related open-based settlement example, but SQ should be studied through a separate event-study or robustness module rather than mixed into the headline clean sample.

### How are look-ahead bias controls handled?

The forecast origin is the U.S. close plus the relevant vendor lag, and it must occur before the OSE target open.

- Every joined predictor is audited against `feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`.
- "U.S. close information" means information available by the cutoff. It does not include all after-close or overnight news.
- FRED features are treated with conservative release lags, but FRED historical values are not ALFRED vintage-safe.
- The requested data window begins before the forecast sample. The clean forecast sample starts only when target fields, J-Quants futures coverage, Massive coverage, FRED coverage, and canonical FX timing satisfy the registered gates.
- Earlier rows can support cache checks, target-history construction, and training history, but they are not forecast evidence under the current clean-sample contract.

### What information enters the forecasts?

Benchmark models and ML models answer related but different questions.

- Benchmark models are target-history-only reference models. Historical and rolling quantiles use empirical target distributions; EWMA, GARCH, GJR-GARCH, and EVT-style benchmarks estimate volatility or tail scaling; CAViaR, CARE, GAS, and Taylor/FZ-style variants add stateful tail-risk dynamics.
- ML Model A, `japan_only`, uses lagged clean losses and gaps, rolling moments, rolling tail summaries, lagged N225 futures session/volume/OI features, lagged J-Quants N225 large-option implied-state aggregates, calendar month terms, DST, and absorption-regime indicators. It does not use U.S. close predictor blocks.
- The later ML information sets add U.S. ETF, sector, rates, volatility, FX, credit-risk, and minute-based U.S. close features, followed by Japan proxy ETFs and Asia proxy ETFs.
- Daily ETF and asset-market blocks use close-to-close log returns and log high-low ranges, frozen at the audited U.S. close cutoff.
- FRED, Cboe, rates, volatility, and USD/JPY blocks use levels, first differences, staleness and release-lag diagnostics, and Cboe VIX range where available.
- The minute block includes late-session returns, realized variance, up/down semivariance, range, final-window momentum, and within-ticker volume-pressure measures. Minute skewness and kurtosis are recorded as noisy small-sample diagnostics.
- J-Quants N225 large-option features are domestic `japan_only` predictors and use only prior available option-chain aggregates. The U.S.-listed options-risk layer is registered but not active headline evidence unless historical options entitlement, liquidity, coverage, and timestamp checks pass.

### What models are compared?

{advanced_implementation_text}

- Benchmark floor models include target-history baselines and GARCH/EVT-style econometric floors.
- {advanced_implementation_bullet}
- ML-tail models include direct LightGBM quantile, location-scale empirical tail calibration, and standardized-loss POT-GPD variants.
- LightGBM is used as a fixed, tabular, nonlinear learner for the nested-information-set experiment, not as an algorithmic novelty claim.
- Hyperparameters are held fixed across information sets and refit dates to limit data-dependent tuning.
- Advanced econometric benchmarks are still benchmarks. They are more specialized target-history-only comparators, not a third headline contribution.

### How do the LightGBM tail variants work?

The direct-quantile model estimates the VaR level directly. The location-scale and POT-GPD variants separate conditional filtering from tail calibration.

- The location-scale variant first estimates the conditional center and conditional scale of positive losses, then estimates the high tail on standardized losses.
- For each monthly refit, training uses clean history strictly before the forecast date.
- Blocked expanding out-of-sample predictions are used to construct prior standardized losses, so tail calibration is not based on full-sample residuals.
- The empirical location-scale model maps standardized VaR and ES back to loss units as `location + scale times standardized tail level`.
- The POT-GPD variants fit a Generalized Pareto tail to out-of-fold standardized losses above the registered 0.90 threshold.
- Plain MLE remains the standard filtered-EVT comparator.
- The stabilized POT-GPD variant is a finite-sample regularized filtered-EVT variant. It uses diagnostic EVI anchoring, extremal-index weighting, shape caps, and a conditional scale refit where available. Intermediate capped-MLE, EVI-shrink, and EI-weighted variants are ablation evidence.
- Location-scale and POT-GPD rows enter headline tables only if their OOS coverage, standardized-loss counts, exceedance counts, ES validity, and common-sample gates pass.

### How are forecasts evaluated?

The evaluation is a tail-risk forecast panel, not a single leaderboard.

- The core headline columns are `rows`, `var_breach_rate`, `expected_breach_rate`, `exceedance_count`, `kupiec_pvalue`, `christoffersen_pvalue`, `mean_quantile_loss`, `mean_fz_loss`, and `mean_exceedance_severity`.
- At `tail_level = 0.95`, the nominal breach rate is 5%.
- `var_breach_rate` should be close to `expected_breach_rate`; it is not better simply because it is smaller.
- Kupiec tests unconditional VaR coverage. Christoffersen tests whether exceptions show serial dependence.
- Quantile loss evaluates VaR forecasts. Fissler-Ziegel loss evaluates joint VaR-ES forecast pairs where valid ES forecasts exist.
- Mean exceedance severity measures how far realized losses exceed VaR conditional on an exception, so it must be read with exception counts and coverage.
- DM and MCS records are average-sample inference on registered loss differentials. They do not establish conditional predictive ability.
- CPA records are conditional loss-difference diagnostics: loss differentials are regressed on ex-ante observables such as VIX, DST, absorption timing, and lagged loss differences. CPA does not generate VaR or ES forecasts.
- Murphy diagrams, stress-window summaries, DST attenuation, ES severity, and trigger diagnostics are supporting evidence, not replacements for headline coverage and inference gates.

### How should the current benchmark-versus-ML pattern be read?

The current evidence should be read as a coverage-versus-scoring tradeoff.

- Benchmark floor rows generally have breach rates closer to the nominal 5% VaR level.
- Some LightGBM information sets show lower average loss on the registered sample, but their VaR breach rates are higher than nominal.
- Lower loss may partly reflect less conservative VaR estimates rather than better conditional tail calibration.
- The safer interpretation is not that LightGBM as an algorithm defeats the econometric benchmark suite. The safer interpretation is that nested ML information sets test whether point-in-time U.S. close information changes tail-loss forecasts beyond target-history baselines.
- Any lower-loss statement must be read together with coverage, exception counts, Kupiec/Christoffersen diagnostics, DM/MCS, CPA diagnostics, and common-sample gates.

### What do left-tail and right-tail results imply?

Left-tail and right-tail forecasts are both real futures risk surfaces, but they should not be combined into one symmetric mechanism.

- The left tail corresponds to adverse downside opening gaps; the right tail corresponds to adverse upside opening gaps for short exposure.
- The current artifacts show different left/right patterns, including differences in coverage, information-set changes, and DST diagnostics.
- The paper should report both sides separately and avoid averaging them into one tail-risk result.
- Feature-level explanations remain descriptive unless supported by a dedicated attribution design.
- Proxy-block patterns should not be written as structural regional price-discovery claims.

### Which evidence can support manuscript claims?

{claim_scope_table}

- Headline claims require a clean committed run, a shared common sample, zero leakage failures, and author-reviewed tables.
- Restricted rows can explain model-family behavior on matched dates, but they cannot replace the headline nested-information-set evidence.
- Diagnostic rows can motivate interpretation and future checks, but they should not be worded as model-selection or risk-management usefulness claims without their own evidence gates.

### What are the main manuscript risks and feasible paper framing?

The main risk is not whether the pipeline ran; it is whether the claims stay inside the evidence.

- ML headline breach rates are high relative to the nominal VaR level, even where loss metrics improve.
- EVT and location-scale models are implemented, but their headline status depends on OOS coverage, ES validity, and common-sample gates.
- FRED is conservatively lagged but not ALFRED vintage-safe.
- The residual U.S.-close-mark target is disabled because a licensed timestamped Nikkei futures mark at the U.S. close cutoff is not available in this run.
- A natural manuscript framing is point-in-time U.S. close information for OSE pre-open tail-risk forecasting, with futures opening-risk management and forecast-evaluation discipline as supporting angles.
- Plausible outlets depend on emphasis: Journal of Futures Markets for futures-market risk, International Journal of Forecasting or Journal of Forecasting for forecast evaluation, Pacific-Basin Finance Journal for Japan and Asia-Pacific market information, and The Journal of Risk for VaR/ES validation.
- The current bottom line is that the pipeline produces research-candidate evidence from the durable gold layer; {advanced_bottom_line_bullet}
"""
