---
hide:
  - navigation
---

# Results Snapshot

Static snapshot as of 2026-04-26.

This page records the current local data-engineering state. It is not an empirical results page: the OSE Nikkei 225 Futures target data is not yet available under the current J-Quants free plan, so no model performance claim is active.

## Run Metadata

Field | Value
--- | ---
Workflow front door | `just`
Python environment | external `UV_PROJECT_ENVIRONMENT`
Latest quality gate | `just test`, `just docs-build`
Test status | 29 passed
Coverage | 96.68%
Docs build | strict MkDocs build passed

## Interpretation Summary

The repository is ready for target-data ingestion once a futures-capable J-Quants subscription is available. U.S. predictor ingestion, FRED risk proxies, calendar alignment, and rule-based contract scaffolding are implemented and tested. The research pipeline has not yet reached target construction, feature-table construction, baseline modeling, LightGBM, EVT, or VaR-ES evaluation.

## Data Engineering Snapshot

Source | Current command | Current local result | Status
--- | --- | --- | ---
Massive.com | `n225-open-gap-tail massive-smoke` | 50 daily rows across 10 U.S. ETF/FX predictors; SPY minute sample has 921 rows, including 390 regular-session rows. | Implemented and smoke-tested.
FRED | `n225-open-gap-tail fred-smoke` | 15 rows for `VIXCLS`, `DGS2`, and `DGS10` over the smoke window. | Implemented and smoke-tested.
Calendars | `n225-open-gap-tail calendar-build` | 31 January 2026 calendar rows; 20 U.S. trading days and 19 JPX trading days. | Implemented as alignment scaffold.
Contract metadata | `n225-open-gap-tail contracts-build` | 9 rule-based quarterly contracts; 242 central-contract selector rows; 20 roll-window rows. | Implemented as rule-based scaffold.
J-Quants | `n225-open-gap-tail jquants-smoke` | Equity smoke works; futures endpoint remains unavailable on the free plan. | Target-data blocker.

## Artifact Index

Artifact family | Path pattern | Tracked?
--- | --- | ---
Massive raw smoke | `data/raw/massive/` | No
Massive normalized parquet | `data/interim/massive/` | No
FRED raw and parquet | `data/raw/fred/`, `data/interim/fred/` | No
Calendar tables | `data/raw/calendars/`, `data/interim/calendars/` | No
Contract metadata | `data/raw/contracts/`, `data/interim/contracts/` | No
Docs build | `site/` | No
Secrets and local environment | `.env`, `uv.lock` | No

## Current Blockers

1. **Futures target access.** The main target requires OSE Nikkei 225 Futures daily/session OHLC, settlement, volume, open interest, contract month, last trading day, and SQ fields. The current J-Quants free plan does not provide the futures endpoint.
2. **Vendor reconciliation.** Rule-based contract metadata is useful for implementation and tests, but final empirical work must reconcile it with J-Quants or JPX contract metadata.
3. **No model evidence yet.** Any statement about LightGBM-EVT performance, VaR/ES calibration, or hedge-trigger usefulness remains planned until the target and feature builders are complete.

## Next Evidence Gate

The next gate is the **target data audit**:

- confirm futures subscription access;
- download a bounded historical futures sample;
- build and audit `full_gap_settle_to_open`;
- trace extreme gaps back to raw futures rows;
- verify roll, SQ, holiday, and missing-session flags.
