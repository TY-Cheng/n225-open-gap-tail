# Development Audit Prompt

Use this as the handoff contract for implementation review. It should stay durable:
keep the research boundaries, audit questions, and claim gates here; keep concrete
commands, file paths, and artifact names in the repository documentation and current
workflow outputs.

```text
You are working in the n225-open-gap-tail repository. Your task is to build and audit
the reproducible research pipeline for "U.S. Close Information and Pre-Open Tail Risk
in OSE Nikkei 225 Futures".

The research is about OSE Nikkei 225 Futures pre-open tail risk, not generic Japanese
equity overnight returns. Both left-tail downside risk and right-tail upside risk are
modeled as separate futures risk surfaces. OSE futures have a night session, so every
model, table, figure, and claim must state its forecast origin, reference price, target
family, tail side, and information cutoff.

Start by auditing the current repository state against this contract. Only proceed to
new implementation after documenting blockers, non-blocking risks, missing tests, and
documentation drift.

Working principles:

- Use the repository's documented workflow entrypoints for status checks, validation,
  full runs, and documentation builds. Use lower-level entrypoints only when debugging
  a specific layer.
- Treat the data path as cache-first. Rebuilding derived layers must not call vendor
  APIs unless raw caches are missing or refresh was explicitly requested.
- Vendor credentials, raw vendor data, local environments, caches, generated reports,
  and local build artifacts are machine-local state and must not be committed.
- Any external sidecar or worker output remains unmerged evidence until Codex or a
  human reviews it. Do not treat worker patches or sidecar artifacts as repository
  truth before review.
- Keep tests honest: unit tests, schema tests, smoke tests, and real-data validation
  tests must be named and documented separately.
- Maintain the repository's coverage and strict documentation-build standard. Every
  new functional module needs focused tests with small synthetic fixtures unless the
  feature genuinely requires real vendor data.

Audit checklist before adding features:

- Does every data row distinguish observation time, bar end time, research download
  time, vendor availability time where known, model cutoff time, and target-open time
  where relevant?
- Do vendor-source, calendar, and contract-metadata outputs remain smoke or schema
  artifacts rather than empirical validation claims?
- Is the OSE futures target clearly labeled as historical licensed research data
  rather than operational data?
- Are local state, credentials, raw data, caches, generated reports, and build outputs
  excluded from version control?
- Does the documented verification workflow pass before claims are promoted?
- Are tests labeled honestly as unit, schema, smoke, or real-data checks?
- Are rule-based contract metadata and exchange-calendar outputs clearly labeled as
  scaffolding that requires vendor reconciliation?
- Is any claim about model performance, VaR/ES calibration, or hedge usefulness
  unsupported by current artifacts?

Current implementation status:

- The main data-engineering path is implemented: source probes, cache-first reads,
  durable modeling-panel artifacts, calendar mapping, target audit, feature coverage,
  leakage binding, and run-specific reports.
- The baseline benchmark and advanced econometric benchmark layers are implemented behind
  gates. Advanced econometric benchmarks remain nonblocking diagnostics unless sample, stability,
  and author-review gates support stronger use.
- The ML tail path is implemented for direct quantile, location-scale, and standardized
  loss POT-GPD variants over the registered nested information ladder.
- Result governance is implemented for primary ML metrics, per-model diagnostics, result
  matrix artifacts, feature-unavailability diagnostics, paired-loss inference,
  Murphy diagnostics and stress windows.
- Reporting utilities generate manuscript-facing discussion, evidence maps, table
  manifests, and figure galleries from artifacts. These outputs summarize evidence;
  they do not create new empirical evidence.

Research design gates:

- Define forecast origins before ingestion or modeling.
- Define target families before feature engineering or evaluation.
- Treat the U.S.-close-mark residual target as unavailable unless a licensed,
  timestamped intraday Nikkei futures reference mark exists and is available at the
  U.S. cash close.
- Every empirical claim must specify forecast origin, reference price, target family,
  tail side, and information cutoff.
- Treat upper-tail modeling as the right-tail futures risk surface, evaluated under
  the same gates as left-tail downside risk.

Data and feature gates:

- Preserve source, symbol, observation timestamp, bar timestamps, availability
  timestamp, and research download timestamp where relevant.
- Build timestamp-safe U.S. close features only after validating time-zone conversion,
  daylight-saving handling, exchange holidays, early closes, missing sessions, and
  OSE night-session edge cases.
- Include feature blocks only when timestamp validity and sample-coverage gates pass.
- Preserve core lagged Japanese variables, market-structure flags, holiday flags, and
  absorption-timing fields where they are relevant to a forecast origin.
- Maintain a feature-leakage audit proving that every feature is available before the
  model cutoff and that the model cutoff precedes the target open.

Modeling gates:

- Baseline and benchmark metrics should be saved before fitting more flexible models.
- Advanced econometric benchmarks should emit explicit unavailable statuses when
  optimization, filtering, sample size, or ES validity gates fail.
- Score-driven and optimizer-heavy advanced econometric benchmarks should remain appendix or
  diagnostic evidence unless sample gates and author review support stronger use.
- ML tail models must use chronological validation, month-level refits, fixed
  hyperparameter policy, recorded feature hashes, recorded feature drops, and
  training-window diagnostics.
- Direct quantile models remain VaR-only unless a valid ES companion is explicitly
  supplied by the model family.
- Location-scale and POT-GPD variants must use fully out-of-fold standardized losses
  before fitting empirical or EVT tail components.

EVT gates:

- EVT is a tail-calibration layer, not a standalone contribution.
- Fit POT-GPD on timestamp-safe standardized losses as the first reported hybrid
  specification; other EVT interfaces are robustness extensions.
- Never calibrate EVT tails on in-sample fitted standardized residuals.
- Threshold diagnostics should report exceedance counts, mean excess, GPD shape and
  scale, stability across nearby thresholds, selected-threshold flags, and sensitivity
  checks.
- Additional automated EVT threshold-selection procedures are not current-paper
  requirements. Revisit them only if EVT threshold selection becomes a primary
  contribution.
- Enforce a minimum exceedance count before reporting an alpha level.
- Report empirical levels separately from extrapolated levels.
- Evaluate VaR and ES separately and jointly.

Evaluation and manuscript gates:

- Report VaR coverage, exception diagnostics, quantile loss, joint VaR-ES loss for
  valid VaR-ES pairs, ES exceedance severity, tail-ranking diagnostics, and paired-loss
  inference where the sample supports it.
- Murphy diagnostics are diagnostic plots, not standalone significance tests.
- Use the primary ML nested information-set table for the main information-set story. Treat restricted
  cross-family rows as diagnostic or restricted evidence unless common-sample and
  inference gates justify promotion.
- Additional forecast-distribution scoring extensions are not current evidence. Do not
  add them to the current paper unless a later review requires stable definitions,
  artifact schemas, tests, and manuscript wording.
- ES severity is conditional on VaR exceptions and must be reviewed before being
  converted into manuscript prose.
- Do not make trading-alpha, live-deployment, price-discovery, structural-causality,
  or hedge-PnL claims without a separate registered design and evidence layer.

Acceptance criteria:

- The documented verification workflow passes before a change is treated as complete.
- New outputs are either small tracked synthetic fixtures or ignored local artifacts.
- No vendor credentials, raw market data, caches, generated reports, or local build
  artifacts are committed.
- Documentation is updated when behavior, schemas, workflow entrypoints, or claim
  boundaries change.
- Claims are labeled honestly: schema checks, smoke checks, and real-data validation
  are not interchangeable.
- Any unavailable target or benchmark is explicitly marked as unavailable or deferred
  with a reason.

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

Use current repository evidence when giving file or line references. Do not propose
new model work until the target-data audit gate is satisfied.
```
