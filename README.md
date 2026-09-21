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
- Screens native VaR/ES forecasts using Kupiec, Christoffersen independence and
  GREM, then compares admitted models using FZG, quantile loss, paired inference
  and an FZG model confidence set.

The repository does not implement a live trading system, portfolio allocation rule, or
execution-cost study.

## Current Empirical Snapshot

The current snapshot uses frozen forecasts from
`body22_expanding_oof_cov97_full_20260913`, reevaluated in
`reevaluation_fzg_grem_20260921` without retraining.

- Scheduled OOS: 2023-01-26–2026-05-22, with 722 clean target dates.
- Two of 22 ML recipes pass all eight scenarios: Median–IQR–UniBM and
  Mean–RMS-Gamma–POT-MLE. Four of 12 external models pass both tails.
- External-only FZG selection chooses GJR-GARCH-EVT as the single reference.
- The main comparison uses 628 joint dates, 2023-07-03–2026-05-22.
- IQR–UniBM has the lowest mean FZG; Gamma–MLE has the lowest quantile loss.
  FZG MCS retains both ML models, so no unique best ML model is established.

These are exploratory, same-inspected-OOS results, not fresh-holdout validation.
See `docs/results_snapshot.md` for exact scores, tests, sensitivity and provenance.

## Research Design

### Target

The main target is the settlement-to-open gap:

```text
log(OSE day-session open) - log(previous settlement)
```

Forecasts use an upper-loss orientation; losses and forecasts may be negative:

- `left_tail`: downside opening-gap risk, `realized_loss = -gap_t`.
- `right_tail`: upside opening-gap risk, `realized_loss = gap_t`.

For both sides, a VaR exception is defined as:

```text
realized_loss > var_forecast
```

Admission is assessed separately in every scenario. Comparative scores average
A–D and both tails equally within each shared date, then average dates equally.
This global objective does not imply identical left/right economic mechanisms.

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

ML tail models are refit monthly using expanding training windows. Bounded
inner expanding-OOF selection shares LightGBM parameters across information sets
and tails within each refit; the selected parameters can change between months.

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

The revised 22-spec experiment (seven bodies x three tails plus direct quantile)
excludes Fair--log-absolute and Mean--RMS-Tweedie. Ordinary, minute and options
features require at least 97% finite coverage in each training window.
It has a separate `body-rolling --source-run ...
--output-dir ...` CLI entry point. It rebuilds the accepted sample view from
source panel data, generates monthly shared-body forecasts for A--D/both tails,
and writes per-refit OOF/diagnostics into a new directory. It does not reuse old
forecast shards, run external benchmarks, select models, or export a manuscript.
Run the existing benchmark suite on that same new panel before `reevaluate`;
the latter reads the new run's 22-model roster. These are separately authorized
execution steps. `body-pilot` remains the bounded one-date entry point. Public
UniBM must be importable in the process environment. The legacy `just full`
workflow below still uses the original eight ML specifications.

`body-tuned --source-run ... --output-dir ...` runs the accepted bounded
component search before those same 22 forecasts. Each outer monthly cutoff uses
five expanding validation blocks, with size `ceil((N_common - 250) / 5)` and
at least 250 earlier training observations per case. There is no shuffle.
Held-out losses are pooled by date within each scenario, then averaged equally
across A--D/both tails to select shared parameters once per component, not once
per fold. Spread targets use the selected center's earlier OOF errors; only
structurally eligible folds enter spread selection. The winner's actual prefix
predictions are retained, so selected folds are not trained again. Standardized
OOF residuals calibrate the tails, preserving warm-up and later missing positions.
Final center fits use full native histories; final residual-based spread fits
use all available OOF center errors. IQR uses the fitted quartiles instead.
Parameter selection uses the whole outer training window: these are time-ordered
OOF residuals, not an archive of historically selected hyperparameters or a
selection-independent calibration sample. The outer monthly test stays separate.
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
`oof_residuals.parquet` and forecasts in `refits/`, and the aggregate
predictions in `forecasts/`.
The run also preserves its working-tree source diff/new source files. Current
training uses decimal losses; old multiplier-100 artifacts remain unchanged.

`reevaluate` applies native VaR gates plus W500 ES-GREM before selecting the
single global external reference and comparing all admitted ML recipes. It
writes native availability, fixed-common-date FZG/quantile scores, all-pair
two-sided bootstrap tests with Holm adjustment, and FZG-only MCS. FZG accepts
coherent signed ES and uses percentage-point units for evaluation only.

To compare information sets only within the frozen admitted recipes, without
rerunning gates or training, use a new output directory:

```bash
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli information-contrasts \
  --evaluation-dir artifacts/reevaluation_fzg_grem_20260921 \
  --output-dir artifacts/information_contrasts_20260921
```

This writes A−reference, B−A, C−B and D−C tests for each admitted ML recipe,
using the original main common dates and equal tail weights. All requested
contrasts share one Holm family per score/block, separate from the global
model comparisons. Outputs include scores, paired tests, a report and a two-panel
FZG figure (A–D mean CIs, a GJR reference band and paired CIs/Holm p-values).
Mean-level FZG intervals are recorded in `mean_intervals.parquet`;
existing directories are never overwritten.

To assemble the paper figure/table bundle from these frozen outputs, without
training, rescoring or rerunning inference:

```bash
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli paper-bundle \
  --evaluation-dir artifacts/reevaluation_fzg_grem_20260921 \
  --information-dir artifacts/information_contrasts_20260921 \
  --output-dir artifacts/paper_bundle_20260921
```

The new directory contains PNG/PDF figures, CSV/LaTeX tables, captions and a
source/output hash manifest. It covers sample availability and forecast timing,
all-candidate admission, global comparison/MCS, information increments and native
GREM diagnostics. Existing output directories are refused. This narrow export
does not use the historical FZ0/Set-C figure pipeline or modify the manuscript.

GREM covers the entire pre-screen roster. W500 is a gate; W250 is sensitivity.
At least 450 eligible observations and a complete native sequence with historical
running maximum below 20 are required. Bets use earlier eligible observations;
capital never resets. Cutoff-audited unavailable forecasts get no bets, while
missing losses or unauditable timing leave an explicit unavailable suffix.
The threshold 20 is per sequence, not a recipe-level or post-selection guarantee.
Full rules are in `docs/paper_plan.md`. Historical FZ0/Murphy artifacts remain
unchanged but are not the current default reevaluation outputs.

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

For a completed legacy full run, generate a run-local snapshot without fetching
vendor data or overwriting the maintained website pages:

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

- `docs/results_snapshot.md`: maintained current evidence summary for the website.
- `ARTIFACTS_DIR/<run_id>/snapshot/`: generated legacy run-local results, FAQ and assets.
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
- `docs/results_snapshot.md`: current frozen-forecast scores, gates and inference.
- `docs/data.md`: source roles, target hierarchy, point-in-time controls, and data
  limitations.
- `docs/future_work.md`: extensions that should remain separate from the current paper.
