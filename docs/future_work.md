---
hide:
  - navigation
---

# Deferred Extensions

This page records work that should remain outside the first paper until the target-data, feature, baseline, LightGBM, EVT, and evaluation gates are reproducible.

Scope guardrail: the first paper is a session-aligned historical risk-forecasting study. Extensions should be activated only when they sharpen that study or become a clearly separate paper.

## Extension Portfolio

Extension | Research contribution | When to activate
--- | --- | ---
Intraday U.S.-close Nikkei reference mark | Converts the ideal `residual_usclosemark_to_open` target from a documented extension into a main residual-risk target. | After licensed OSE, CME, SGX, or equivalent intraday Nikkei futures marks are available with timestamps.
Options-implied tail-risk proxies | Tests whether VIX, VVIX, SKEW, VIX term structure, or SPX option-implied tail measures add information beyond ETFs and rates. | After the daily target pipeline is stable and baseline predictor groups are working.
Night-session microstructure | Separates full overnight gap risk from opening-auction residual risk using night-session path, volume, and liquidity features. | After night-session OHLC and, ideally, intraday OSE data are licensed.
Richer econometric benchmark suite | Adds CAViaR variants, ALD VaR-ES, GAS/realized-measure models, and Model Confidence Set inference. | After historical, rolling, volatility-scaled, GARCH-EVT, and LightGBM-only baselines are reproducible.
Real-time pre-open monitoring | Turns the historical design into a live pre-open risk monitor. | Only after live data feeds, vendor availability timestamps, and operational alerting are specified.
Reproducibility package | Makes the project submission-ready with pinned source manifests and table/figure reproduction commands. | Before manuscript circulation.

## Extension 1: Intraday U.S.-Close Nikkei Reference Mark

### Research Question

Does U.S. close information predict residual OSE day-session opening risk after conditioning on a Nikkei futures mark observed at the U.S. cash close?

### Incremental Data

- OSE intraday Nikkei 225 Futures marks.
- CME yen-denominated or USD-denominated Nikkei futures marks.
- SGX Nikkei futures marks if available.
- Source-specific timestamp and availability fields.

### Guardrails

- Do not synthesize a U.S.-close Nikkei mark from daily data.
- Do not use a mark observed after the model cutoff.
- Keep this target unavailable until a licensed intraday source exists.

## Extension 2: Options-Implied Tail-Risk Layer

### Research Question

Do U.S. implied-volatility and option-implied tail-risk measures improve pre-open downside risk forecasts beyond equity ETFs, USD/JPY, and Treasury-rate proxies?

### Candidate Sources

- Cboe historical VIX and related index files.
- FRED `VIXCLS` for historical VIX close.
- Licensed Cboe DataShop or institutional option data for richer tail measures.
- VIX futures term structure if available.

### Acceptance Criteria

- Each implied-risk predictor has a timestamp and source role.
- Delayed historical series are labeled as historical predictors, not live data.
- Incremental information is tested through ablations, not feature-importance prose alone.

## Extension 3: Night-Session Microstructure

### Research Question

How much of the U.S. close signal is absorbed during the OSE night session, and what remains for the day-session opening auction?

### Candidate Features

- Night-session return.
- Night-session range.
- Volume and open-interest changes.
- Last-hour night-session movement.
- Opening-auction residual gap.

### Guardrails

- Do not interpret full opening-gap predictability as residual pre-open predictability.
- Keep full-gap and residual-gap tables separate.
- Report holiday, roll, and SQ-window sensitivity.

## Extension 4: Production Risk Monitor

### Research Question

Can the historical forecasting design be converted into a timestamp-safe pre-open alert system?

### Required Additions

- Live or near-live Massive/Cboe/FRED alternatives for U.S. close predictors.
- Live OSE, CME, SGX, or broker feed for Nikkei futures reference marks.
- Explicit vendor-availability timestamps.
- Alert logs, failure modes, and monitoring.

### Guardrails

- Do not call the historical backtest production-ready.
- Do not rely on J-Quants daily futures OHLC as a live pre-open feed.
- Separate risk alerts from execution or trading strategy claims.

## Extension 5: Reproducibility Package

Before manuscript circulation, build a reproducibility package with:

- data-source manifest and access notes;
- source as-of dates and hashes where permitted;
- schema reports for raw, interim, and processed tables;
- target audit report;
- feature leakage checklist;
- model configuration files;
- table and figure reproduction commands;
- smoke fixtures for reviewers without vendor data.

Submission criterion: every manuscript table and figure maps to one command and one artifact path.
