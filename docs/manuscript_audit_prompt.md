# Manuscript Audit Prompt

Use this prompt when the JFM-targeted LaTeX manuscript exists and needs to be
checked against the locked evidence package. This is a manuscript-facing audit,
not a request to rerun models, add new analyses, or reselect headline evidence.

```text
You are auditing an internal Journal of Futures Markets (Wiley) manuscript draft.

Target journal:
- Journal of Futures Markets, Wiley.

Canonical title:
- "U.S. Close Information and Pre-Open Tail Risk in Nikkei 225 Futures"

Audit stance:
- Act like a JFM empirical-finance referee with an evidence-lock checklist.
- Treat the manuscript as a submission-style internal draft, not a final Wiley
  production package.
- Prioritize bugs, overclaims, missing evidence links, timing/leakage risk, and
  reviewer-facing weaknesses.
- Do not request new models, SHAP plots, feature-importance analysis, trading
  simulations, or margin-model backtests unless the current manuscript already
  claims them.

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

If these paths have moved, locate them with repository search first. Do not infer
results from memory or from file names alone.

Evidence boundary:

- Primary manuscript evidence must remain locked to the current clean committed run:
  tailrisk_20160719_20260508_20260511T152225Z_commit_2b473c4e
- The primary git commit must be:
  2b473c4e177fb9776ba0710411bf990513cd701d
- The primary config hash must be:
  185d7a164462eecacd189001ec2815e2ff9f5fff0051ad922d4c346b7f97d584
- The primary cache key must be:
  f45fadd6303d9b50e4356b421024bfffda9766558cfd0464a6628cba7758427b
- The primary panel signature must be:
  63ea2acb4baad92e9cb757fc661e47e8852e1f9b7ef78714a2a8eb564417da13
- The claim level is research_candidate, not deployment evidence.
- Older May 8, May 10, and dirty May 11 runs must not be used for manuscript claims.
- Appendix configuration-robustness evidence must come from the same locked run and
  may be used only as secondary diagnostic evidence.
- Sensitivity artifacts must not relabel promoted candidates or create a new headline
  table.

Core JFM-fit checks:

- Does the paper read as a futures-market risk-forecasting paper rather than a
  generic Japanese equity spillover or machine-learning leaderboard paper?
- Is the empirical object the OSE Nikkei 225 Futures day-session pre-open
  opening-gap VaR/ES problem?
- Does the introduction explain why the OSE night session makes U.S. close
  information nontrivial rather than mechanically obvious?
- Is the left tail presented as the primary downside pre-open risk object, with
  the right tail used as symmetric evidence on the futures risk surface?
- Does the paper connect the evidence to risk monitoring, clearinghouse-style
  margin concern, and capital-efficiency motivation qualitatively, without
  claiming a margin model or trading strategy?
- Are the contributions stated as session-aligned forecast evaluation, nested
  U.S. close information sets, and conditional tail calibration rather than as
  LightGBM algorithmic novelty?

Market, target, and timing checks:

- Does the manuscript define the settlement-to-open gap clearly?
- Are left-tail and right-tail positive-loss conventions stated consistently?
- Are forecast origin, model cutoff, target open, and vendor availability lag
  stated in every design-critical table or caption?
- Is the invariant
  feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc
  described and respected?
- Does the manuscript distinguish full settlement-to-open targets from
  night-close-to-open or U.S.-close-mark-to-open robustness targets?
- Is DST interpreted as a descriptive timing diagnostic, not a structural causal
  identification design?
- Are FRED predictors described as lag-controlled historical predictors, with an
  explicit non-ALFRED vintage limitation?

Data-source checks:

- Are J-Quants, Massive, FRED, Cboe, calendar, contract metadata, option-state,
  and proxy-market roles described accurately?
- Are source availability, event timestamps, target timestamps, and cutoff
  timestamps separated?
- Are rule-based calendar or contract metadata outputs either reconciled with run
  artifacts or clearly labeled as design scaffolding?
- Are same-target-date option rows excluded or clearly controlled where relevant?

Model and evaluation checks:

- Are models organized as an evolution path:
  Level 0 historical/GARCH/GJR/GJR-EVT benchmark floor;
  Level 1 LightGBM direct quantile information ladder;
  Level 2 LightGBM location-scale empirical calibration;
  Level 3 LightGBM POT-GPD filtered EVT;
  Level 4 stabilized POT-GPD variants as gated robustness candidates?
- Are LightGBM and EVT described as conditional-learning and tail-calibration
  layers, not as a new algorithmic contribution?
- Are historical quantiles, GARCH/GJR/GJR-EVT, CAViaR/CARE/GAS/Taylor-style
  comparators handled honestly as implemented, deferred, or out of scope?
- Are VaR coverage, exception counts, ES diagnostics, Fissler-Ziegel joint
  VaR-ES loss, CPA diagnostics, Murphy diagrams, and trigger/severity diagnostics
  reported without substituting generic accuracy metrics?
- Is the 95% VaR/ES scope respected without adding unsupported tail claims?

Main table and figure checks:

- Does the main text stay focused on at most three tables and three figures?
- Table 1 should be a compact market timing, data, and forecast-design table.
- Table 2 should summarize the benchmark floor without becoming a full matrix.
- Table 3 should separate the headline information ladder from restricted
  side-specific promoted candidate rows.
- Figure 1 should motivate the target tail behavior, preferably with log survival.
- Figure 2 should show left/right coverage-breach diagnostics.
- Figure 3 should support the selected-model or performance narrative without
  turning the paper into a model leaderboard.
- Full matrices, EVT residual diagnostics, Murphy, ES severity, trigger, DST, and
  sensitivity material should be in the appendix unless the main claim depends on
  them directly.

Evidence-map and artifact checks:

- Every \input table and \includegraphics figure must resolve.
- Every manuscript table and figure must map to evidence_map.yaml.
- The evidence map must bind each table/figure to source artifacts and claim scope.
- The locked run fields in evidence_map.yaml must match the copied manifest,
  leakage summary, table manifest, figure manifest, and snapshot.
- The sensitivity tables must map to the May 11 secondary sensitivity artifacts
  and remain diagnostic-only.
- If a table or figure cannot be traced to the locked evidence package, mark it as
  a blocking issue unless it is a clearly manual design table.

Wiley and build checks:

- main.tex should build as the stable draft entry point.
- main_wiley.tex should build as a WileyNJDv5 submission-style validation wrapper.
- Wiley wrapper failures caused by missing local packages such as soul,
  mathastext, varwidth, footmisc, or helvetic should be separated from manuscript
  substance failures.
- Check that the bibliography is internally consistent and that BibTeX runs
  without unresolved citations.
- Check that Wiley/NJD warnings, wide tables, and float warnings do not hide
  missing figures, missing tables, or broken references.
- Confirm that the draft remains an internal free-format-compatible manuscript,
  not an overfit production-template exercise.
- Check whether final submission would need separate title page, anonymized main
  file, data availability statement, funding/conflict statements, or journal-level
  metadata, but do not assume those requirements are settled until the live JFM
  author guidelines are checked.

Claim-language checks:

Allowed claims:
- point-in-time forecast evaluation of OSE Nikkei 225 Futures opening-gap VaR/ES;
- U.S. close and proxy information change loss and coverage patterns;
- direct LightGBM quantile rows show a coverage-loss tension;
- locked-run promoted candidates pass run-level gates as side-specific candidates;
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

Audit for forbidden variants, including:
causal, caused, price discovery, alpha, profitable, dominates, superior, best,
live, deploy, real-time, hedge return, universal winner, production ready.

Results and discussion checks:

- Results should use positive evidence language rather than defensive caveats.
- Caveats should be concentrated in Discussion.
- Coverage-loss tension should be explicit and honest.
- Negative or attenuated results after night-session controls should be treated
  as informative timing evidence, not as failure.
- Sensitivity evidence should be described as secondary support: EWMA and EVT
  threshold checks mostly stable, LightGBM capacity more heterogeneous, deeper
  direct-quantile configurations often increasing coverage stress.

Report format:

1. Verdict:
   - Ready for internal circulation;
   - revision needed before circulation; or
   - do not circulate.
2. Blocking findings:
   - Give file, line, table, figure, or artifact references.
3. JFM fit findings:
   - Explain whether the paper reads like a JFM futures risk paper.
4. Wiley/build findings:
   - Separate manuscript failures from local TeX/package issues.
5. Evidence-lock findings:
   - Identify any table, figure, claim, or sensitivity result not mapped to the
     locked evidence package.
6. Claim-boundary findings:
   - List any overclaims and give exact replacement wording.
7. Section-by-section revision notes:
   - Abstract, Introduction, Market/Target, Data/Timing, Methods, Results,
     Discussion, Conclusion, Appendix.
8. Table/figure routing:
   - Say what should stay main text, move to appendix, or be removed.
9. Final action list:
   - Keep it short, ordered, and directly implementable.

Keep the critique direct, evidence-based, manuscript-facing, and reviewer-aware.
Do not praise the manuscript unless the praise helps distinguish a non-issue from
a real revision need.
```
