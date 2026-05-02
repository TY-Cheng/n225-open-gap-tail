# ruff: noqa: E501
from __future__ import annotations


def discussion_qa_markdown(
    *,
    advanced_implementation_text: str,
    advanced_implementation_bullet: str,
    advanced_bottom_line_bullet: str,
    claim_scope_table: str,
) -> str:
    return f"""## Discussion Q&A

### What is this project testing?

It tests whether timestamp-safe information available by the U.S. close cutoff helps forecast left-tail and right-tail risk for the next Osaka Nikkei 225 Futures day-session open.

- The object is tail risk, not average return prediction or an execution rule.
- The comparison is organized as an information ladder: Japan-only history first, then U.S. close core, then Japan proxy ETFs, then Asia proxy ETFs.
- The current page reports what the pipeline produced; it does not automatically make a model-selection claim.

### What exactly is being forecast?

The primary target is the loss version of the settle-to-open Nikkei futures gap for the OSE day-session open.

- Left and right tails are transformed into positive loss units and evaluated separately.
- Roll/SQ windows and invalid reference prices are excluded from clean target evidence.
- The residual U.S.-close mark target is disabled in this run because there is no licensed timestamped intraday Nikkei mark.

### Which Nikkei 225 Futures contract is used when many expiries trade?

The target source is the OSE Nikkei 225 Futures large contract, not mini or micro contracts.

- The J-Quants futures rows are first filtered to rows marked as the central contract month.
- The target audit then requires the day-session open and the previous reference settlement or close to come from the same contract where possible.
- Observations are removed from the clean target evidence when they cross a contract roll, last-trading-day boundary, SQ window, invalid reference price, or missing target field.
- Rule-based quarterly contract metadata exists for audit and diagnostics, but the empirical target is governed by audited J-Quants central-contract flags and same-contract target construction.

### Can returns from different expiries be pooled in one model?

Pooling is done at the observation level, not by stitching raw prices into a naive continuous futures price.

- The target audit first keeps the J-Quants row marked as the central contract month for each trading date.
- It then builds a history by `contract_code` and, for each central-contract row, searches backward inside the same `contract_code` to find the prior reference row.
- The settle-to-open gap is `log(current day-session open) - log(prior settlement)` from that same contract. The close-to-open gap is computed the same way with the same contract's prior day-session close.
- The audit carries `reference_contract_code`, `same_contract_only`, roll/SQ flags, and missing reasons so cross-contract references are visible rather than silently treated as returns.
- A row enters the clean target sample only when the reference is same-contract, the row is outside the roll/SQ window, and required prices are present.
- The model pool is then the time-ordered set of these clean gap observations across successive central quarterly contracts. Benchmarks and ML models fit one active-contract risk process on that pooled clean sample; ML lag and rolling-history features are updated only from clean rows.
- The current headline `Y` is the settle-to-open target: `gap_t = full_gap_settle_to_open`. For left-tail models the positive loss is `-gap_t`; for right-tail models it is `gap_t`. `full_gap_close_to_open` is carried in the panel for audit and alternative diagnostics, but it is not the current headline target family.
- For benchmark models, `X` is target history only: past clean losses/gaps enter empirical quantile, EWMA, GARCH, GJR-GARCH, EVT-style, CAViaR, CARE, GAS, and related benchmark forecasts.
- For ML-tail models, `X` is a nested information ladder. `japan_only` uses lagged clean losses/gaps, rolling loss moments, calendar month terms, DST, and absorption-regime indicators. The next steps add U.S. close core ETF/sector/rates/volatility/FX/late-SPY features, then Japan proxy ETF features, then Asia proxy ETF features.
- `contract_code`, `contract_month`, and roll/SQ flags are retained as audit fields; they are not treated as ordinary ML predictors in the headline ladder.
- This is defensible for forecasting the active large-contract Nikkei 225 futures tail-risk surface. It does not claim that maturity-specific basis, liquidity, or time-to-expiry effects are fully modeled.

### Why carry both settle-to-open and close-to-open gaps?

They are two economically different reference-price definitions, not two targets created to patch missing data.

- `settle-to-open` uses the exchange settlement price as the prior reference. This is the current headline target because settlement is the official futures mark most naturally connected to clearing, margin, and risk-management accounting.
- `close-to-open` uses the prior day-session close as the prior reference. It is more intuitive as a last-traded day-session close-to-next-open return, but it is not the current headline target family.
- The project carries both so the target choice is auditable and so an alternative target can be evaluated without rebuilding the raw futures layer.
- For a pure "information after the U.S. close to OSE open" target, the ideal reference would be a licensed timestamped Nikkei futures mark at the U.S. close cutoff. That target is disabled in this run, so the headline target is explicitly a full settle-to-open opening-gap target.

### Is pre-open tail risk economically meaningful?

Yes, but the claim should be framed as a risk-management channel rather than as evidence that this sample contains observed forced liquidations.

- JPX describes Nikkei 225 Futures as margin-based leveraged contracts and warns that leverage affects losses as well as profits; under market stress, additional cash margin can be needed and losses can exceed the deposited margin ([JPX Nikkei 225 Futures overview](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/)).
- JPX's margin overview gives the general mechanism: adverse futures and options price movements can create significant losses, and margin is posted to ensure payments when losses occur ([JPX margin overview](https://www.jpx.co.jp/english/derivatives/rules/margin/)).
- JSCC's futures/options margin rules make the channel operational: listed derivatives are margined through JSCC, customer positions require margin, and intraday/emergency margin calls can apply; the emergency margin-call list explicitly includes Nikkei 225 Futures ([JSCC Margin on Futures and Options](https://www.jpx.co.jp/jscc/en/cash/futures/marginsystem/margin.html)).
- JSCC also has margin add-ons for liquidity and concentration risk, including the index-futures group containing Nikkei 225 Futures, which supports the interpretation that tail moves matter through both price risk and market-depth/position-size channels ([JSCC Margin Add-on Rules](https://www.jpx.co.jp/jscc/en/cash/futures/marginsystem/addonim.html)).
- The useful paper insight is therefore not "we observe forced liquidation." It is that pre-open tail forecasts proxy a real risk-management problem: leveraged futures positions can face margin, liquidity, and risk-limit pressure when the opening price jumps before normal day-session liquidity is available.
- Historical cases such as Barings show that Nikkei futures losses and margin/funding pressure can become institutionally material, but they are channel motivation rather than direct sample evidence. Use official/regulatory sources for the collapse record and academic market-stress context ([GOV.UK Barings inquiry report](https://www.gov.uk/government/publications/report-into-the-collapse-of-barings-bank); [Steenbeek 1999, Bank of Japan edited volume metadata](https://pure.eur.nl/en/publications/price-discovery-during-periods-of-stress-barings-the-kobe-quake-a/)).

### Is it fair that benchmarks use less information than ML models?

It is fair only if the comparison is framed correctly.

- Benchmark models are target-history-only floors: the benchmark shards read only forecast dates, clean realized losses, and the underlying gap needed to define left- versus right-tail losses.
- "Target history only" does not mean a naive one-lag regression. Historical and rolling quantiles use empirical target distributions, EWMA and GARCH-style models estimate volatility dynamics, and CAViaR/CARE/GAS-style benchmarks impose their own tail-dynamic structure.
- ML Model A (`japan_only`) is feature engineering on the same target-history source: lagged clean losses/gaps, rolling mean/volatility/tail summaries, calendar month terms, DST, and absorption-regime indicators. It does not use U.S. close predictor blocks.
- This makes Model A broadly comparable as a no-U.S.-information ML baseline, but not a perfectly identical-feature comparison. ML A exposes target-history summaries as tabular predictors; econometric benchmarks encode target-history dynamics through model structure.
- The Model B/C/D ladder is not a pure algorithm horse race against the benchmarks. It is an incremental-information experiment: after the Japan/history baseline, do U.S. close core, Japan proxy, and Asia proxy features add forecast value?
- Therefore the paper should avoid saying "LightGBM beats econometric benchmarks" as a standalone learner claim. The safer claim is that the nested ML-tail ladder tests whether timestamp-safe U.S. close information improves tail-risk forecasts beyond target-history baselines.

### Are benchmark forecasts dynamic, or are their daily tail quantiles fixed?

They are not fixed full-sample quantile lines. Each benchmark forecast is generated as a dated out-of-sample forecast using information available before that forecast date.

- In the broad time-varying-forecast sense, all benchmark models are dynamic: the floor benchmark loop uses only clean target history up to `t-1` when producing the forecast for date `t`.
- Historical and rolling quantiles therefore update as the eligible history changes, although they can move in step-like fashion because empirical tail order statistics often remain unchanged for several adjacent dates.
- EWMA, GARCH-t, GJR-GARCH-t, and GJR-GARCH-EVT produce daily forecasts through volatility or tail-scaling estimates based on the training history.
- In the stricter stateful-model sense, not all benchmarks are dynamic recursion models. CAViaR, CARE, GAS, and Taylor/FZ-style variants are the stateful dynamic benchmark layer: they refit parameters on the registered refit calendar and update the latent VaR/scale state through valid panel dates.
- The current benchmark artifacts should therefore be read as daily out-of-sample VaR/ES forecasts, not as a single in-sample high quantile reused across the whole evaluation window.

### Are the four ML information layers engineered in the same way?

Mostly yes. The layers differ by which source blocks are admitted, not by giving later layers a special feature-engineering recipe.

- Every ML layer includes the same target-history features: lagged clean losses/gaps, rolling means, rolling volatility, rolling tail quantile, calendar month, DST, and absorption-regime indicators.
- Daily ETF and asset-market blocks use the same simple transformations: close-to-close log returns and log high-low ranges, frozen at the audited U.S. close cutoff.
- FRED/Cboe/rates/volatility blocks use levels, first differences, staleness/release-lag diagnostics, and Cboe VIX range where available.
- USDJPY uses timestamp-safe level and return features from the canonical FX source.
- The SPY minute block is the main intraday-engineered block: late 30-minute and 60-minute returns, late-session range, final-window momentum, and late-volume surge.
- The nested difference is source access: `japan_only` has target-history/calendar features; the U.S. core layer adds U.S. ETF/sector/rates/volatility/FX/late-SPY features; Japan proxy adds EWJ/DXJ return/range; Asia proxy adds EWY/EWT/EWH return/range.

### Is the feature engineering strong enough relative to nearby literature?

It is defensible for a timestamp-safe first headline design, but it is not the richest possible tail-risk feature set.

- The current design is aligned with the literature's basic structure: target-history/HAR-like summaries, market returns/ranges, macro-financial predictors, and cross-market spillover variables. Recent realized-volatility ML evidence also warns that extra predictors can help daily/weekly forecasts, but nonlinear ML does not systematically dominate simpler models, so the current conservative ladder is appropriate ([Branco, Rubesam, and Zevallos 2024](https://www.sciencedirect.com/science/article/abs/pii/S0927539824000598)).
- The cross-market motivation is also standard: U.S. and Japanese index futures studies find economically important U.S.-to-Japan return and volatility spillovers, which supports the U.S. close information ladder ([Pan and Hsueh 1998](https://ideas.repec.org/a/kap/apfinm/v5y1998i3p211-225.html)).
- Overnight and intraday decomposition is relevant to the question: ETF/futures evidence treats overnight and daytime returns as different risk objects and evaluates VaR/ES or tail risk separately ([Liu and Tse 2017](https://www.sciencedirect.com/science/article/pii/S1059056016301563)).
- The main gap versus tail-risk frontier papers is high-frequency realized information. Realized-measure VaR/ES models often use realized variance, realized range, and related intraday measures to drive tail dynamics; recent work even adds realized skewness and kurtosis ([Gerlach and Wang 2020](https://www.sciencedirect.com/science/article/pii/S0169207019301992); [Chen, Hsu, and Watanabe 2023](https://www.sciencedirect.com/science/article/pii/S1544612322005050); [Dynamic tail risk forecasting with realized skewness and kurtosis, 2024](https://arxiv.org/abs/2409.13516)).
- The most relevant next additions are therefore not more generic U.S. ETFs. They are timestamp-safe Nikkei/OSE-specific realized features: intraday realized volatility, realized range, downside/upside semivariance, realized skewness/kurtosis, jump/range indicators, night-session partial measures if available before the cutoff, Nikkei implied-volatility/options measures, and liquidity or depth variables such as volume, open interest changes, spreads, and days-to-expiry controls.
- These additions should enter an enriched or robustness information set first, not the current headline ladder. The clean sample has only about 1.6k forecast rows, so adding many high-dimensional predictors without stronger gates would raise overfitting and data-snooping concerns.

### Why is timing the central issue?

The forecast origin is the U.S. close plus vendor lag, and it must occur before the OSE target open. "U.S. close information" means information available by this cutoff; it does not mean all U.S. after-close or overnight news.

- Every joined predictor is audited against `feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc`.
- FRED features are treated with timestamp-safe release lags; FRED historical values are not ALFRED vintage-safe.
- Leakage audit failures are zero in this run, but warnings remain visible below rather than hidden.

### Why does the clean sample start in 2018?

The requested data window begins earlier, but the clean forecast sample starts only when all required target and predictor blocks satisfy the registered coverage and timing gates.

- Earlier rows remain useful for target-history audit, raw-cache checks, and training history, but they are not forecast evidence under the current clean-sample contract.
- The clean start is driven by combined J-Quants required-field coverage, Massive daily entitlement coverage, required FRED coverage, and canonical FX timing coverage.
- Post-2018 rows satisfy the current clean-sample gates for the required headline blocks; isolated feature-level gaps are still audited, and enriched or optional blocks can have shorter histories unless promoted by a future specification.

### What has been implemented?

{advanced_implementation_text}

- Benchmark floor models include target-history baselines and GARCH/EVT-style econometric floors.
- {advanced_implementation_bullet}
- ML-tail models include direct LightGBM quantile, location-scale LightGBM, and standardized-loss POT-GPD.
- The headline ML-tail table remains strict: it currently keeps direct quantile rows because the newer tail-model variants have shorter common coverage.

### Why call CAViaR, CARE, GAS, and FZ-style models "advanced" if they are benchmarks?

They are benchmarks. "Advanced" is an internal tier label, not a claim that they are the paper's primary model family.

- The benchmark suite has two target-history-only tiers: floor benchmarks and advanced econometric benchmarks.
- Floor benchmarks are simple, robust reference points such as historical quantile, rolling quantile, EWMA, GARCH-t, GJR-GARCH-t, and GJR-GARCH-EVT.
- Advanced benchmarks are still target-history-only, but they are more specialized tail-risk models: CAViaR recursively models VaR, CARE uses expectile-based tail dynamics, GAS updates a parametric state by score dynamics, and Taylor/FZ-style variants optimize VaR-ES-oriented losses.
- The reason to separate them is practical and interpretive: these models have heavier optimization, recursive state updates, calibration choices, and shorter or more fragile valid-sample gates.
- A referee will usually view all of them as benchmark/econometric comparators rather than as a separate contribution. The paper should therefore call them "advanced econometric benchmarks" or "extended benchmark suite," not present them as a third headline model class competing with the information-set ladder.

### Why use LightGBM as the ML learner?

LightGBM is used as a fixed, tabular, nonlinear learner for the nested information-set experiment, not as an algorithmic novelty claim.

- It handles mixed market predictors, nonlinearities, and interactions without turning the paper into a broad model tournament.
- Hyperparameters are held fixed across information sets and refit dates to limit data-dependent tuning.
- The econometric benchmark suite remains the main non-ML comparison layer; LightGBM is the ML information-extraction layer.

### Why are POT-GPD and location-scale not in the headline ML table?

They are implemented, but they do not replace the headline direct-quantile ladder.

- The headline ladder uses the strict shared information-set sample and currently retains direct LightGBM quantile rows.
- Location-scale and standardized-loss POT-GPD rows are restricted or diagnostic evidence when their common-sample and tail-event gates are shorter.
- EVT should therefore be described as a tail-calibration and robustness layer in this run, not as the central headline empirical result.

### What performance metrics are used, and how should they be read?

The main metric tables report a tail-risk forecast evaluation panel, not a single leaderboard.

- The core headline columns are `rows`, `var_breach_rate`, `expected_breach_rate`, `exceedance_count`, `kupiec_pvalue`, `christoffersen_pvalue`, `mean_quantile_loss`, `mean_fz_loss`, and `mean_exceedance_severity`.
- `rows` is the number of valid out-of-sample forecasts. `var_breach_rate` is the fraction of realized losses exceeding the VaR forecast, and `expected_breach_rate` is the nominal rate implied by the tail level. At `tail_level = 0.95`, the nominal breach rate is 5%.
- `exceedance_count` records the number of VaR exceptions. `kupiec_pvalue` tests unconditional VaR coverage, while `christoffersen_pvalue` tests whether exceptions show serial dependence.
- `mean_quantile_loss` is the VaR pinball loss. `mean_fz_loss` is the joint VaR-ES Fissler-Ziegel score for valid VaR-ES forecast pairs. `mean_exceedance_severity` measures how far realized losses exceed VaR conditional on an exception.
- These columns are present in both `benchmark_metrics.parquet` and `ml_tail_metrics.parquet`, so benchmark and ML-tail rows can be read through the same metric vocabulary.

### What dimensions do the performance metrics cover?

The evaluation design separates four dimensions.

- Calibration and coverage: breach rates, expected breach rates, Kupiec tests, and Christoffersen tests ask whether VaR exceptions are too frequent, too rare, or clustered.
- Scoring accuracy: quantile loss evaluates VaR forecasts, and FZ loss evaluates joint VaR-ES forecast pairs. These scoring losses matter because a model can have a near-nominal breach rate while setting VaR too conservatively.
- Tail severity: exceedance counts and mean exceedance severity describe how often the forecast fails and how large the misses are, which is economically relevant for margin, liquidity, and risk-limit interpretation.
- Statistical comparison: block-bootstrap DM records, HLN/Tmax MCS records, restricted result-matrix rows, CPA conditional loss-difference diagnostics, Murphy elementary-score diagnostics, stress-window diagnostics, and DST attenuation diagnostics keep model comparisons from resting on raw average losses alone.

### Are these metrics comprehensive and standard enough for this research?

For the current research question, the metric set is comprehensive enough and is organized conservatively.

- The project does not rely only on breach rates or only on scoring losses. It checks VaR coverage, exception independence, VaR loss, joint VaR-ES loss, exception severity, common-sample fairness, loss-difference inference, information-set increments, and stress/DST diagnostics.
- The classic components are standard in VaR and forecast-evaluation work: Kupiec unconditional coverage, Christoffersen independence, quantile loss, Diebold-Mariano-style forecast comparison, and Model Confidence Set.
- The more modern tail-risk components are also appropriate for current VaR/ES work: Fissler-Ziegel joint VaR-ES scoring, Murphy-style elementary-score diagnostics, CPA conditional predictive ability diagnostics, common-sample/model-eviction gates, and restricted result matrices for avoiding sample-mismatch comparisons.
- The design is therefore not just a legacy backtest, and it is not an unconstrained collection of diagnostics. The headline layer stays conservative, while the diagnostic layer records how robust the interpretation is.
- The current reading discipline is to inspect `breach_rate`, `Kupiec`, `Christoffersen`, `quantile_loss`, `FZ_loss`, `exception_count`, common-sample status, and inference status together. In this run, benchmark floor rows have breach rates closer to the nominal 5% level, while some ML-tail information sets have lower loss scores; that pattern should be interpreted as a coverage-versus-scoring tradeoff, not as a standalone statement that the lower-loss model is better calibrated.
- Restricted result-matrix rows and downstream diagnostics are useful evidence, but they do not replace the headline information-set ladder unless they pass the registered sample and claim gates.

### Why can benchmarks have better breach rates while ML has lower loss?

This pattern is supported by the current artifacts as a cautious interpretation, not as a model-selection claim.

- Benchmark floor breach rates are closer to the nominal 5% VaR level, so they are better calibrated on coverage.
- Some LightGBM information sets have lower quantile or FZ loss because their VaR levels are less conservative on average.
- Lower loss can therefore partly reflect a sharper or more aggressive VaR forecast, which is why coverage, loss, exception counts, and inference gates must be read together.

### Where does LightGBM help relative to benchmarks?

The current evidence supports a candidate information-extraction role, especially in the left-tail ladder after adding U.S. close core variables.

- It does not support a blanket statement that LightGBM is better calibrated than the benchmark floor.
- The reported tables evaluate average loss and breach behavior, not median conditional forecast quality.
- A median-effect claim would need an explicit median loss or paired distribution diagnostic; it is not a current headline result.

### What differs between left-tail and right-tail results?

The two risk surfaces are intentionally separated.

- Left-tail quantile loss changes most when U.S. close core variables are first added to Japan-only history.
- Right-tail changes are smaller at the U.S. core step and appear more dependent on later proxy blocks in the current ladder.
- The paper should therefore avoid treating upside and downside opening-gap risk as one symmetric mechanism.

### Which U.S. close core variables may be contributing?

The core block aggregates U.S. equity, sector, volatility, FX, rates, credit-risk, and late-session SPY features available by the cutoff.

- Plausible contributors include broad index ETFs, sector dispersion, VIX/Cboe volatility measures, Treasury-rate changes, USD/JPY controls, credit-risk proxies, and SPY late-session pressure.
- The current tables support block-level interpretation more than feature-level attribution.
- Any feature-level story should be presented as descriptive diagnostics unless supported by a dedicated attribution design.

### Do Japan proxy or Asia proxy ETFs add more?

In the current headline ladder, the largest change generally appears when U.S. close core variables are added.

- After U.S. close core, Japan proxy ETFs add more visible marginal loss reduction than the Asia proxy block.
- The Asia proxy block adds little incremental improvement in the current headline quantile-loss ladder and can slightly worsen the left-tail row.
- These proxy-block patterns are descriptive and should not be written as structural regional price-discovery claims.

### Which journals look like plausible homes for a paper from this project?

The strongest fit depends on whether the paper is framed as a futures-market paper, a forecasting paper, or an Asia-Pacific market-information paper.

- **Journal of Futures Markets** is the most natural finance-market outlet because the object is an exchange-traded futures contract and the evidence concerns tail-risk forecasting, market information, and risk-management interpretation. Recent Journal of Futures Markets contents include futures volatility forecasting, downside risk, option-implied risk, tail-risk spillovers, and machine-learning/interpretable-model work ([Journal page](https://onlinelibrary.wiley.com/journal/10969934); [recent RePEc contents](https://ideas.repec.org/s/wly/jfutmk.html)).
- **International Journal of Forecasting** is a higher-stretch but credible fit if the contribution is written as a timestamp-safe forecasting design. Its scope explicitly includes financial forecasting, forecast evaluation, implementation, forecast uncertainty, machine-learning forecasting, and reproducible online supplements ([IJF aims and scope](https://www.sciencedirect.com/journal/international-journal-of-forecasting)).
- **Pacific-Basin Finance Journal** is a strong fit if the manuscript emphasizes Japan/OSE, Asia-Pacific capital markets, and useful empirical finance. Its scope focuses on reliable empirical research on Asia-Pacific capital markets and useful research for real financial-market decision problems ([PBFJ aims and scope](https://www.sciencedirect.com/journal/pacific-basin-finance-journal)); it has also published Nikkei futures volatility work ([Bacha and Vila 1994](https://www.sciencedirect.com/science/article/pii/0927538X94900175)).
- **Journal of Forecasting** is a reasonable fallback for a benchmark-rich financial forecasting article, especially if the evaluation framework and forecast comparison are foregrounded ([Journal page](https://onlinelibrary.wiley.com/journal/1099131x); [recent RePEc contents](https://ideas.repec.org/s/wly/jforec.html)).
- **The Journal of Risk** is a conditional fit if the manuscript is recast around VaR/ES risk measurement and model validation. Its scope targets financial risk measurement, management, volatility/jumps, risk measures, and AI/ML in financial risk management ([Journal of Risk scope](https://www.risk.net/journal-of-risk)).
- **Quantitative Finance** is possible but more demanding: its scope includes financial econometrics, market dynamics and prediction, derivatives, microstructure, liquidity, and operational risk, but it will likely expect stronger quantitative or methodological novelty than a single-market information-ladder application ([Quantitative Finance aims and scope](https://www.tandfonline.com/journals/rquf20/about-this-journal)).
- **Finance Research Letters** is better as a compressed short-paper venue. It lists forecasting, financial econometrics, financial markets, microstructure, and risk among finance areas, but the full benchmark/diagnostic design is probably too large for a letter-length paper ([FRL aims and scope](https://www.sciencedirect.com/journal/finance-research-letters)).

### What manuscript story versions are feasible?

The safest stories keep the claim inside the evidence gates.

- **Story A: timestamp-safe U.S. close information for OSE pre-open tail risk.** This is the main recommendation. The contribution is the information ladder: Japan-only history, U.S. close core, Japan proxy, and Asia proxy blocks under strict timing and leakage audits. Likely outlets are Journal of Futures Markets, Pacific-Basin Finance Journal, and International Journal of Forecasting.
- **Story B: futures opening-risk management.** The paper frames settle-to-open VaR/ES as a margin, liquidity, and risk-limit problem for leveraged Nikkei futures. The empirical punchline is not that ML is perfectly calibrated, but that richer timestamp-safe information can sharpen loss forecasts under a clear coverage caveat. Likely outlets are Journal of Futures Markets, The Journal of Risk, and Pacific-Basin Finance Journal.
- **Story C: forecast-evaluation discipline for financial tail risk.** The paper emphasizes common samples, benchmark floors, FZ scoring, DM/MCS, CPA, Murphy diagnostics, and claim gates. This is most suitable for International Journal of Forecasting or Journal of Forecasting if the paper is written as a reusable evaluation design rather than a narrow Nikkei case study.
- **Story D: left/right asymmetry and partial overnight absorption.** This is a secondary story. It stresses that "U.S. close information" means information available by the cutoff, not all overnight news, and that left and right opening-tail surfaces should be evaluated separately. This story is useful in the introduction and discussion, but probably should not be the only headline claim.
- Across all versions, avoid claims that LightGBM unconditionally beats econometric benchmarks, that proxy ETFs prove regional price discovery, that the study observes forced liquidation, or that the disabled U.S.-close residual target has been estimated.

### What is the main referee risk in the current evidence?

The most likely challenge is not whether the pipeline ran, but whether the claims are kept inside the evidence gates.

- ML headline breach rates are too high relative to the nominal VaR level, even where loss metrics improve.
- EVT and location-scale models are implemented but not headline-retained.
- "U.S. close information" must be defined as information available by the cutoff, not all after-close news.
- FRED is conservatively lagged but not ALFRED vintage-safe, and feature-level explanations remain descriptive.
- Final manuscript claims require a clean committed run and author review of tables, sample gates, and inference diagnostics.

### What is the current bottom line?

The pipeline is now producing full-run research-candidate evidence from the durable gold layer.

- The gold sample starts at the dynamic combined clean start, not the 2016 cache lower bound.
- {advanced_bottom_line_bullet}
- Before manuscript claims, review the headline/restricted/diagnostic boundaries, inference gates, and vintage limitations rather than selecting a model from one metric.

### Which results can support headline claims?

{claim_scope_table}

- Headline claims require a clean committed run, a shared common sample, zero leakage failures, and author-reviewed tables.
- Restricted rows can explain model-family behavior on matched dates, but they cannot replace the headline information ladder.
- Diagnostic rows can motivate discussion and future checks; they should not be worded as model-selection or risk-management usefulness claims without their own evidence gates.
"""
