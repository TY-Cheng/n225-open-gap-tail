# N225 Open Gap Tail Risk

Research code for **The Incremental Content of U.S. Close Information for Pre-Open Downside Tail Risk: Evidence from OSE Nikkei 225 Futures**.

The intended target is the next Osaka Exchange Nikkei 225 futures day-session opening gap, measured from the prior relevant OSE close or settlement to the next day-session open. The feature set should only use information observable before the Japan day-session open, with special attention to the U.S. cash close, U.S. futures marks, volatility indexes, USD/JPY, and cross-market ETF or sector signals.

## Setup

This repo uses `uv` and `just`. The local virtual environment is controlled by `.env`:

```bash
UV_PROJECT_ENVIRONMENT="${HOME}/.venvs/n225-open-gap-tail"
```

```bash
just status
just check
```

`just check` syncs the uv environment, formats and fixes `src` and `tests`, runs mypy and
pytest, and performs a strict docs build. Do not commit `.env`; put shareable defaults in
`.env.example`.

J-Quants should be configured through the V2 API key flow. The run futures
target pipeline requires local Premium futures access:

```bash
JQUANTS_API_VERSION="v2"
JQUANTS_API_KEY="replace-me"
JQUANTS_API_BASE_URL="https://api.jquants.com/v2"
JQUANTS_API_PLAN="premium"
JQUANTS_EQUITY_MASTER_ENABLED="true"
JQUANTS_EQUITY_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_INTRADAY_ENABLED="false"
```

Massive.com should be configured as the U.S. predictor source:

```bash
MASSIVE_API_KEY="replace-me"
MASSIVE_BASE_URL="https://api.massive.com"
MASSIVE_DAILY_TICKERS="SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLB,XLU,XLC,TLT,GLD,USO,EEM,FXI,SMH,HYG,LQD,EWJ,DXJ,EWY,EWT,EWH"
MASSIVE_MINUTE_TICKER="SPY"
MASSIVE_PROBE_TICKERS="I:VIX"
```

FRED, calendars, and rule-based Nikkei futures metadata use non-secret settings:

```bash
FRED_SERIES="VIXCLS,DGS2,DGS10,T10Y2Y,DEXJPUS"
CALENDAR_US_EXCHANGE="XNYS"
CALENDAR_JPX_EXCHANGE="JPX"
NIKKEI_CONTRACT_ROLL_DAYS_BEFORE_LAST_TRADE="5"
NIKKEI_CONTRACT_MONTHS="3,6,9,12"
```

## Data Plan

Minimum viable dataset:

- OSE Nikkei 225 futures contract metadata, trading calendar, session definitions, day-session open, close or settlement, volume, open interest, and roll dates.
- U.S. close information: SPY, QQQ, DIA, IWM, sector ETFs, VIX-style indexes, U.S. index futures or ETFs, rates proxies, USD/JPY, and major macro/news calendar flags.
- Japan context: Nikkei 225 spot index OHLC, Japan holidays, previous Japan cash and futures session behavior.
- Modeling labels: opening gap return, exceedance indicator, tail threshold, realized next-session adverse move, and train/test split timestamps.

Current source view:

- Massive.com is useful for U.S. close-side predictors, especially U.S. equities, ETFs, indexes, options, and CME-group futures as available by plan. It is not the primary source for OSE/JPX Nikkei 225 futures.
- JPX/J-Quants API is the right first source for daily OSE futures OHLC if the target is the Japanese Nikkei 225 futures contract. New development should use the V2 API key flow. The current local setup has Premium futures access for historical target audits; this remains a research source, not a live pre-open feed.
- JPX/J-Quants DataCube is the escalation path for one-minute or tick data if the opening print or session mechanics need higher-frequency validation.
- Nikkei Indexes can support spot Nikkei 225 OHLC, but that is not a substitute for the futures open/close target.

See `docs/data.md` for the data contract and source checklist.

## Repository Layout

```text
src/n225_open_gap_tail/   Source tree
tests/                    Unit and smoke tests
docs/                     Project notes and workflow docs
data/                     Local data only; ignored by git
reports/                  Local model outputs; ignored by git
notebooks/                Exploratory notebooks
```

The source tree is organized by function rather than by research-stage labels. This repo
runs in uv non-package mode (`tool.uv.package = false`); the code is not built or installed
as a wheel.

```text
n225_open_gap_tail/
  cli.py
  config/       Settings, research configuration, and shared runtime constants
  data_lake/    Atomic Parquet IO, schemas, Hive cache paths, and cache markers
  sources/      J-Quants, Massive, FRED, Cboe, and source readiness probes
  market/       Exchange calendars and Nikkei futures contract metadata
  features/     Timestamp-safe feature construction and as-of joins
  panel/        Durable gold panel construction and leakage binding
  forecasting/  Suite orchestration, run locking, and artifact routing
  models/       Benchmark and ML tail model implementations
  metrics/      VaR/ES losses, coverage tests, result matrix, and diagnostics
  inference/    Block-bootstrap DM, HLN Tmax MCS, Murphy, and stress diagnostics
  reporting/    LaTeX tables and notes
  diagnostics/  Snapshot and local git provenance helpers
```

## Data Utility Commands

```bash
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli jquants-smoke
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli massive-smoke
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli fred-smoke
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli calendar-build
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli contracts-build
```

These commands are debugging utilities, not the run workflow. They write through the same
cache vocabulary as the main pipeline: vendor payloads under `data/bronze/` and typed
normalized outputs under `data/silver/`.

For run work, use `just full`; do not mix utility smoke artifacts with research-run
evidence.

The manuscript-facing snapshot is generated separately from completed full-run artifacts:

```bash
just snapshot
```

It reads the latest completed `reports/runs/<run_id>` and durable `data/gold/` artifacts
to regenerate `docs/results_snapshot.md` without calling vendors.

## Research-Grade Workflow

The unified run entrypoint is:

```bash
just full
```

`full` runs local checks, builds the cache-first modeling panel, runs the Benchmark baseline floor,
audits feature leakage timestamps, runs the ML tail LightGBM information-set ladder, and
exports LaTeX table fragments under ignored
`reports/runs/`. The default panel start is `2016-07-19`; the run manifest then
computes `combined_clean_start` from required features only: J-Quants required-field
coverage, XLC-inclusive Massive core coverage, FRED core coverage, and the canonical
FRED H.10 USD/JPY control. These outputs are
`research_candidate_not_final_manuscript` until manually reviewed.

The data path is typed and resumable:

- J-Quants, Massive, FRED, calendar, and rule-based contract caches use ignored
  `data/bronze/` and `data/silver/`.
- Durable gold artifacts are stored under `data/gold/tailrisk_panel/schema_version=1/run_id=<run_id>/`.
  `reports/runs/<run_id>/` keeps run-specific forecasts, metrics, audits, and tables.
- Parquet writes are atomic and carry `xxhash64` chunk hashes plus schema hashes.
- Old orphan `.tmp` files are garbage-collected at run start.
- FRED current-historical caches are labeled `vintage_safe=false`; `DEXJPUS` is treated
  as a Federal Reserve H.10 weekly-batch as-of FX control, not a live FX mark.
- FRED current-historical caches use a 30-day TTL that is
  evaluated once at run start, not mid-run.
- Non-FX FRED predictors are selected feature-by-feature using timestamp-safe as-of
  logic. Release-lag fills carry explicit metadata, filled diffs are marked, and
  `fred_rates_staleness_days` enters the expanded ML tail block as an auditable staleness
  feature.
- SPY minute bars are reduced chunk-by-chunk to late-session features using the official
  NYSE close or early close; the late-volume-surge baseline is recomputed across loaded
  cache partitions, and full raw minute history is not retained by default.
- Derivatives intraday remains disabled, so `residual_usclosemark_to_open` is extension-only.
- ML tail writes feature-unavailability diagnostics under
  `reports/runs/<run_id>/metrics/`, including aggregate and date-level Parquet
  tables for missing active features.
- ML tail runs three registered LightGBM model families when the leakage gate passes:
  direct quantile, fully out-of-fold location-scale with Duan smearing, and
  fully out-of-fold standardized-loss POT-GPD. Location-scale/POT forecasts that fail
  sample, scale, or GPD validity gates are recorded as unavailable diagnostics rather than
  invalid paper-metric rows.
- ML tail keeps the strict headline information-set ladder in `ml_tail_metrics.parquet` and
  writes a separate `ml_tail_result_matrix*` layer for restricted common-sample VaR-only
  and VaR-ES comparisons across LightGBM tail-model families. These matrix rows are
  marked `headline_claim_allowed=false`; they support audit and discussion, not
  automatic superiority claims.

For custom windows or workers, pass recipe arguments positionally, for example
`just full 2022-01-01 "" 4`. The lower-level recipes remain available for debugging:
`_build-panel`, `_evaluate`, `_leakage-check`, and `_export-tables`.
`_evaluate` uses staged dispatch: `benchmark` runs the baseline floor; `ml_tail` runs the
LightGBM direct-quantile, location-scale, and standardized-loss POT-GPD information-set
ladder; richer econometric suites remain future work until they have real implementations.
