# Development Audit

Use this as the single handoff for the next coding agent. It combines the development prompt with the audit checklist, so implementation and review use the same research contract.

```text
You are working in the n225-open-gap-tail repository. Your task is to build the first reproducible research pipeline for "The Incremental Content of U.S. Close Information for Pre-Open Downside Tail Risk: Evidence from OSE Nikkei 225 Futures".

The research is about OSE Nikkei 225 Futures downside pre-open tail risk, not generic Japanese equity overnight returns. OSE futures have a night session, so every model, table, and claim must state its forecast origin, reference price, target family, and information cutoff.

Start by auditing the current repository state against this contract. Only proceed to new implementation after documenting any blockers, non-blocking risks, missing tests, and documentation drift.

Before editing anything, read these files in order:

1. README.md
2. docs/results_snapshot.md
3. docs/data.md
4. docs/paper_plan.md
5. docs/audit/development.md
6. .env.example
7. pyproject.toml
8. justfile

Respect the existing workflow:

- Use `just status`, `just check`, and `just full` as the main entrypoints.
  Use lower-level recipes such as `just _build-panel` and `just _evaluate` only when debugging a specific layer.
- `just full` defaults to `2016-07-19` as a cache lower bound. The manifest computes
  `combined_clean_start` from required J-Quants field coverage, XLC-inclusive Massive core
  coverage, required FRED core coverage, and canonical FRED H.10 USD/JPY coverage. Do not
  hard-code a later modeling start in model code.
- Treat the data path as cache-first: Hive-style typed Parquet, atomic writes, `xxhash64`
  chunk hashes, run-start GC of orphan temp files, and layer-aware rebuilds. Rebuilding
  silver/gold must not call vendor APIs unless bronze is missing or refresh was explicitly
  requested.
- FRED current-historical caches are `vintage_safe=false`; TTL is evaluated once at run
  start, never mid-run. `DEXJPUS` must use H.10 batch-release as-of timing and is the
  only default USD/JPY source.
- The intended uv environment comes from `.env` through `UV_PROJECT_ENVIRONMENT`.
- Treat the sibling `../agent-runner` project as an external sidecar worker pool when delegation is useful. From this repo, call it through `just agent ...`, for example `just agent litellm-status` or `just agent run-worker "Objective" "src/foo.py,tests/test_foo.py"`.
- External worker outputs remain sidecar artifacts and worktrees until Codex or a human reviews them. Do not treat external worker patches as merged code or empirical evidence.
- Do not commit `.env`, `uv.lock`, raw vendor data, credentials, caches, generated reports, or local build artifacts.
- Keep tests honest: smoke tests, schema tests, and real-data validation tests must be named and documented separately.
- Maintain at least 95% test coverage. Every new functional module needs focused tests with small synthetic fixtures.

Audit checklist before adding features:

- Does every data row distinguish observation time, bar end time, research download time, vendor availability time where known, model cutoff time, and target-open time where relevant?
- Do Massive, FRED, calendar, and contract metadata outputs remain smoke/schema artifacts rather than empirical validation claims?
- Is J-Quants V2 the only J-Quants API path, with no V1 residue?
- Is the OSE futures target clearly labeled as historical J-Quants Premium research data rather than live pre-open production data?
- Are raw vendor data, `.env`, `uv.lock`, build outputs, generated data artifacts, and caches ignored?
- Do all `uv`-based `just` recipes require an external `UV_PROJECT_ENVIRONMENT`?
- Does `just check` pass with coverage above 95% and a strict docs build?
- Are tests named honestly as unit, schema, smoke, or real-data checks?
- Are rule-based contract metadata and exchange-calendar outputs clearly labeled as scaffolding that requires vendor reconciliation?
- Is any claim about model performance, VaR/ES calibration, or hedge usefulness unsupported by current artifacts?

Current implementation status:

- Main data-engineering path is implemented: source probes, cache-first bronze/silver reads, durable gold panel artifacts, calendar map, target audit, feature coverage, leakage binding, and run-specific reports.
- Benchmark floor is implemented for historical, rolling, EWMA/vol-scaled, GARCH/GJR, and GJR-GARCH-EVT style models behind gates. The advanced benchmark suite is implemented as a nonblocking benchmark layer with CAViaR, CARE/expectile, Taylor ALD, direct FZ-loss, GAS-t, and GAS-POT forecast rows plus optimizer diagnostics.
- ML tail path is implemented for `lightgbm_direct_quantile`, fully out-of-fold `lightgbm_location_scale`, and fully out-of-fold `lightgbm_standardized_loss_pot_gpd` over the registered nested information ladder.
- Result governance is implemented for headline metrics, per-model diagnostics, result matrix artifacts, feature-unavailability diagnostics, block-bootstrap DM, HLN Tmax MCS, Murphy diagnostics, stress windows, and DST attenuation records.
- The report layer now exports manuscript-facing ES severity, diagnostic VaR-trigger, DST attenuation, claim-scope, and result-matrix summary table fragments. These are still governance/reporting artifacts: ES severity is conditional on VaR exceptions, VaR-trigger rows are not hedge PnL or trading-alpha evidence, and DST attenuation is descriptive forecast evidence rather than a structural causal mechanism.

Implement the pipeline in this order:

0. Research design lock
   - Define forecast origins before ingestion or modeling:
     `US_CASH_CLOSE`, `OSE_NIGHT_CLOSE`, and `PREV_OSE_DAY_CLOSE`.
   - Define target families:
     `full_gap_settle_to_open`, `full_gap_close_to_open`, `residual_usclosemark_to_open`, and `residual_nightclose_to_day_open`.
   - Mark `residual_usclosemark_to_open` as unavailable unless an intraday Nikkei futures reference mark is licensed, timestamped, and available at the U.S. cash close.
   - Every empirical claim must specify forecast origin, reference price, target family, and information cutoff.
   - Treat upper-tail modeling as the right-tail futures risk surface, evaluated under the same gates as left-tail downside risk.

1. Configuration and schemas
   - Add typed settings for J-Quants and Massive.com access without exposing secret values.
   - Define stable internal schemas for futures session rows, U.S. predictor rows, target rows, feature rows, model-input rows, forecasts, and evaluation outputs.
   - Required timestamp and target fields:
     `observation_ts_utc`, `bar_start_ts_utc`, `bar_end_ts_utc`, `vendor_available_ts_utc`, `research_download_ts_utc`, `model_cutoff_ts_utc`, `target_open_ts_utc`, `reference_price`, `reference_price_ts_utc`, `reference_price_source`, `forecast_origin_name`, and `target_family`.
   - Required market-structure flags:
     `is_roll_window`, `is_sq_window`, `is_japan_holiday_adjacent`, `is_us_holiday_adjacent`, `is_us_early_close`, and `is_ose_holiday_trading`.
   - Add synthetic fixtures for normal dates, missing sessions, roll windows, SQ windows, U.S. early closes, DST transitions, and holiday-adjacent sessions.

2. J-Quants ingestion
   - Build a client or loader for OSE Nikkei 225 Futures daily/session OHLC.
   - Default to Nikkei 225 Futures large contract as the main target source.
   - Preserve fields needed for contract month, central contract flag, day-session OHLC, night-session OHLC, settlement price, volume, open interest, last trading day, and special quotation day.
   - Treat J-Quants futures OHLC as an ex-post research target source, not as a live pre-open production feed.
   - Write raw pulls only to ignored local data directories.

3. Massive.com ingestion
   - Build a client or loader for U.S. close-side predictors.
   - Start with a small explicit ticker universe: broad equity ETFs, major sector ETFs, volatility or implied-risk proxies where licensed, USD/JPY or rates proxies where available, and U.S. futures only where the subscribed plan supports them.
   - Store source, symbol, observation timestamp, bar start and end timestamp, vendor endpoint metadata, vendor availability timestamp, and research download timestamp.
   - Massive timestamps must be treated as UTC and explicitly converted to ET before U.S. session alignment.

4. Calendar and timestamp alignment
   - Implement ET/JST/UTC conversion and daylight-saving handling.
   - Build a join key that maps U.S. close information to the next eligible OSE day-session open.
   - Add tests for U.S. holidays, Japan holidays, U.S. early-close days, DST transitions, OSE non-trading days, U.S. close near OSE night close, Japan business day after a U.S. holiday, U.S. business day before a Japan holiday, and OSE night-session edge cases.

5. Target builder
   - Implement `full_gap_settle_to_open` as the primary daily/session target.
   - Implement `full_gap_close_to_open` as a secondary full-gap target.
   - Implement `residual_nightclose_to_day_open` as a robustness target when the night close is available and timestamp-valid.
   - Implement `residual_usclosemark_to_open` only as a disabled or unavailable target until a licensed intraday Nikkei futures reference mark exists.
   - Work with downside losses `L_t = -gap_t` for lower-tail modeling.
   - Generate target audit artifacts with missingness, distribution summaries, tail counts, extreme-gap source tracebacks, roll-window diagnostics, SQ-window diagnostics, and holiday-adjacent diagnostics.
   - Enforce target audit invariants:
     `target_open_ts_utc > model_cutoff_ts_utc`;
     `reference_price_ts_utc <= model_cutoff_ts_utc` for residual targets;
     no feature availability timestamp may be later than `model_cutoff_ts_utc`;
     roll-window observations are excluded, flagged, or evaluated in a dedicated robustness table;
     extreme targets are traceable to raw contract rows and session fields.

6. Feature builder
   - Build timestamp-safe U.S. close features.
   - Include the Tier 1 and Tier 1.5 candidate universe from `docs/data.md`: U.S. ETF returns and ranges, sector returns and dispersion, USD/JPY, TLT, GLD, USO, EEM, FXI, SMH where source coverage passes audit, Japan proxy tickers (`EWJ`, `DXJ`) and Asia proxy tickers (`EWY`, `EWT`, `EWH`) as separate ML tail information blocks, VIX close/range, SKEW or VIX term-structure proxies where licensed or public source support exists, Treasury rates, yield-curve slope, funding proxies, credit spreads, and calendar/event flags.
   - Add SPY late-session minute-bar features after timestamp validation: last-30-minute return, last-hour return, late-session range, late-60-minute volume surge, and final-window reversal or momentum. Freeze these features at U.S. close plus the configured vendor-availability lag, and recompute the volume-surge baseline across loaded cache partitions rather than inside each monthly chunk.
   - Mandate core lagged Japanese variables:
     prior gap, lagged OSE day returns, lagged OSE night returns where available, volume and open-interest changes, roll-window flags, SQ-window flags, Japan holiday-adjacent flags, U.S. holiday-adjacent flags, U.S. early-close flags, and OSE holiday-trading flags.
   - Add DST absorption fields:
     `dst_regime`, `us_close_to_ose_night_close_minutes`, `absorption_regime`, and optional `alpha_absorb_group`.
   - Add a feature leakage checklist artifact proving that every feature is available before the model cutoff and that the model cutoff precedes the target open.

7. Baseline models
   - Implement unconditional historical quantiles, rolling historical quantiles, EWMA or volatility-scaled quantiles, and a simple linear or penalized baseline.
   - Save baseline metrics before training LightGBM models.

7A. Econometric tail-risk baselines
   - Implement GARCH-t or GJR-GARCH-t if the dependency is available.
   - Implement GJR-GARCH-EVT on standardized residuals.
   - CAViaR SAV/asymmetric-slope variants are implemented as stateful recursive advanced benchmarks with empirical ES companions and optimizer diagnostics.
   - CARE/expectile-style VaR-ES, Taylor-style ALD VaR-ES, and direct FZ-loss variants are implemented as nonblocking advanced benchmark models with explicit VaR-ES semantics.
   - GAS-t and GAS-POT are implemented as score-driven advanced benchmarks; keep them appendix/diagnostic unless the sample gates and author review support stronger use.
   - GAS-t currently uses the registered raw Student-t log-scale score recursion (`score_scaling=raw_student_t_log_scale_score`) with log-scale state; invalid score/state, invalid `nu`, or exploding scale must emit `unavailable_gas_filter_failed`. A true unit-inverse-Fisher GAS variant requires a separate formula change and rerun.
   - CARE is expectile-based and separate from Taylor ALD. Its expectile level must be calibrated on the training window by grid search to match the target VaR exception rate, with `expectile_tau`, calibration breach rate, objective, and status recorded.
   - Full advanced benchmark evaluation is runtime-heavy: expect roughly 4--8 hours single-threaded for all optimizer-based model-by-tail shards; use `benchmark-floor` for fast checks and parallelize only across model/tail shards.
   - If a main advanced benchmark is numerically unstable or sample-inadequate, label it unavailable with a reason; do not replace it with weak evidence.
   - Save these metrics before LightGBM tuning.

8. LightGBM model variants
   - Implement chronological validation only; do not use random train/test splits.
   - ML tail first pass runs `lightgbm_direct_quantile`, `lightgbm_location_scale`, and
     `lightgbm_standardized_loss_pot_gpd` over the registered nested ladder:
     `japan_only`,
     `japan_only_plus_us_close_core`,
     `japan_only_plus_us_close_core_plus_japan_proxy`,
     and `japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy`.
   - Require `leakage_check_failures = 0` before ML tail model evaluation.
   - Use month-level refits with daily forecasts for the first LightGBM pass; record active feature hashes, dropped features, training missingness, training variance, target family, information set, tail level, and refit frequency.
   - `lightgbm_location_scale` uses fully out-of-fold standardized losses, pooled Duan smearing, empirical standardized VaR/ES, and explicit unavailable diagnostics when OOF sample, scale, or ES gates fail.
   - `lightgbm_standardized_loss_pot_gpd` reuses the same fully OOF standardized losses and fits GPD exceedances with `loc=0`; finite-ES, threshold, and exceedance-count gates must pass before emitting forecast rows.
   - Keep `lightgbm_direct_quantile` as the unchanged direct quantile benchmark at registered tail levels.
   - Implement `exceedance_probability_model` for rolling lower-tail thresholds only after the main ML tail ladder is stable; this is not current evidence.
   - Optionally implement `severity_model` for exceedance magnitudes; this is not current evidence.
   - Calibrate probability outputs on validation data when they are used as exceedance probabilities.
   - Keep hyperparameter tuning simple and reproducible in the first pass.

9. EVT layer
   - Use the primary LightGBM-EVT interface from `docs/paper_plan.md`: LightGBM estimates a location-scale pair, losses are standardized by predicted scale, POT-GPD is fit on fully out-of-fold standardized downside exceedances, and VaR/ES are transformed back to the target scale.
   - Fit POT-GPD on standardized losses as the first reported hybrid specification; other EVT interfaces remain robustness extensions.
   - Use timestamp-safe training-window information only; never calibrate EVT tails on in-sample fitted standardized residuals.
   - Select thresholds using mean-excess linearity plus GPD shape and scale stability above the threshold.
   - Store threshold grid diagnostics: exceedance count, mean excess, Hill or tail-index estimates where appropriate, shape stability, scale stability, and sensitivity across nearby thresholds.
   - Add optional automated threshold diagnostics such as Danielsson-style double-bootstrap or Beirlant-Goegebeur style sequential checks when implementation is stable.
   - Enforce a minimum exceedance count before reporting an alpha level.
   - Report empirical levels such as 5%, 2.5%, and 1% separately from extrapolated levels.
   - Do not claim 0.1% performance unless the sample size supports meaningful evaluation.
   - Evaluate VaR and ES separately and jointly.

10. Evaluation and manuscript artifacts
    - Produce reproducible tables and figures under ignored report/artifact directories.
    - Report quantile loss, VaR coverage, conditional coverage or independence tests, dynamic quantile diagnostics where feasible, Fissler-Ziegel joint VaR-ES score, ES exceedance severity diagnostics, and tail ranking metrics.
    - Build Murphy diagrams for VaR-ES dominance diagnostics; treat them as diagnostic plots, not standalone significance tests.
    - Build model-comparison artifacts with block-bootstrap DM and HLN Tmax MCS when the OOS loss series supports it. Side-specific instrumented conditional predictive ability diagnostics are implemented for ML-tail direct-quantile information-set comparisons.
    - Inspect `ml_tail_feature_unavailability.parquet` and
      `ml_tail_feature_unavailability_dates.parquet` before changing model-eviction thresholds;
      release-lagged FRED rates should be handled by timestamp-safe fill metadata, while
      remaining SPY late-session volume gaps are explicit active-feature exclusions.
    - Keep `ml_tail_metrics.parquet` as the headline ML tail ladder. Use `ml_tail_result_matrix*`
      artifacts for restricted VaR-only and VaR-ES comparisons across LightGBM tail-model
      families and within-model information-set increments; these rows are diagnostic or
      restricted evidence and must not be promoted into automatic superiority claims.
    - Report quantile-score calibration and sharpness decomposition when implementation is stable.
    - Build incremental-information tables in this order:
      Japan-only, Japan plus U.S. close core, Japan plus U.S. close core plus Japan proxy,
      and Japan plus U.S. close core plus Japan proxy plus Asia proxy.
    - Use the exported DST attenuation table with the absorption coefficient and its component gains by EST/EDT regime as descriptive forecast evidence. Do not call it a structural causal mechanism without a separate registered identification design.
    - Use the exported ES severity table for exceedance-severity diagnostics. It reports severity conditional on VaR exceptions and should be reviewed before being converted into manuscript prose.
    - Use the exported VaR-trigger diagnostic table only as a pre-open risk-monitoring diagnostic. It reports a fixed within-model VaR trigger, false alarms, missed exceptions, and triggered exception severity; it does not estimate hedge PnL, costs, turnover, or loss avoided.
    - Treat hedge-trigger results as pre-open risk-management diagnostics, not trading-profit claims.

Acceptance criteria for each implementation phase:

- `just check` passes with coverage >= 95% and a strict docs build.
- New outputs are either small tracked synthetic fixtures or ignored local artifacts.
- No vendor credentials or raw market data are committed.
- Documentation is updated when behavior, schemas, or workflow entrypoints change.
- Claims are labeled honestly: schema checks, smoke checks, and real-data validation are not interchangeable.
- Any unavailable target or benchmark is explicitly marked as unavailable/deferred with a reason.

When reporting progress, separate:

- Blocking issues.
- Non-blocking risks.
- Missing tests.
- Documentation drift.
- Recommended next implementation step.
- Implemented and tested.
- Implemented but only smoke-tested.
- Requires real vendor data.
- Requires licensed intraday data.
- Still planned or deferred.

Use file paths and line references where possible. Do not propose model work until the target-data audit gate is satisfied.
```
