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
- Reports VaR coverage, quantile loss, Fissler-Ziegel VaR-ES loss, DM inference,
  Murphy diagrams, and supporting risk diagnostics.

The repository does not implement a live trading system, portfolio allocation rule, or
execution-cost study.

## Current Empirical Snapshot

The current clean snapshot is based on the completed run
`tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4`.

- Clean evaluation window: `2018-06-20` to `2026-05-22`.
- Forecast sample: `1722` trading-day observations.
- Primary risk level: 95% VaR, corresponding to a nominal 5% exception rate.
- Baseline benchmark median breach rate: about 5.8%.
- ML direct-quantile breach rates across nested information sets: about 8.9% to 12.3%.

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
- Advanced econometric benchmarks: CAViaR, CARE/expectile models, and GAS models
  where convergence and validity checks are satisfied.
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

Mutable research storage is also controlled by `.env`. On local machines, keep
`DATA_DIR` as an absolute external path outside cloud-synced checkouts. A
repo-local `data/` symlink is acceptable if it resolves outside this repo.
`REPORTS_DIR` can remain `reports` because run
summaries, figures, and tables are much smaller than the data lake.

Typical local checks:

```bash
just status
just check
```

`just check` syncs the uv environment and runs read-only validation: format check,
ruff lint, mypy, the mypy-ignore debt guard, default pytest, strict MkDocs build,
and local architecture/name guards. Use `just fix` when you want ruff to format
and apply automatic lint fixes.

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
exports LaTeX tables and figures, and writes run outputs under `REPORTS_DIR/runs/`.
When the `end` argument is omitted, the workflow uses the most recent completed
Friday as the data cutoff rather than the run date. Pass an explicit
`YYYY-MM-DD` end date to override that paper-freeze default.
The default is cache-first (`force=false`); use force only for intentional schema/cache
invalidation. By default, `just full` excludes Massive OPRA U.S. options features
(`options=false`) so the canonical full-history run is not driven by the shorter
OPRA entitlement window. To build those features only for appendix or recent-window
diagnostics, opt in explicitly:

```bash
just full 2016-07-19 "" 6 false false
```

For a completed run, regenerate the snapshot without fetching vendor data:

```bash
just snapshot latest
```

Snapshot export also refreshes the slide-facing model metrics audit under
`docs/tables/<run_id>/model_metrics_breach_audit.md` and
`docs/tables/<run_id>/model_metrics_full_rows.csv`. This companion artifact
covers the breach-neighborhood and sample-eligibility gates; the generated
Results Snapshot contains the full 24-check screen.

Appendix-only configuration robustness can be generated without changing
coverage admissibility or canonical paired-loss results:

```bash
just sensitivity latest
```

The sensitivity run is fixed to the post-24-check paper set: `GJR-GARCH-EVT`,
`LGBM mean/scale POT-GPD MLE (C)`, and `LGBM mean/scale POT-GPD UniBM (C)`.

The visible `just` surface is intentionally small:

```bash
just status
just source-probe
just check
just fix
just full
just snapshot latest
just sensitivity latest
just docs
```

## Outputs

- `docs/results_snapshot.md`: generated evidence map for the latest completed run.
- `REPORTS_DIR/runs/<run_id>/latex/tables/`: paper-facing LaTeX tables.
- `REPORTS_DIR/runs/<run_id>/latex/figures/`: paper-facing figures.
- `REPORTS_DIR/runs/<run_id>/latex/table_manifest.json`: table provenance.
- `REPORTS_DIR/runs/<run_id>/latex/figure_manifest.json`: figure provenance.
- `DATA_DIR`: local mutable data lake, ignored by git and kept outside the repo.
- `REPORTS_DIR`: local run summaries and generated reporting artifacts, ignored by git and usually kept at `reports`.

## Claim Boundaries

- The contribution is a forecast-evaluation design for Nikkei 225 Futures opening-gap
  VaR/ES, not a new machine-learning algorithm.
- The U.S.-close-mark target is deferred until licensed intraday Nikkei futures marks are
  available.
- EVT results are judged within the registered 95% VaR/ES design and its common
  out-of-sample dates.

## More Detail

- `docs/paper_plan.md`: research questions, model families, evaluation design, and claim
  boundaries.
- `docs/results_snapshot.md`: generated evidence map for the current completed run.
- `docs/data.md`: source roles, target hierarchy, point-in-time controls, and data
  limitations.
- `docs/future_work.md`: extensions that should remain separate from the current paper.
