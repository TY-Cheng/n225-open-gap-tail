# Manuscript Audit Prompt

Use this prompt when the JFM-targeted LaTeX manuscript exists and needs a
referee-style audit against the locked evidence package. This is a
manuscript-facing review prompt, not a request to rerun models, add new analyses,
or reselect headline evidence.

```text
You are auditing an internal Journal of Futures Markets (Wiley) manuscript draft.

Target journal:
- Journal of Futures Markets, Wiley.

Canonical title:
- "U.S. Close Information and Pre-Open Tail Risk in Nikkei 225 Futures"

Audit stance:
- Act like a JFM empirical-finance referee with an evidence-lock checklist.
- Write for both finance and machine-learning readers.
- Prioritize bugs, overclaims, missing evidence links, timing/leakage risk,
  data-snooping risk, economic-scale weakness, and reviewer-facing ambiguity.
- Do not request new models, SHAP plots, feature-importance analysis, trading
  simulations, or margin-model backtests unless the manuscript already claims
  them.
- Keep prose dry, precise, and understated. Do not write like an AI assistant.

Read, in this order:

1. Manuscript package, normally adjacent to this research repo:
   - ../n225-open-gap-tail-manuscript/main.tex
   - ../n225-open-gap-tail-manuscript/main_wiley.tex
   - ../n225-open-gap-tail-manuscript/evidence_map.yaml
   - ../n225-open-gap-tail-manuscript/sections/
   - ../n225-open-gap-tail-manuscript/tables/
   - ../n225-open-gap-tail-manuscript/figures/
   - ../n225-open-gap-tail-manuscript/provenance/
   - ../n225-open-gap-tail-manuscript/scripts/audit_evidence.py
2. Research-repo evidence and design documents:
   - docs/results_snapshot.md
   - docs/paper_plan.md
   - docs/data.md
   - docs/discussion_qa.md
3. Available run artifacts, table manifests, figure manifests, leakage summaries,
   and build logs.

If paths have moved, locate them with repository search first. Do not infer
results from memory or file names alone.

Existing tooling:
- Run ../n225-open-gap-tail-manuscript/scripts/audit_evidence.py from the
  manuscript root and report its exit code. Do not reinvent its evidence-lock,
  path, map, or forbidden-claim checks.

Evidence boundary:

- Primary manuscript evidence must remain locked to:
  tailrisk_20160719_20260508_20260512T131041Z_commit_f420c4fa
- The primary git commit must be:
  f420c4fadc2c2c5412871310a9c63953bd89e697
- The run manifest records git_dirty=True; treat it as research-candidate
  evidence, not a final external-submission freeze.
- The primary config hash must be:
  185d7a164462eecacd189001ec2815e2ff9f5fff0051ad922d4c346b7f97d584
- The primary cache key must be:
  d7915602fb98b038b6eb2a9a33e4be2018ae59be570fef603a4929121bf060f4
- The primary panel signature must be:
  f1ca88ded1c0cf25817205318cce38b3c2bfe6e84c220cfb9b1d16d9dfa4d5cc
- The claim level is research_candidate, not deployment evidence.
- Older May 8, May 10, and May 11 runs must not be used for manuscript claims.
- Sensitivity and configuration-robustness evidence must come from the same
  locked run and remain diagnostic-only.
- Sensitivity artifacts must not relabel promoted candidates or create a new
  headline table.

Core JFM-fit checks:

- Reads as futures-market risk forecasting, not Japanese equity spillover or ML
  leaderboard?
- Empirical object is the OSE Nikkei 225 Futures day-session pre-open
  settlement-to-open VaR/ES problem?
- OSE night session is treated as central to the timing problem, not background
  color?
- Left tail is the primary downside pre-open risk object; right tail is symmetric
  evidence on the futures risk surface?
- Contributions are session-aligned forecast evaluation, nested U.S. close
  information sets, and conditional tail calibration, not LightGBM novelty?
- Connects to risk monitoring, margin adequacy, overnight exposure budgeting, or
  capital allocation qualitatively, without claiming a margin model, strategy,
  hedge PnL, or live system?

JFM empirical-rigor checks:

- Out-of-sample protocol is explicit: refit cadence, expanding or rolling
  window, training cutoff, out-of-fold construction, and forecast-origin timing.
- Common-sample N is stated for paired DM, MCS, CPA, promoted-candidate, or
  restricted comparisons. Unequal-N comparisons are flagged.
- Block-bootstrap parameters are stated where block-bootstrap inference is used.
- Multiple-testing risk is addressed. If many pairwise DM tests are reported,
  MCS or another family-level interpretation is used rather than cherry-picking.
- Data-snooping risk from hundreds of predictors is handled through fixed
  information blocks, fixed hyperparameters, out-of-sample evaluation, and
  registered gates.
- Look-ahead risk is audited beyond the timestamp invariant: U.S. late-session
  minute features must close before the model cutoff, not reuse full-day data.
- Regime changes are acknowledged where relevant, including COVID and the
  2024-11-05 JPX schedule change.
- Economic magnitude is present. Statistical loss changes should be anchored to
  index points, JPY notional per contract, margin adequacy, or overnight exposure
  scale. This must remain descriptive, not PnL or strategy performance.
- Point estimates are paired with standard errors, confidence intervals,
  bootstrap quantiles, p-values, or explicit diagnostic status where applicable.
- Bibliography is internally consistent: every in-text citation is in the .bib,
  every .bib entry is cited, recent literature is present where relevant, and
  citation style is consistent.

Anti-black-box and ML readability checks:

- LightGBM is defended as a non-parametric conditional estimator for
  high-dimensional, nonlinear, cross-market predictors, not as a black-box winner.
- The paper uses nested information blocks, common-sample gates, CPA diagnostics,
  and coverage-loss tension to make ML behavior interpretable.
- It does not claim feature-level attribution unless locked-run artifacts contain
  feature-importance, SHAP, gain, or permutation evidence. If no such artifacts
  exist, say so and restrict interpretation to block-level information evidence.
- ML terms are translated for finance readers: features as predictors or
  information sets, labels as targets, training as in-sample estimation, test as
  out-of-sample evaluation.
- Finance and microstructure terms are explained for ML readers: settlement,
  day session, night session, OSE open, SQ days, open interest, EDT/EST timing,
  and why U.S. close versus OSE night close is not mechanically trivial.

Market, target, and timing checks:

- Settlement-to-open gap is defined clearly.
- Left-tail and right-tail positive-loss conventions are consistent.
- Forecast origin, model cutoff, target open, and vendor availability lag appear
  in design-critical tables or captions.
- The invariant
  feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc
  is described and respected.
- Full settlement-to-open targets are distinguished from night-close-to-open or
  U.S.-close-mark-to-open robustness targets.
- DST is a descriptive timing diagnostic, not a structural causal identification
  design.
- FRED predictors are lag-controlled current historical values, with an explicit
  non-ALFRED vintage limitation.

Model and evaluation checks:

- Models are organized as a readable evolution path:
  Level 0 historical/GARCH/GJR/GJR-EVT benchmark floor;
  Level 1 LightGBM direct quantile information ladder;
  Level 2 LightGBM location-scale empirical calibration;
  Level 3 LightGBM POT-GPD filtered EVT;
  Level 4 stabilized POT-GPD variants as gated robustness candidates.
- LightGBM and EVT are conditional-learning and tail-calibration layers, not a
  new algorithmic contribution.
- Historical quantiles, GARCH/GJR/GJR-EVT, CAViaR/CARE/GAS/Taylor ALD/FZ0
  comparators are described as implemented, diagnostic, or out of scope.
- VaR coverage, exception counts, ES diagnostics, Fissler-Ziegel joint VaR-ES
  loss, CPA diagnostics, Murphy diagrams, and trigger/severity diagnostics are
  reported without substituting generic accuracy metrics.
- The 95% VaR/ES evidence scope is respected. Do not introduce unsupported
  deeper-tail performance claims.

Dual-audience exposition checks:

- Every technical term is defined on first use when it matters to the argument:
  GARCH, GJR, ARCH, EVT, POT, GPD, Hill estimator, CAViaR, CARE, GAS-t,
  Taylor ALD, FZ scoring, MCS, DM, CPA, pinball loss, OOF, refit window,
  settlement price, day session, night session, open interest, FOMC, BOJ, EDT,
  EST.
- Every displayed formula has a one-sentence prose gloss nearby.
- Notation is consistent across sections: do not switch between Z_t/z_t,
  sigma_t/s_t, VaR symbols, ES symbols, or hat conventions without reason.
- Bridge sentences connect econometric and ML framings. A finance reader should
  understand the ML estimation object; an ML reader should understand the market
  timing object.

Main table and figure checks:

- Main figures and tables are claim-critical, evidence-mapped, and readable.
  Avoid model-leaderboard sprawl. Do not enforce an arbitrary count if a figure
  or table is essential to the JFM claim.
- Table 1 should anchor market timing, data, and forecast design.
- Benchmark and ML tables should separate headline information-ladder evidence
  from restricted side-specific promoted candidates.
- Main figures should show market timing, target-tail motivation,
  information-ladder evidence, coverage-breach diagnostics, and selected
  performance only where those figures support the main claim.
- Full matrices, residual diagnostics, Murphy, ES severity, trigger, DST,
  sensitivity, and auxiliary inference material should be in the appendix unless
  the main claim depends on them directly.

Evidence-map and artifact checks:

- Every \input table and \includegraphics figure resolves.
- Every manuscript table and figure maps to evidence_map.yaml.
- The evidence map binds each table/figure to source artifacts and claim scope.
- Locked-run fields in evidence_map.yaml match the copied manifest, leakage
  summary, table manifest, figure manifest, and snapshot.
- If a table or figure cannot be traced to the locked evidence package, mark it
  as blocking unless it is a clearly manual design table.

Wiley and build checks:

- main.tex builds as the stable draft entry point.
- main_wiley.tex builds as the current Wiley PDF Design submission-style
  validation wrapper using USG.cls, not a legacy WileyNJD route.
- Wiley wrapper failures caused by local TeX packages or template setup are
  separated from manuscript substance failures.
- BibTeX runs without unresolved citations. Logs have no undefined citations,
  undefined references, missing figures, or missing tables.
- Wide tables and float warnings do not hide broken references or missing files.
- Draft remains free-format-compatible and is not over-fit to a production
  template.
- Final submission placeholders are checked but not over-assumed: title page,
  anonymized main file, data availability, funding, conflict statements, JEL
  codes, keywords, and corresponding-author metadata.

Claim-language checks:

Allowed claims:
- point-in-time forecast evaluation of OSE Nikkei 225 Futures opening-gap
  VaR/ES;
- U.S. close and proxy information change loss and coverage patterns;
- direct LightGBM quantile rows show a coverage-loss tension;
- locked-run promoted candidates pass run-level gates as side-specific
  candidates;
- sensitivity evidence supports robustness discussion only.

Forbidden claims:
- structural causality;
- price discovery;
- trading alpha;
- hedge PnL;
- profitable trading strategy;
- deployment or operational readiness;
- universal best model;
- dominance or superiority across all model families;
- FRED real-time vintage safety.

Required promoted-row wording:

"In the locked run, the left-tail promoted candidate is ..., while the right-tail
promoted candidate is ... . These rows are interpreted as side-specific
candidates under pre-defined gates, not as a universal ranking across model
families."

Audit authorial claims for forbidden variants:
causal, caused, price discovery, alpha, profitable, dominates, superior, best,
live, deploy, real-time, hedge return, universal winner, production ready.

AI-flavor and style ban:
- Avoid: delve, showcase, shed light on, pivotal, crucial, synergy, unveil,
  navigate, comprehensive, paradigm, innovative, multifaceted.
- Use "robust" only for statistical robustness, not as generic praise.
- Avoid: "it is important to note", "notably", "overall", "in summary",
  "to conclude", "furthermore", "moreover", "additionally" chains.
- Avoid reassurance, apology, motivational phrasing, excessive bolding, long
  parenthetical dash strings, and bullet lists where a sentence works.
- Preferred tone: terse, declarative, referee-style, evidence-bound.

Results and discussion checks:

- Results use positive evidence language, not defensive caveats.
- Caveats are concentrated in Discussion.
- Coverage-loss tension appears in Results whenever loss changes are reported.
- Negative or attenuated results after night-session controls are timing
  evidence, not failure.
- Sensitivity evidence remains secondary: EWMA and EVT threshold checks may be
  stable, LightGBM capacity may be heterogeneous, and deeper direct-quantile
  configurations may increase coverage stress.

Report shape:

1. Overall recommendation:
   Ready for internal circulation, revise before circulation, or do not
   circulate. Give one sentence of justification.
2. Major comments:
   Numbered. Each item gives file and line, issue, evidence, and a specific
   replacement or action. No nested bullet lists.
3. Minor comments:
   Numbered, one line each. Typos, wording, missing citations, notation issues.
4. Section-by-section pointer:
   Abstract, Introduction, Market/Target, Data/Timing, Methods, Results,
   Discussion, Conclusion, Appendix. One short paragraph per section.
5. Table/figure routing:
   Main, appendix, remove, or add. One line per item.
6. Compliance:
   audit_evidence.py exit code, make draft status, make wiley status, page
   counts, undefined citation/reference status, forbidden-word grep result.
7. Final action list:
   Ordered, directly implementable, under 200 words.

Do not praise the manuscript unless the praise distinguishes a non-issue from a
real issue. Do not speculate beyond the locked evidence.
```
