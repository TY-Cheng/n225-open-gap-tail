# N225 Open Gap Tail Risk

Research code for a point-in-time out-of-sample study of OSE Nikkei 225 Futures
opening-gap tail risk.

The paper asks whether information observed at the U.S. cash-market close helps forecast
the VaR and Expected Shortfall (ES) of the next OSE day-session open. The setting is not a
generic overnight-return exercise: OSE futures trade through an active night session, so
U.S. information may be partially incorporated before the Japanese opening auction.

## What This Repository Does

- Builds a point-in-time forecast panel for Nikkei 225 Futures opening-gap risk.
- Evaluates downside and upside opening-gap risk as separate tail surfaces.
- Tests nested information sets built around Japan-only history, U.S. close variables,
  Japan proxy ETFs, and Asia proxy ETFs.
- Compares benchmark econometric models, advanced tail-risk benchmarks, and LightGBM tail
  specifications.
- Reports VaR coverage, quantile loss, Fissler-Ziegel VaR-ES loss, DM/MCS inference,
  conditional predictive ability diagnostics, Murphy diagrams, and supporting risk
  diagnostics.

The repository does not implement a live trading system, portfolio allocation rule, or
execution-cost study.

## Current Empirical Snapshot

The current clean snapshot is based on the completed run
`tailrisk_20160719_20260429_20260508T053721Z_commit_14205f41`.

- Clean evaluation window: `2018-06-20` to `2026-04-28`.
- Forecast sample: `1660` trading-day observations.
- Primary risk level: 95% VaR, corresponding to a nominal 5% exception rate.
- Baseline benchmark median breach rate: about 6.1%.
- ML direct-quantile breach rates across nested information sets: about 7.6% to 12.7%.

This means lower average loss values for the ML tail models must be read together with
coverage diagnostics. In the current evidence, the direct-quantile LightGBM models often
produce less conservative VaR estimates than the baseline benchmarks.

The current results are research-candidate evidence. Final manuscript claims still require
author review of the tables, figures, and claim boundaries.

## Research Design

### Target

The main target is the settlement-to-open gap:

```text
log(OSE day-session open) - log(previous settlement)
```

Forecasts are evaluated in positive loss units:

- `left_tail`: downside opening-gap risk, `realized_loss = -gap_t`.
- `right_tail`: upside opening-gap risk, `realized_loss = gap_t`.

For both sides, a VaR exception is defined as:

```text
realized_loss > var_forecast
```

Left and right tails are evaluated separately. The empirical results should not be
averaged across sides or interpreted as the same economic mechanism.

### Information Sets

- `japan_only`: target history, lagged Japanese futures variables, rolling volatility,
  volume/open-interest information, and Japanese calendar variables.
- `japan_only_plus_us_close_core`: adds U.S. close equity, volatility, FX, and rates
  predictors available before the OSE open.
- `japan_only_plus_us_close_core_plus_japan_proxy`: adds U.S.-traded Japan proxy ETFs,
  including `EWJ` and `DXJ`.
- `japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy`: adds Asia proxy ETFs,
  including `EWY`, `EWT`, and `EWH`.

### Models

- Baseline benchmarks: historical quantile, rolling quantile, volatility-scaled quantile,
  GARCH/GJR-GARCH, and GJR-GARCH-EVT.
- Advanced econometric benchmarks: CAViaR, CARE/expectile models, GAS models, Taylor-style
  asymmetric-Laplace VaR-ES specifications, and joint VaR-ES estimation through
  Fissler-Ziegel scoring where convergence and validity checks are satisfied.
- ML tail models: flexible, tree-based direct quantile estimation via gradient boosting
  (LightGBM), LightGBM location-scale models, and LightGBM standardized-loss POT-GPD.

ML tail models are refit monthly using expanding training windows. LightGBM
hyperparameters are held fixed across information sets and refit dates to limit
data-dependent tuning.

## Point-in-Time Controls

Every predictor used for a forecast must satisfy:

```text
feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc
```

The current audit reports no hard look-ahead-bias failures. FRED macro-financial
predictors use conservative publication lags, but they do not use unrevised real-time
ALFRED vintages. This is a data limitation and should be disclosed in empirical writing.

## Data Sources

- J-Quants Premium: Nikkei 225 Futures daily prices, settlement, volume, and open interest.
- Massive: U.S. ETFs, Japan proxy ETFs, Asia proxy ETFs, and curated
  U.S.-listed ETF late-session minute predictors.
- FRED: rates, FX, and macro-financial predictors with publication-lag controls.
- CBOE: volatility-index predictors, including VIX.

Source credentials belong in `.env`. Do not commit `.env`; keep shareable defaults in
`.env.example`.

## Quick Start

This repo uses `uv` and `just`. The local virtual environment is controlled by `.env`:

```bash
UV_PROJECT_ENVIRONMENT="${HOME}/.venvs/n225-open-gap-tail"
```

Typical local checks:

```bash
just status
just check
```

`just check` syncs the uv environment, formats and fixes `src` and `tests`, runs mypy,
runs pytest, and performs a strict MkDocs build.

To serve the documentation site:

```bash
just docs
```

## Research Run

The full workflow is:

```bash
just full
```

It runs checks, builds the point-in-time panel, evaluates benchmark and ML-tail suites,
exports LaTeX tables and figures, and writes run outputs under ignored `reports/runs/`.
The default is cache-first (`force=false`); use force only for intentional schema/cache
invalidation. By default, `just full` also enables bounded U.S. options features
(`options=true`): it uses Massive OPRA `day_aggs_v1` flat files to compute ATM-IV
proxies and routes them by economic exposure into the B/C information sets. To run
without U.S. options features, use:

```bash
just full 2016-07-19 "" 6 false false
```

For a completed run, regenerate the snapshot without fetching vendor data:

```bash
just snapshot latest
```

Useful lower-level commands are available for debugging:

```bash
just _build-panel
just _evaluate <run_id> 4 benchmark false both
just _evaluate <run_id> 4 ml-tail false both
just _export-tables <run_id>
```

## Outputs

- `docs/results_snapshot.md`: generated evidence map for the latest completed run.
- `reports/runs/<run_id>/latex/tables/`: paper-facing LaTeX tables.
- `reports/runs/<run_id>/latex/figures/`: paper-facing figures.
- `reports/runs/<run_id>/latex/table_manifest.json`: table provenance.
- `reports/runs/<run_id>/latex/figure_manifest.json`: figure provenance.
- `data/` and `reports/`: local data and model outputs, ignored by git.

## Claim Boundaries

- The contribution is a forecast-evaluation design for Nikkei 225 Futures opening-gap
  VaR/ES, not a new machine-learning algorithm.
- Conditional predictive ability results are loss-differential regressions on ex-ante
  observables. They do not generate VaR or ES forecasts.
- DST results are descriptive timing-regime evidence, not structural identification.
- Trigger diagnostics are risk-monitoring summaries, not trading-strategy evidence.
- The U.S.-close-mark target is deferred until licensed intraday Nikkei futures marks are
  available.
- EVT results should first be judged at 95% VaR on common out-of-sample dates. Promotion
  of 97.5% results requires sufficient common-sample size, exception counts, and stable
  POT-GPD diagnostics.

## More Detail

- `docs/paper_plan.md`: research questions, model families, evaluation design, and claim
  boundaries.
- `docs/results_snapshot.md`: generated evidence map for the current completed run.
- `docs/data.md`: source roles, target hierarchy, point-in-time controls, and data
  limitations.
- `docs/future_work.md`: extensions that should remain separate from the current paper.
