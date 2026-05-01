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
- This is defensible for forecasting the active large-contract Nikkei 225 futures tail-risk surface. It does not claim that maturity-specific basis, liquidity, or time-to-expiry effects are fully modeled.

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

### How should broad readers interpret the metrics?

Coverage diagnostics ask whether VaR exceptions are too frequent or too rare; quantile loss scores VaR accuracy; FZ loss scores VaR-ES pairs.

- Lower quantile loss is better only within a common sample and claim boundary.
- FZ loss is only meaningful for valid VaR-ES pairs and needs enough exceptions to avoid short-sample overinterpretation.
- Restricted result-matrix rows are useful diagnostics, not replacements for the headline information-set ladder.

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
