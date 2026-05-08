# ruff: noqa: E501
from __future__ import annotations


def advanced_benchmark_qa_text(advanced_forecast_rows: int) -> tuple[str, str, str]:
    if advanced_forecast_rows > 0:
        return (
            "The baseline benchmarks, advanced econometric benchmarks, and ML-tail suite are implemented and have completed artifacts in this run.",
            (
                "Advanced econometric benchmark families such as CAViaR, CARE/expectile, Taylor ALD, "
                "direct FZ-loss, and GAS produce nonblocking empirical forecast rows; "
                "their interpretation still follows the benchmark and restricted-sample gates."
            ),
            (
                "baseline benchmark, advanced econometric benchmark, and ML-tail suites completed with zero "
                "recorded forecast failures; advanced rows are implemented evidence but remain "
                "nonblocking until author-reviewed against the same sample and inference gates."
            ),
        )
    return (
        (
            "The baseline benchmarks and ML-tail suite are implemented and have completed artifacts in this run. "
            "The advanced econometric benchmark layer is registered as nonblocking, but this run has not produced empirical advanced-model forecast rows."
        ),
        (
            "Advanced econometric benchmark families such as CAViaR, CARE/expectile, Taylor ALD, "
            "direct FZ-loss, and GAS should be read as unavailable diagnostics when "
            "their optimizers produce no valid forecast rows."
        ),
        (
            "baseline benchmark and ML-tail suites both completed with zero recorded forecast "
            "failures; advanced econometric benchmark rows are nonblocking diagnostics in this run."
        ),
    )


def discussion_qa_markdown(
    *,
    advanced_implementation_text: str,
    advanced_implementation_bullet: str,
    advanced_bottom_line_bullet: str,
    claim_scope_table: str,
    opening_gap_scale_text: str,
) -> str:
    return f"""---
hide:
  - navigation
---

# Discussion Q&A

This page gives the plain-language framing behind the generated results snapshot. It is a guide to the empirical design and the current evidence, not a substitute for the tables, figures, and registered diagnostics.

## What is the paper asking?

The paper asks whether information known by the U.S. cash-market close helps forecast the next OSE Nikkei 225 Futures day-session opening tail.

- The contract is the OSE large Nikkei 225 Futures contract.
- The target is opening-gap risk at the next OSE day-session open.
- Left-tail and right-tail losses are reported separately. Both matter for futures positions, but they need not have the same economic pattern.
- The main comparison is across nested information sets: Japan-only history, U.S. close core variables, Japan proxy ETFs, and Asia proxy ETFs.
- The results are research-candidate evidence. They are not a model-selection statement by themselves.

## What is the target?

The primary target is the settlement-to-open gap:

`gap_t = log(OSE day-session open_t) - log(previous settlement_{{t-1}})`

- For left-tail models, loss is `-gap_t`.
- For right-tail models, loss is `gap_t`.
- A VaR exception occurs when `realized_loss > VaR forecast`.
- The primary risk level is 95% VaR/ES, so the nominal exception rate is 5%.
- Rows around roll and SQ windows are excluded from the clean primary sample.
- `full_gap_close_to_open` and `residual_nightclose_to_day_open` are kept for audit and diagnostic use, but they are not the primary target.
- A U.S.-close-mark-to-OSE-open residual target would need a licensed timestamped Nikkei futures mark at the U.S. close cutoff. That target is not active in this run.

## Why is the OSE open worth studying?

The open matters because it is the first OSE day-session mark after the U.S. close information set and after the Japanese night-session interval.

{opening_gap_scale_text}

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
- Benchmarks use target history only.
- The ML information sets add predictors in a fixed order: Japan-only, then U.S. close core, then Japan proxies, then Asia proxies.
- U.S.-listed options features are audit-gated. They are not primary evidence unless source, coverage, liquidity, and timing checks pass.

## What models are compared?

{advanced_implementation_text}

- Baseline benchmarks include historical quantiles, rolling quantiles, EWMA, GARCH-t, GJR-GARCH-t, and GJR-GARCH-EVT.
- {advanced_implementation_bullet}
- The ML suite includes direct LightGBM quantile forecasts, location-scale empirical calibration, standardized-loss POT-GPD variants, and the new research-candidate LightGBM+EVT routes.
- LightGBM is used as a fixed tabular learner. The paper does not claim a new machine-learning algorithm.
- Hyperparameters are held fixed across information sets and refit dates.
- Most models use expanding pre-forecast training histories. The rolling-quantile benchmark is the designed exception: it uses the most recent 1,000 clean observations.

## How do the LightGBM+EVT variants work?

The final VaR/ES level is 95%. POT-GPD variants use a 0.90 threshold only for
tail fitting; it is not the reported VaR level.

- Direct LightGBM estimates the 95% VaR level directly.
- Location-scale models estimate a conditional center and scale, then calibrate the upper tail of standardized losses.
- Standardized-loss POT-GPD models fit a Generalized Pareto tail above the registered 0.90 threshold of out-of-fold standardized losses.
- Median/MAD and median/IQR routes use more robust body filters before the POT-GPD step.
- Plain MLE is the standard EVT comparator. Robust body-filter routes remain research-candidate diagnostics until the evidence supports promotion.
- The current paper-facing promotion bridge is side-specific: median/IQR POT-GPD is the left-tail promoted ML-tail row, and location-scale empirical is the right-tail promoted ML-tail row. These rows are read with restricted DM/MCS evidence and do not create a universal model-family ranking.

## How are forecasts judged?

The evaluation is built around tail-risk performance, not a single ranking.

- Coverage: VaR breach rate should be close to the nominal 5% level.
- Exception count: coverage evidence is weak when the number of tail events is too small.
- Kupiec: tests unconditional VaR coverage.
- Christoffersen: tests exception clustering.
- Quantile loss: evaluates VaR forecasts.
- Fissler-Ziegel loss: evaluates joint VaR/ES forecasts where ES is valid.
- Mean exceedance severity: reports how large exceptions are once they happen.
- DM and MCS are average-sample inference across the unconditional evaluation sample.
- CPA is a conditional loss-difference diagnostic based on loss-differential regressions on ex-ante observables. It does not produce forecasts.
- Murphy diagrams, DST, stress-window, ES severity, and trigger diagnostics are supporting evidence.

## What do the current results say?

The current evidence is a calibration-versus-loss tradeoff.

- Baseline benchmarks generally sit closer to the 5% VaR exception target.
- Direct LightGBM quantile rows often show lower average loss on this registered sample, but their breach rates are above the nominal level.
- That means lower loss cannot be read alone as better tail calibration.
- Filtered EVT and location-scale models improve coverage discipline in several comparisons, but the evidence is not one model-family ranking.
- Among the new EVT candidates, median/IQR POT-GPD has the clearest left-tail calibration diagnostics in the current run. The right-tail promoted ML-tail row is location-scale empirical, while right-tail EVT evidence is less clean and should be reported separately.
- The paper should state the tension plainly: flexible ML information sets can change forecast loss, while VaR coverage gates determine whether that change is usable for risk claims.

## What can the paper claim?

{claim_scope_table}

- The paper can claim a point-in-time forecast evaluation of OSE Nikkei 225 Futures opening-gap tail risk.
- It can report that U.S. close information and proxy blocks change average loss and coverage patterns under registered information sets.
- It can report that direct LightGBM quantile forecasts are too liberal in the current primary ML rows.
- It can report side-specific promoted ML-tail rows after showing the promotion gate and restricted DM/MCS evidence: median/IQR POT-GPD for the left tail and location-scale empirical for the right tail.
- It should not claim that one model is universally strongest.
- It should not average left-tail and right-tail evidence into one mechanism.
- It should not present DST, trigger, or feature-block diagnostics as causal proof or realized trading performance.
- The current bottom line: the pipeline now produces a clean evidence set from the durable gold layer; {advanced_bottom_line_bullet}
"""
