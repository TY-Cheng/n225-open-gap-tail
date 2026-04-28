# N225 Open Gap Tail Risk

Research code for **The Incremental Content of U.S. Close Information for Pre-Open Downside Tail Risk: Evidence from OSE Nikkei 225 Futures**.

The intended target is the next Osaka Exchange Nikkei 225 futures day-session opening gap, measured from the prior relevant OSE close or settlement to the next day-session open. The feature set should only use information observable before the Japan day-session open, with special attention to the U.S. cash close, U.S. futures marks, volatility indexes, USD/JPY, and cross-market ETF or sector signals.

## Setup

This repo uses `uv` and `just`. The local virtual environment is controlled by `.env`:

```bash
UV_PROJECT_ENVIRONMENT="${HOME}/.venvs/n225-open-gap-tail"
```

```bash
just setup
just status
just test
```

Do not commit `.env`; put shareable defaults in `.env.example`.

J-Quants should be configured through the V2 API key flow:

```bash
JQUANTS_API_VERSION="v2"
JQUANTS_API_KEY="replace-me"
JQUANTS_API_BASE_URL="https://api.jquants.com/v2"
JQUANTS_API_PLAN="free"
JQUANTS_EQUITY_MASTER_ENABLED="true"
JQUANTS_EQUITY_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_DAILY_ENABLED="false"
```

Massive.com should be configured as the U.S. predictor source:

```bash
MASSIVE_API_KEY="replace-me"
MASSIVE_BASE_URL="https://api.massive.com"
MASSIVE_DAILY_TICKERS="SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLB,XLU,XLC,TLT,GLD,USO,EEM,FXI,SMH,HYG,LQD,C:USDJPY"
MASSIVE_MINUTE_TICKER="SPY"
MASSIVE_PROBE_TICKERS="I:VIX"
```

FRED, calendars, and rule-based Nikkei futures metadata use non-secret settings:

```bash
FRED_SERIES="VIXCLS,DGS2,DGS10,T10Y2Y,BAMLH0A0HYM2,BAMLC0A0CM"
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
src/n225_open_gap_tail/   Python package
tests/                    Unit and smoke tests
docs/                     Project notes and workflow docs
data/                     Local data only; ignored by git
reports/                  Local model outputs; ignored by git
notebooks/                Exploratory notebooks
```

## Data Smoke Tests

```bash
n225-open-gap-tail jquants-smoke
n225-open-gap-tail massive-smoke
n225-open-gap-tail fred-smoke
n225-open-gap-tail calendar-build
n225-open-gap-tail contracts-build
n225-open-gap-tail snapshot
```

The J-Quants smoke command downloads a tiny V2 sample and probes the futures endpoint. The snapshot command runs the 2022-present full-smoke target audit and predictor availability pipeline, writes Parquet/JSON artifacts under ignored `reports/snapshots/`, and regenerates `docs/results_snapshot.md`.

The Massive smoke command downloads a small U.S. daily aggregate panel plus a one-day minute aggregate sample. Raw API payloads go under ignored `data/raw/massive/`; normalized parquet files with timestamp audit columns go under ignored `data/interim/massive/`.

The FRED smoke command downloads historical VIX and Treasury-rate proxies. The calendar build command creates U.S./JPX trading-day, early-close, holiday, and DST alignment tables. The contracts build command creates rule-based Nikkei 225 futures quarterly contract metadata and a central-contract selector; this is research scaffolding that must be reconciled against J-Quants or JPX contract metadata before final empirical results.

## Paper-Grade P2A Workflow

The unified paper-grade entrypoint is:

```bash
just full
```

`full` runs local checks, builds the full-history paper panel, runs the P2A baseline floor,
audits feature leakage timestamps, and exports LaTeX table fragments under ignored
`reports/paper_runs/`. These outputs are `paper_candidate_not_final_manuscript` until
manually reviewed.

For custom windows or workers, pass recipe arguments positionally, for example
`just full 2022-01-01 "" 4`. The lower-level recipes remain available for debugging:
`_paper-panel`, `_paper-eval`, `_paper-leakage-check`, and `_paper-latex-tables`.
`_paper-eval` uses staged dispatch: `p2a` runs the baseline floor; `p2b`/`p2c` are
explicit nonblocking gates until their registered model implementations produce evidence.
