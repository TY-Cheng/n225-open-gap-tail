---
hide:
  - navigation
---

# Future Work

This page records extensions that should remain outside the current paper unless they
become necessary for interpretation. The present paper is a point-in-time out-of-sample
forecast evaluation of OSE Nikkei 225 Futures opening-gap VaR and Expected Shortfall. It
already covers benchmark models, ML tail models, left-tail and right-tail risk surfaces,
coverage diagnostics, loss-based comparison, CPA regressions, Murphy diagrams, DST
diagnostics, ES severity, and risk-trigger summaries.

Future work should therefore do one of two things: either sharpen the economic
interpretation of the current evidence, or define a clearly separate paper.

## Extension Summary

Extension | Research question | When to pursue
--- | --- | ---
Intraday U.S.-close Nikkei reference mark | Does U.S. close information predict the opening-auction residual after conditioning on a Nikkei futures price observed at the U.S. cash close? | After licensed OSE, CME, SGX, or equivalent intraday Nikkei futures marks are available with reliable timestamps.
EVT and high-quantile evaluation | Does the LightGBM POT-GPD layer improve VaR-ES performance beyond direct LightGBM quantile forecasts, especially at more extreme quantiles? | After the 95% common-sample comparison is stable, and before any 97.5% claim is made.
Richer option-implied tail-risk predictors | Do option-implied measures beyond VIX close add incremental information for opening-gap tail risk? | After the core U.S. close information sets are settled and richer option data can be timestamped.
Night-session microstructure and absorption | How much U.S. information is incorporated during the OSE night session, and what remains for the day-session open? | After night-session OHLC or intraday OSE data are available with session-level timestamps.
Real-time pre-open risk monitoring | Can the historical forecast design be converted into a live pre-open risk-monitoring process? | Only after live feeds, vendor availability, failure handling, and alert logs are specified.
Submission reproducibility package | Can every table and figure be reproduced from documented commands and source manifests? | Before manuscript circulation.

## 1. Intraday U.S.-Close Nikkei Reference Mark

### Question

Does U.S. close information predict residual OSE day-session opening risk after
conditioning on a Nikkei futures price observed at the U.S. cash close?

### Data Requirements

- OSE intraday Nikkei 225 Futures prices, or a licensed equivalent.
- CME or SGX Nikkei futures marks if they provide a reliable U.S.-close reference.
- Source-specific timestamps and data-availability records.

### Guardrails

- Do not synthesize a U.S.-close Nikkei mark from daily data.
- Do not use a mark observed after the forecast origin.
- Keep the U.S.-close-mark target unavailable until a licensed intraday source exists.
- Keep full settlement-to-open risk separate from U.S.-close-mark-to-open residual risk.

## 2. EVT and High-Quantile Evaluation

### Question

Does the LightGBM standardized-loss POT-GPD layer improve VaR-ES performance relative to
direct LightGBM quantile forecasts?

### First Comparison

- Compare 95% direct LightGBM quantile forecasts against 95% LightGBM POT-GPD forecasts.
- Use common out-of-sample dates.
- Evaluate VaR coverage, quantile loss, FZ joint VaR-ES loss, ES exceedance severity, and
  exception counts together.

### Conditions for 97.5% Results

97.5% VaR/ES results should be promoted only if the evidence supports them:

- sufficient common-sample observations;
- sufficient out-of-sample exceptions;
- stable GPD shape and scale estimates;
- threshold-sensitivity checks;
- interpretable ES severity diagnostics;
- clear separation between left-tail and right-tail results.

Computing a 97.5% forecast is not, by itself, enough to make a 97.5% empirical claim.

## 3. Richer Option-Implied Tail-Risk Predictors

### Question

Do option-implied measures beyond the VIX close add information about OSE opening-gap tail
risk beyond ETFs, rates, FX, and the existing volatility-index controls?

### Candidate Predictors

- VVIX.
- SKEW or related option-implied tail measures.
- VIX futures term structure.
- SPX option-implied tail or variance-risk-premium measures, subject to data access.

### Guardrails

- Record the observation timestamp and the practical availability time for each predictor.
- Treat delayed historical series as historical predictors, not live pre-open data.
- Test incremental value through pre-specified information-set additions or ablations.
- Do not rely on feature-importance narratives without out-of-sample loss and coverage
  evidence.

## 4. Night-Session Microstructure and Absorption

### Question

How much of the U.S. close signal is incorporated during the OSE night session, and what
part remains for the next day-session open?

### Candidate Measures

- Night-session return.
- Night-session range.
- Last-hour night-session movement.
- Night-session volume and liquidity measures.
- Opening-auction residual gap after conditioning on the night-session close.

### Guardrails

- Do not interpret full settlement-to-open predictability as opening-auction residual
  predictability.
- Keep settlement-to-open, close-to-open, night-close-to-open, and U.S.-close-mark-to-open
  targets in separate tables.
- Report holiday, roll-window, SQ-window, and early-close sensitivity.

## 5. Real-Time Pre-Open Risk Monitoring

### Question

Can the historical forecast design be converted into a live pre-open risk-monitoring
process?

### Required Additions

- Live or near-live U.S. close predictors.
- A live OSE, CME, SGX, or broker feed for Nikkei futures reference prices.
- Vendor-availability timestamps and missing-data rules.
- Alert logs, failure handling, and monitoring procedures.

### Guardrails

- Do not describe the historical backtest as production-ready.
- Do not rely on J-Quants daily futures OHLC as a live pre-open feed.
- Keep risk alerts separate from execution, transaction-cost, and trading-alpha claims.

## 6. Submission Reproducibility Package

Before manuscript circulation, prepare a reproducibility package with:

- data-source manifest and access notes;
- source as-of dates and hashes where permitted;
- schema reports for raw, interim, and processed tables;
- target audit report;
- point-in-time feature checklist;
- model configuration files;
- table and figure reproduction commands;
- smoke fixtures for reviewers without vendor data.

Submission criterion: every manuscript table and figure should map to one documented
command and one output path.
