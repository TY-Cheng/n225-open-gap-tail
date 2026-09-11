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

This repo uses `uv` and `just`, with Python 3.13.15 as the local/CI target.
Dependency versions are recorded in `uv.lock`. The local virtual
environment is controlled by `.env`:

```bash
UV_PROJECT_ENVIRONMENT="${HOME}/.venvs/n225-open-gap-tail"
```

When upgrading from Python 3.12, keep the old environment for reproducing prior
runs and create a separate environment before changing `.env`:

```bash
UV_PROJECT_ENVIRONMENT="${HOME}/.venvs/n225-open-gap-tail-py313" \
  uv sync --python 3.13.15 --locked --all-extras --dev
```

Mutable research storage is also controlled by `.env`. On local machines, keep
`DATA_DIR` as an absolute external path outside cloud-synced checkouts. A
repo-local `data/` symlink is acceptable if it resolves outside this repo.
`ARTIFACTS_DIR` defaults to `artifacts`: each experiment writes directly to
`artifacts/<run_id>/`, without an intermediate `runs/` directory. `REPORTS_DIR`
is reserved for human-readable reports, not experiment inputs or outputs.

Typical local checks:

```bash
just status
just check
```

`just check` syncs the uv environment and runs read-only validation: format check,
ruff lint, mypy, the mypy-ignore debt guard, default pytest, strict MkDocs build,
and local architecture/name guards. Use `just fix` when you want ruff to format
and apply automatic lint fixes.

Tool caches live under `.cache/`: `mypy/`, `pytest/`, `ruff/`, and
`coverage/`. Keep local run checkpoints and ad hoc review notes in
`.cache/reports/`; these and root `CONTEXT.md` are ignored by Git.
Keep durable research decisions and reproducible instructions in `docs/`,
not solely in local notes. Existing tracked documentation and paper assets
remain versioned.

To serve the documentation site:

```bash
just docs
```

## Research Run

The revised 28-spec experiment has a separate `body-rolling --source-run ...
--output-dir ...` CLI entry point. It rebuilds the accepted sample view from
source panel data, generates monthly shared-body forecasts for A--D/both tails,
and writes per-refit OOF/diagnostics into a new directory. It does not reuse old
forecast shards, run external benchmarks, select models, or export a manuscript.
Run the existing benchmark suite on that same new panel before `reevaluate`;
the latter reads the new run's 28-model roster. These are separately authorized
execution steps. `body-pilot` remains the bounded one-date entry point. Public
UniBM must be importable in the process environment. The legacy `just full`
workflow below still uses the original eight ML specifications.

`body-tuned --source-run ... --output-dir ...` runs the accepted bounded
component search before those same 28 forecasts. Each outer monthly cutoff uses
three-fold random CV (shuffle, seed 0) over the full training history, with
common validation-date folds and at least 250 training observations per case.
Held-out losses are pooled by date within each scenario, then averaged equally
across A--D/both tails to select shared parameters. Spread CV targets are formed
using the center fitted on that fold's training subset; there is no nested HPO.
Final center and spread fits use full native histories; their **in-sample**
standardized residuals calibrate the tails, with zero artificial OOF warm-up and
actual nonfinite positions retained. This is not OOF tail calibration or a claim
of temporally independent inner validation; the outer monthly test stays separate.
The finite pool has six configurations and
79/139/199 round caps. Each candidate/fold/scenario is fitted once up to 199
rounds and scored at all three prefixes, with no additional continuous
early-stopping search. Incomplete candidates are not ranked on fewer cases;
if none is complete, the existing fixed-settings/160-round fallback is retained.
LGBM--POT-MLE and LGBM--UniBM use a shape upper bound of 0.99. A changed MLE
shape triggers a fixed-shape GPD scale refit; UniBM scale is fitted at the bounded
shape. VaR and ES use this same final pair. Only the final `evt_shape` is reported,
without a raw/used shape pair or cap-hit flag. Retained UniBM regression uncertainty
and bootstrap diagnostics describe the underlying fit, not the capped estimator.
External benchmarks are unchanged; no extra ML cap/threshold sensitivity is run.
Single fits are limited to 300 seconds and each joint selection to 30 minutes.
`--forecast-date 2026-05-01 --workers 1` restricts this command to an all-eight, one-date
pilot with a 60-minute workflow budget; supervise the process group to enforce
that ceiling even during native tail-estimator calls. Full runs support
`--workers 1` through `3` (default `2`) for independent months, with LightGBM
`num_threads=3` per fit; this never separates the eight-way selection. Other
nested BLAS thread limits remain at one. Selection receipts live in `selection/`, per-refit
`in_sample_residuals.parquet` and forecasts in `refits/`, and the aggregate
predictions in `forecasts/`.
The run also preserves its working-tree source diff/new source files. Current
training uses decimal losses; old multiplier-100 artifacts remain unchanged.

`reevaluate` writes native VaR gates and comparison-specific common-date FZ0
results, then `grem_curves.parquet` and `grem_summary.parquet`. GREM includes the
entire pre-screen candidate roster, with W=500 primary and W=250 sensitivity;
it never changes model/reference selection. Bets use earlier eligible observations
and cumulative capital never resets. Known calendar/forecast unavailability gets
zero bets; missing losses or unverified availability timing leave an explicit
unavailable suffix. The reference level 20 is per-sequence, not a simultaneous
or post-selection guarantee. See the accepted Q28--Q30 in `docs/paper_plan.md`.

Q14 adds `joint_calibration.parquet`, `joint_murphy.parquet` and
`joint_murphy_samples.parquet` without changing that selection. Native joint
identification means have pointwise block-bootstrap intervals; these are not a
joint or conditional calibration test. Murphy curves use joint-eligible fixed
common dates and a finite shared threshold grid, not a dominance test.

The full workflow is:

```bash
just full
```

It runs checks, builds the point-in-time panel, evaluates benchmark and ML-tail suites,
exports LaTeX tables and figures, and writes run outputs under `ARTIFACTS_DIR/<run_id>/`.
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
- `ARTIFACTS_DIR/<run_id>/`: run manifests, panel copies, forecasts, metrics, and diagnostics.
- `ARTIFACTS_DIR/<run_id>/latex/tables/`: paper-facing LaTeX tables.
- `ARTIFACTS_DIR/<run_id>/latex/figures/`: paper-facing figures.
- `ARTIFACTS_DIR/<run_id>/latex/table_manifest.json`: table provenance.
- `ARTIFACTS_DIR/<run_id>/latex/figure_manifest.json`: figure provenance.
- `DATA_DIR`: local mutable data lake, ignored by git and kept outside the repo.
- `ARTIFACTS_DIR`: defaults to `artifacts`, ignored by git. Re-evaluation defaults to
  a sibling directory named `reevaluation_<source_run_id>_<timestamp>`; explicit
  `--output-dir` options remain available.
- `REPORTS_DIR`: optional human-readable reports, ignored by git; defaults to `reports`.

Existing local `reports/runs/<run_id>/` directories must be moved to
`artifacts/<run_id>/` when adopting this layout. Update their manifest/metadata
path locators, retaining the original execution logs, model configuration, and
data-lake bindings. There is no legacy-path fallback.

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
