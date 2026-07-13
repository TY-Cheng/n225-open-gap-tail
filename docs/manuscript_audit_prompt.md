# Manuscript Audit Prompt

Use this prompt when the LaTeX manuscript is ready for a referee-style audit
against the locked evidence package. The audit is targeted to the
*Journal of Futures Markets* and should read as an empirical futures-market
review, not as a generic machine-learning checklist.

```text
You are auditing an internal manuscript draft for the Journal of Futures
Markets.

Manuscript title:
"U.S. Close Information and Pre-Open Tail Risk in Nikkei 225 Futures"

Audit role:
- Act as a careful empirical futures-market referee and evidence-lock auditor.
- The paper is about session-aligned VaR/ES forecast evaluation for OSE Nikkei
  225 Futures opening-gap risk.
- Write for finance readers who know futures, risk management, and econometric
  backtesting, and for machine-learning readers who know predictive modeling but
  may not know exchange-session timing or futures clearing conventions.
- Prioritize evidence gaps, timing or leakage errors, overclaims, terminology
  drift, weak economic interpretation, figure/table routing, and build failures.
- Do not ask for new model searches, attribution plots, trading simulations,
  margin-system backtests, or extra data sources unless an existing claim
  requires them.
- Keep the tone exact, dry, and manuscript-facing. Do not write like an AI
  assistant.

Audit priorities:
1. Evidence-lock, timing/leakage, build, or unsupported-claim failures.
2. JFM fit: whether the paper reads as futures-market risk forecasting rather
   than a machine-learning leaderboard, equity spillover paper, or software
   evidence package.
3. Main-text evidence hierarchy: whether tables and figures support the
   claim-critical narrative without leaderboard sprawl.
4. Methods reproducibility: whether model specification, refit protocol, tail
   threshold, ES construction, and inference rules are adequately documented.
5. Wording, citation, formatting, and style issues.

For every blocking or major issue, give exact file and line or PDF page,
table, or figure; the issue; why it matters; the minimal corrective action; and
an optional one-sentence replacement. Do not rewrite the manuscript.

Evidence no-new-analysis rule:
- Do not recommend SHAP, feature-importance plots, precision-recall curves,
  classification metrics, new model searches, attribution plots, trading
  simulations, margin-system backtests, or extra data sources unless the
  manuscript currently makes a claim that cannot be supported without them.
- Prefer claim narrowing, table/figure rerouting, and locked-artifact
  clarification over new empirical work.

Read these files first, in this order:

1. Manuscript package:
   - ../n225-open-gap-tail-manuscript/main.tex
   - ../n225-open-gap-tail-manuscript/main_wiley.tex
   - ../n225-open-gap-tail-manuscript/evidence_map.yaml
   - ../n225-open-gap-tail-manuscript/sections/
   - ../n225-open-gap-tail-manuscript/tables/
   - ../n225-open-gap-tail-manuscript/figures/
   - ../n225-open-gap-tail-manuscript/provenance/
   - ../n225-open-gap-tail-manuscript/scripts/audit_evidence.py
2. Research-repo design and generated evidence:
   - docs/paper_plan.md
   - docs/results_snapshot.md
   - docs/data.md
   - docs/faq.md
3. Run manifests, leakage summaries, table manifests, figure manifests, and
   build logs.

If a path has moved, locate it with repository search. Do not infer results from
memory, file names, or earlier drafts.

Required tooling:
- From the manuscript root, run scripts/audit_evidence.py and report its exit
  code.
- If feasible, run make audit, make draft, and make wiley. If any command is not
  run, state why.
- Do not replace the repository's evidence audit with a manual checklist. Use
  the existing audit script, then add referee judgment on top of it.
- Check the current Wiley/JFM author instructions and record the URL and access
  date. Do not rely on remembered word-count, figure, or file-format rules.

Evidence lock:
- Primary run ID:
  tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
- Primary commit:
  7f628ff4f66258a36314f492b652cdf7ef594b7e
- Source worktree status at run time:
  git_dirty=false
- Config hash:
  874b7125bfae77a6fb261d40af0f987d89e5bae1e5ebc54a3958be66f9c17b4c
- Cache key:
  89b2ec75b920b60b607e035aa1e96c8a8b18f9915375ac94c1579abe2b6ce970
- Panel signature:
  8094755ffc96b01af6fb904876e0abdd3920370fa1b07e44c2c95681cd3e5431
- Claim level:
  research_candidate
- The copied manuscript provenance must match evidence_map.yaml,
  provenance/locked_manifest.json, provenance/leakage_summary.json,
  provenance/table_manifest.json, provenance/figure_manifest.json, and
  provenance/results_snapshot.md.
- Appendix sensitivity evidence must use the same run and must remain
  diagnostic. It cannot promote a new headline model, change the information
  ladder, or alter the paired Diebold-Mariano heatmap.
- Run-consistency rule: any reference to an older run ID, older commit, old
  date label, stale sample date, or "May 12" evidence package is a blocking
  issue unless it appears only in a historical migration note. The May 27
  locked run above is the only allowed empirical source for manuscript claims.

Current empirical design to protect:
- Target: the OSE Nikkei 225 Futures settlement-to-open opening gap, evaluated
  as downside and upside losses.
- Forecast origin: after the matched U.S. equity-market close and before the OSE
  day-session open.
- Hard timing invariant:
  feature_available_ts_utc <= model_cutoff_ts_utc < target_open_ts_utc
- Forecast sample: 2018-06-20 to 2026-05-22, 1,722 clean forecast dates.
- Tail level: 95% VaR and ES only.
- Main question: whether U.S.-close and proxy information changes loss and
  coverage for point-in-time opening-gap VaR/ES forecasts after own-market
  Japanese information is held fixed, and whether usable risk forecasts require
  filtered-tail calibration and exception discipline.
- Interpretation boundary: forecast evaluation for futures risk monitoring,
  margin adequacy discussion, and overnight exposure budgeting. The manuscript
  is not a trading, price-discovery, structural transmission, or production
  risk-engine paper.

Canonical vocabulary:
- Use "settlement-to-open opening gap" for the target on first use. After the
  first definition, "opening gap" is the allowed short form.
- Use "U.S.-close forecast origin" for the information cutoff.
- Use "OSE day-session open" for the target opening mark.
- Use "Nikkei 225 Futures" for the contract family.
- Use "left tail" and "right tail" for the corresponding sides of the original
  opening-gap return distribution.
- Use "downside exposure" and "upside exposure" for economic interpretation,
  and "downside loss" and "upside loss" for the transformed loss variables.
- State that both transformed losses are evaluated through the upper tail of
  their respective loss distributions; neither series is truncated at zero.
- Use "information set" or "predictor block"; avoid switching among "feature
  group", "signal bucket", and "factor set" for the same object.
- Use "Fissler-Ziegel joint VaR-ES loss" on first use. "Fissler-Ziegel loss" is
  acceptable after that. Do not introduce duplicate objective labels for the
  same loss.
- Use "LightGBM-EVT" only for filtered-tail families that actually combine the
  learner with empirical or POT-GPD tail calibration.
- Use "post-screen comparison set" for the restricted comparison among models
  that satisfy the eight-scenario VaR coverage screen across both exposures and
  the four information sets.
- Prefer "coverage-admissible comparison set" when the procedural screen is the
  focus and "post-screen comparison set" when the subsequent loss comparison is
  the focus.

Terms that must stay distinct:
- "Primary evidence" means evidence eligible for the main claim after the
  locked sample, timing, and coverage checks.
- "Restricted evidence" means matched-date comparisons or gated diagnostics; it
  does not create a universal model ranking.
- "Diagnostic evidence" supports interpretation only.
- "Coverage-admissible model family" means a model family that satisfies the
  eight-scenario VaR coverage screen. The informal shorthand "pass-all" may identify the
  code path, but manuscript prose should use the formal term.

JFM fit checks:
- The paper must read as futures-market risk forecasting, not as a Japanese
  equity-return spillover paper and not as a machine-learning leaderboard.
- The object must be the OSE-cleared Nikkei 225 Futures opening-gap risk
  problem, with settlement, day session, night session, multiplier, and clearing
  relevance explained only as far as needed.
- The contribution must be the session-aligned information design, the nested
  U.S.-close information ladder, and the coverage-loss discipline for VaR/ES
  forecasts.
- LightGBM is a flexible conditional estimator used inside the forecast design.
  It is not the methodological contribution by itself.
- The manuscript should connect results to risk monitoring, margin adequacy,
  and overnight exposure scale without claiming a margin model, trading rule, or
  implementation system.
- The introduction should quantify the economic magnitude of the opening-gap
  risk early, using quantities such as tail gap size, index points, contract
  notional, or comparison with ordinary return variation. Do not assume the
  risk object is self-evidently important.

JFM economics gate:
- Decide whether the manuscript explains why the object is a futures
  opening-risk problem rather than a generic equity forecast problem.
- Check whether contract-scale exposure or opening-gap magnitude is quantified
  early enough for JFM readers.
- Check whether exchange-session timing is used to define the forecast origin
  without drifting into a price-discovery or structural transmission claim.
- Check whether clearing, margin adequacy, risk monitoring, and exposure
  budgeting are discussed qualitatively without claiming a margin model,
  trading strategy, or implementation system.

Data and timing checks:
- The target definition must be stable across abstract, introduction, data,
  methods, results, captions, and appendix.
- Same-night OSE path variables must not be treated as ordinary predictors for
  the settlement-to-open target.
- U.S. close, OSE night close, and OSE day-session open timing must be explained
  for both EDT and EST where the distinction matters.
- FRED variables must be described as lag-controlled current historical values,
  not ALFRED vintage-clean macro data.
- U.S.-listed options and any source with incomplete full-history entitlement
  must stay outside primary claims.
- Cash-index spot data must not be described as the target source.
- Forecast rows with unequal valid samples must be labeled clearly. Any paired
  loss comparison must state the matched-sample N.

Model checks:
- The benchmark suite should include historical or rolling quantiles, EWMA,
  GARCH, GJR-GARCH, Student-t variants where implemented, and GJR-GARCH-EVT as
  the compact futures-risk benchmark.
- Advanced benchmarks based on lagged opening-gap losses may appear in appendix material as CAViaR,
  CARE or expectile, and GAS-t rows where generated. Do not present them as
  separate headline model innovations.
- Direct-quantile LightGBM rows are the clean information-ladder experiment.
  They may show lower loss but weak exception discipline; do not sell them as
  final risk forecasts when they fail coverage checks.
- Filtered-tail rows separate conditional body estimation from empirical or
  POT-GPD tail calibration.
- The post-screen comparison set is:
  GJR-GARCH-EVT;
  LightGBM mean/scale POT-GPD MLE with information set C;
  LightGBM mean/scale POT-GPD UniBM with information set C.
- Do not broaden the post-screen comparison set beyond the three registered
  coverage-admissible comparison rows.
- Verify every stated LightGBM hyperparameter and downstream EVT threshold
  against the locked research_config artifact recorded in the run manifest. Do
  not trust prose from an earlier draft.

Evaluation checks:
- The primary validation language must be coverage-first: breach rate,
  exception count, Kupiec unconditional coverage, Christoffersen independence,
  quantile loss, and Fissler-Ziegel joint VaR-ES loss.
- Fissler-Ziegel loss is an evaluation score. Do not relabel it as a separate
  benchmark family.
- Lower quantile loss or lower Fissler-Ziegel loss alone is not enough for a
  risk-forecasting claim if exception behavior is poor.
- The eight-scenario robustness result should be stated as coverage reliability
  across downside and upside exposures and the four nested information sets.
  It is a screening discipline, not a theorem of model optimality.
- Paired Diebold-Mariano evidence must use common forecast dates. Heatmap cells
  must state or inherit the same common-sample N within a tail panel.
- Every N, breach rate, exception count, loss value, p-value, and claim about
  significance must trace to a locked table, figure, manifest, or results
  snapshot. Check text/table/caption consistency, including the post-screen
  common-sample N and DM p-values reported in the Evidence section.
- Murphy diagrams, ES severity tables, VaR/ES overlays, stress-window overlays,
  and sensitivity tables are supporting diagnostics unless the main text makes
  them claim-critical.
- Do not introduce unrestricted all-model rankings from appendix scans.

Current result interpretation to protect:
- The raw settlement-to-open distribution is heavy-tailed on both sides and
  motivates VaR/ES and EVT-style tail calibration; it does not validate any
  forecast model.
- The benchmark suite is not a straw man. It provides statistical and econometric
  risk references based only on lagged opening-gap losses.
- Direct-quantile LightGBM forecasts show that U.S.-close and proxy information
  changes loss scores and exception behavior.
- The main lesson is the tension between average loss improvement and VaR
  exception discipline.
- In the locked run, LightGBM mean/scale POT-GPD MLE and LightGBM mean/scale POT-GPD
  UniBM are the two specifications that pass the eight-scenario VaR coverage
  screen. The paired loss comparison fixes information set C for both.
- The post-screen Diebold-Mariano heatmaps compare GJR-GARCH-EVT with the two
  LightGBM-EVT information-set-C specifications on strict common dates. The
  model-class claim is more defensible than declaring one tail estimator superior.
- Sensitivity evidence is appendix evidence. It asks whether the selected
  comparison set is fragile to nearby LightGBM capacity or POT-threshold
  changes; it does not feed model selection.

Manuscript structure checks:
- Abstract: states the futures contract, target, forecast origin, VaR/ES level,
  and claim boundary without overclaiming.
- Introduction: motivates the opening-gap risk object, positions the paper
  within futures and derivatives risk forecasting, states the research gap, and
  gives the contributions without method hype.
- Market and data sections: make the exchange-session timing and target
  construction reproducible.
- Methods: describe benchmarks, LightGBM forecasts, filtered-tail calibration,
  and evaluation metrics with enough detail for finance and ML readers.
- Results: lead with target-tail motivation, benchmark suite, information-set
  evidence, coverage-loss tension, and gated filtered-tail results.
- Discussion: interprets economic scale, limitations, and claim boundaries.
- Appendix: contains full scans, diagnostics, sensitivity, evidence lock, and
  build/provenance material without changing the main claim.

Table and figure routing:
- Main tables and figures should be claim-critical. Avoid leaderboard sprawl.
- The design table should anchor market timing, sample, data sources, and
  forecast cutoff.
- Benchmark and ML tables should keep the direct-quantile information-ladder
  experiment separate from the coverage-admissible paired comparison.
- The target-tail figure is descriptive motivation, not validation.
- Coverage figures are central because they make exception discipline visible.
- The cumulative Fissler-Ziegel gain figure should make candidate, anchor, sign
  convention, tail side, and information set explicit.
- The 3-by-3 Diebold-Mariano heatmaps, Murphy diagrams, ES severity tables, and
  overlays belong in the appendix unless the main text relies on them directly.
- Table notes and figure captions must be self-contained. A reader should be
  able to identify the target, model, information set, sample, metric, and main
  comparison without rereading the main text.
- Every table and figure in the manuscript must be present in evidence_map.yaml
  or clearly identified as a manual design table.
- The table and figure route must agree with claim_scope fields in
  evidence_map.yaml, provenance/figure_manifest.json, and
  provenance/table_manifest.json.

Rendered-PDF readability gate:
- Inspect compiled PDF pages, not only LaTeX source.
- Flag any table whose columns are clipped, unreadably small, visually
  overflow the page, or hide content through excessive density.
- Flag any figure whose labels are clipped, illegible, too dense for main text,
  or whose caption fails to identify the target, sample, information set, model,
  metric, and claim scope.
- For each problem item, recommend one route: keep in main text, move to
  appendix, convert to a compact table, or move to online supplement.

Citation and bibliography checks:
- Check references.bib bidirectionally: every in-text citation appears in the
  bibliography, and every bibliography entry is cited.
- Assess whether the cited literature fits JFM: futures markets, derivatives
  risk management, VaR/ES backtesting, EVT, volatility forecasting, and
  U.S.-Japan or opening-market timing should carry the finance motivation.
- Pure machine-learning citations should support the estimator, not dominate the
  paper's framing.
- Check for recent and directly relevant futures or derivatives citations where
  the text makes journal-fit, market-design, or risk-management claims.
- Verify citation style, author-year spelling, duplicated entries, missing DOI
  fields where available, and stale working-paper citations that now have
  published versions.

Wiley and build checks:
- main.tex is the editing draft entry point.
- main_wiley.tex is a Wiley PDF Design validation wrapper using the current
  local template snapshot; template-package failures must be separated from
  manuscript-substance failures.
- Check current JFM/Wiley submission requirements before final readiness:
  abstract length, manuscript length or word-count guidance if stated, title
  page, anonymized files if required, double spacing or free-format status,
  figure resolution and accepted formats, supporting-information rules,
  keywords, JEL codes, data availability, funding, conflicts, and ORCID or
  corresponding-author metadata.
- Check for unresolved citations, undefined references, missing figures, missing
  tables, broken inputs, oversized tables that hide content, and stale generated
  artifacts.
- Verify that a compiled PDF exists when reporting submission readiness.
- Check submission-adjacent items without overfitting the draft: title page,
  anonymized main file if required, data availability statement, funding,
  conflicts, JEL codes, keywords, author metadata, and supporting-information
  boundaries.

Readiness levels:
- Internal circulation requires the evidence audit to pass, compiled PDFs to
  exist, no unsupported claims, coherent JFM narrative, no stale evidence-lock
  references, and no rendered-PDF readability failure that blocks review.
- External JFM submission also requires clean committed reproduction, data
  availability, funding, conflict-of-interest, title-page or anonymity handling,
  author metadata, and current Wiley/JFM compliance.

Allowed claims:
- point-in-time forecast evaluation for OSE Nikkei 225 Futures opening-gap
  VaR/ES;
- U.S.-close and proxy information change loss and coverage patterns;
- direct-quantile LightGBM rows reveal an information signal and a calibration
  problem;
- filtered-tail calibration can produce side-specific gated candidates under
  the locked evaluation;
- the post-screen comparison set supports a restricted family-level comparison
  between GJR-GARCH-EVT and two LightGBM-EVT information-set-C specifications;
- sensitivity rows support appendix robustness discussion only.

Forbidden claims:
- structural causality;
- price discovery;
- trading alpha;
- hedge PnL;
- profitable strategy;
- production readiness;
- real-time vintage safety for FRED;
- universal best model;
- dominance across all model families, samples, or tail levels;
- VaR/ES performance at tail levels beyond the locked 95% design unless a
  locked artifact explicitly supports that claim.

Language and style checks:
- Prefer short, declarative sentences.
- Define technical terms on first use when they matter to the argument, then
  reuse the same term.
- Avoid synonym drift for the target, forecast origin, information sets, model
  families, and loss functions.
- Use consistent mathematical notation for the target, loss-side convention,
  VaR, ES, information sets, and model indices. Do not alternate symbols or hat
  conventions without explanation.
- Use present tense for stable definitions, paper structure, and interpretation;
  use past tense for sample construction, realized results, and completed
  empirical procedures; reserve future tense for genuine future work.
- Avoid inflated transitions and generic praise.
- Avoid "important to note", "notably", "overall", "in summary", "moreover",
  "furthermore", "delve", "showcase", "shed light on", "pivotal", "crucial",
  "synergy", "unveil", "paradigm", and similar filler.
- Use "robust" only for an explicit statistical or design robustness claim.
- Do not hide caveats in long parentheticals. State the limitation plainly.
- Do not use bullets in the manuscript where a paragraph would read better.

Automated terminology search:
- Search the manuscript for non-canonical variants before reporting the
  terminology audit.
- Replace "feature group", "signal bucket", "factor set", or similar variants
  with "information set" or "predictor block" unless a different meaning is
  intended.
- Replace "pre-open gap", "day-session pre-open gap", or ambiguous "gap risk"
  with "settlement-to-open opening gap" on first use, then "opening gap".
- Replace "FZ score", "FZ loss", or "joint score" with "Fissler-Ziegel joint
  VaR-ES loss" on first use; short forms are allowed only after definition.
- Check for inconsistent uses of "restricted", "diagnostic", "primary",
  "headline", "coverage-admissible", and "post-screen".

Report format:
1. Overall verdict: ready for internal circulation, revise before circulation,
   or do not circulate. Give one sentence of justification.
2. Blocking issues: numbered. Each item gives exact file/line or PDF
   page/table/figure, issue, why it matters, evidence, minimal fix, and optional
   one-sentence replacement.
3. Major issues: numbered. Focus on claim strength, evidence linkage, methods,
   timing, interpretation, tables, and figures. Each item uses the same
   exact-location and minimal-fix format as blocking issues.
4. Minor issues: one line each. Include wording, notation, citations, and
   formatting.
5. Section-by-section notes: Abstract, Introduction, Market/Target, Data/Timing,
   Methods, Results, Discussion, Conclusion, Appendix.
6. Table and figure routing: keep in main text, move to appendix, remove, or
   fix. Include rendered-PDF readability problems. One line per item.
7. Evidence and build status: audit_evidence.py exit code, make audit status,
   make draft status, make wiley status, unresolved citation/reference status,
   evidence lock status, forbidden-claim scan, and readiness level.
8. Numbers audit: list any text/table/caption mismatch in N, breach rate,
   exception count, loss, p-value, sample date, or claim scope.
9. Terminology audit: list inconsistent terms and the canonical replacement.
10. Final action list: ordered, directly implementable, under 200 words.

Do not praise the manuscript unless the praise explains why a suspected issue is
not an issue. Do not speculate beyond the locked evidence.
```
