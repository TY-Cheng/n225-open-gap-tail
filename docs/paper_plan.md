---
hide:
  - navigation
---

# Paper Plan

Updated 2026-09-21. This is the current research design and evaluation contract,
not a chronological grill log. Results and their provenance are maintained in
[Results Snapshot](results_snapshot.md); superseded decisions remain in Git history.

Working title: **U.S. Close Information and Pre-Open Tail Risk in OSE Nikkei 225 Futures**.

## Research scope

The current locked run evaluates only `full_gap_settle_to_open`: next OSE
day-session log open minus previous settlement. Left-tail loss is minus this
gap; right-tail loss is the gap. Losses and forecasts are signed, not clamped.
Forecast inputs must be available by the matched NYSE close plus the declared
availability lag, before the OSE day-session open. Source and timing details
remain in [Data](data.md); training and expanding-OOF design remain in the
repository README.

The research asks whether a LightGBM center/spread filter with tail calibration
can provide usable VaR/ES forecasts across A–D and both tails, and whether
U.S.-close information adds predictive content beyond domestic history.
The latter question requires separate information-increment evidence; a global
model ranking alone does not establish it. The close-to-open and night-close-to-open target variants remain deferred
as forecasting extensions, even where their values are retained for audit.
A residual U.S.-close-mark target requires licensed timestamped OSE futures marks.

No structural causal-spillover, price-discovery, trading-profit or deployment
claim follows from this evaluation. LightGBM–EVT is a model combination, not a
new learning algorithm; left/right risk mechanisms need not be identical.

## Body, tail and training design

The experiment has 22 ML specifications: seven center/spread recipes, each with
empirical, POT-GPD MLE and UniBM tail calibration, plus direct quantile LightGBM.

| Center | Spread construction |
|---|---|
| Mean | log-absolute residual |
| Median | MAD |
| Median | IQR |
| Huber | log-absolute residual |
| Mean | RMS with L2 objective |
| Mean | RMS with Poisson objective |
| Mean | RMS with Gamma objective |

MAD and IQR use their consistency factors; they are not untreated raw scales.
The working hypothesis is that flexible body estimation can exploit relatively
rich central observations while EVT supplies a parsimonious tail extrapolation.
This is a hypothesis to assess, not a guarantee that either ML or EVT will win.
The empirical-tail and direct-quantile models remain controls, not omitted losers.

- Outer evaluation uses monthly expanding-history refits and subsequent OOS forecasts.
- Inner calibration uses five expanding validation blocks, initial training size
  250 and block size `ceil((N_common - 250) / 5)`. No random folds or in-sample
  residual substitution.
- For each component, candidate losses are pooled by observation within scenario,
  then averaged equally across A–D and both tails. Select shared parameters once
  per outer training window, not separately by scenario or inner fold.
- Retain the selected center's OOF errors for spread fitting. Spread folds require
  250 earlier structurally available center errors. Calibrate the tails on
  standardized OOF residuals; final center/spread refits do not replace these
  calibration residuals with in-sample fits.
- Parameter selection uses all of the outer training window. The OOF predictions
  are held out of their fitted trees, but are not a strict historical replay of
  hyperparameter selection or an independent calibration holdout.
- The bounded search uses six capacity profiles and 79/139/199 tree prefixes,
  fitted once up to 199 rounds per candidate/fold/scenario. Maximum depth is 17.
  Parameters are shared across all eight scenarios, not necessarily across months.
- Predictors require 97% finite coverage in each training window. Training uses
  decimal losses. The ML EVT shape upper bound is 0.99; downstream scale, VaR
  and ES use the resulting final parameter pair.
- Twelve external candidates are fitted on the same panel, with native model
  histories and availability retained. Their two tail series are not eight
  independent forecasts.

A–D add information in this order: Japan-only history; U.S.-close core variables;
U.S.-traded Japan proxies; Asia proxies. Current-target-night OSE price paths are
not an assumed observed input merely because lagged night-session fields exist.
Detailed source/timing contracts remain in [Data](data.md); operational search
limits and commands remain in the repository README.

## Manuscript structure and remaining evidence

1. **Introduction:** motivate pre-open VaR/ES risk and state the body/tail hypothesis
   and practical robust-satisficing objective.
2. **Institutional setting and data:** define settlement-to-open losses, OSE/NYSE
   session matching, cutoff availability, contract/sample exclusions and A–D.
3. **Methods:** describe external models, center/spread construction, expanding OOF,
   tail calibration and the distinct training/evaluation units.
4. **Evaluation:** state native gates, global external-reference selection,
   joint common dates, FZG/QL aggregation, paired tests and FZG-only MCS.
5. **Results:** present availability and all-candidate gates before the admitted
   comparison; then global scores, pairwise evidence, MCS, matched information
   contrasts and GREM sensitivity.
6. **Discussion:** distinguish minimum-risk requirements from comparative accuracy,
   identify scenario trade-offs and disclose selection/dependence limitations.
7. **Conclusion:** state supported findings without asserting a unique universal
   winner, causal information transmission or a trading/deployment benefit.

The current [Results Snapshot](results_snapshot.md) includes both the global
comparison and a separate matched information-increment analysis for the two
admitted ML recipes. The incremental evidence is recipe- and score-specific,
not a universal U.S.-information effect. Sample, timing and target-tail motivation
figures must still be tied to the current run rather than relabelled from older
outputs. Residual-risk targets, intraday OSE extensions and extra model families
remain separate work.

## Admission, before ranking

- Use each scenario's native valid VaR dates for Kupiec and Christoffersen
  independence tests: at least 450 observations and both p-values >= 0.05.
  Retain breach rates descriptively; the old 2.5%–7.5% band is not a gate.
- Add the existing ES-GREM (VaR is an auxiliary input), with W=500: at least
  450 eligible observations, an assessable complete native monitoring sequence,
  and running maximum strictly below 20. An earlier crossing cannot be erased
  by later recovery. Missing or unauditable monitoring is not a pass.
- Preserve native chronology, original initialization, cutoff-audited no-bets,
  and no capital resets. W=250 is sensitivity only, not an additional gate.
- An ML recipe must pass all eight A/B/C/D x left/right scenarios. External
  models have two distinct tail scenarios, not eight independent tests.
- These are practical robust-satisficing requirements. No recipe-level 5%
  error guarantee or proof of calibration is claimed. Insufficient exposure
  is not assessable, not evidence of statistical rejection.

## Score, reference and shared dates

- Primary: published logistic FZG, with G1(x)=x, G2(x)=sigmoid(x), and
  its primitive softplus(x), including the forecast-independent log(2)
  constant. Apply the lower-tail formula to (-100 L, -100 VaR, -100 ES).
  Percentage-point conversion is evaluation-only, never a training change.
- Explicitly, with Y=100L, Q=100VaR, E=100ES, a=1-p and h=max(Y-Q,0),
  FZG = h + a Q + sigmoid(-E) (Q-E+h/a) - softplus(-E) + log(2).
  This expanded convention differs from equation (2) of Fissler et al. by
  a term depending only on the realization, so paired differences and rankings
  on the fixed common sample are unchanged. It is not unit-invariant.
- Require finite coherent pairs ES >= VaR, but **do not require ES > 0**.
  GREM retains its own stricter ES > VaR input domain.
- Secondary: quantile loss, also evaluated in percentage-point units.
- From the 12 registered external candidates, retain those passing both tails.
  On one external-only joint common-date panel, equally average the two tail
  FZG scores and select one global reference. Freeze it before inspecting ML
  availability. Exact selection ties use registered roster order and are reported.
- Main roster: every globally admitted ML recipe plus that selected reference.
  Use one fixed joint common-date panel across all roster members and all eight
  scenarios for FZG, QL, paired tests and MCS. External forecasts are reused
  across A–D, not counted as independent observations.
- First average eight scenarios equally within each date, then average dates
  equally. No stacked 8N independence assumption, dynamic weights, candidate
  deletion or reference reselection to enlarge the intersection.
- Retain native availability and exact common-date/missingness reports. If no
  external is admitted, report reference unavailable rather than substitute a
  failed model or historical winner. Zero/one candidates do not establish
  comparative superiority.

## Paired inference and MCS

- All unordered pairs, including ML–ML: delta = mean(score_i - score_j), so
  negative favors i. Two-sided centered circular-block-bootstrap mean tests;
  plus-one Monte Carlo p-values, raw and Holm-adjusted within each score family.
- Report pointwise 95% basic bootstrap intervals using the same joint draws.
  They are not simultaneous intervals; multiplicity conclusions use Holm.
  FZG is the primary family; QL is secondary, with separate adjustment and no
  combined-family 5% guarantee.
- Resample shared date indices for every model on the original target-session
  span, together with the common availability mask. Use ratio means, not
  zero-imputed losses. The estimand is performance on jointly eligible dates,
  not an estimate of unobserved-date performance.
- B=9999, seed=225; b=max(5, round(N_common**(1/3))). Sensitivity uses
  max(5, round(b/2)) and 2b. Report all distinct lengths; do not pick the most
  significant configuration. No additional bootstrap families or nested bootstrap.
- Paired inference requires N_common >= 120 and >=5 distinct exception dates
  for that pair: any breach by either model in any scenario counts the date
  once. MCS requires every pair to meet those floors; otherwise mark the whole
  inference unavailable without evicting roster members. Floors are operational
  reporting policies, not power or validity theorems.
- MCS: FZG only, T_R statistic/elimination, nominal 95%. Reuse joint draws
  throughout elimination. No QL MCS, ranking vote or FZG/GREM composite.
- Preserve exact observational ties. Degenerate nonzero constant differences
  must not be turned into strong significance by adding jitter or flooring
  variances. Report unavailable/degenerate inference explicitly.

## Matched baseline and information contrasts

- Inherit the frozen admitted ML roster, selected GJR reference and all 628 main
  common dates; do not retrain, recompute gates, reselect the reference or shrink
  the sample separately for a contrast.
- Score each tail separately, average the two tails within each information
  set/date, then average dates. Unlike the global comparison, do not average A–D
  before constructing contrasts.
- For each of IQR and Gamma, test A−GJR, B−A, C−B and D−C: eight predeclared
  contrasts. A−GJR compares both model and information configuration; the other
  three are within-recipe information increments. GJR has only one two-tail
  forecast series, not four distinct information sets.
- Reuse the signed percentage-point FZG score and joint calendar-mask CBB:
  two-sided centered tests, 9999 draws, seed 225, main b=9 and sensitivity b=5/18.
  Apply Holm jointly to all eight FZG contrasts within each block configuration;
  QL is a separate eight-contrast secondary family. Keep the existing global
  three-pair family separate; no combined-family 5% guarantee is asserted.
- Use pointwise 95% basic intervals, not simultaneous intervals. Retain the
  N>=120 and five distinct exception-date reporting floors, with exceptions
  counted once per date across the two tails of the two compared configurations.
  Do not condition later contrasts on earlier significance, and do not add MCS.
- B−A adds the **U.S.-close information bundle**, including calendar, U.S.
  equity/late-session, FRED, credit and FX/cross-asset variables. It does not
  isolate U.S. equities or test information beyond contemporaneous OSE night
  prices. Score differences telescope on the shared dates; p-values do not.
- The command `information-contrasts --evaluation-dir <frozen-evaluation>
  --output-dir <new-directory>` exports daily/mean scores, all paired results,
  a compact report and one two-panel FZG figure: A–D sample means with pointwise
  95% main-block CIs (one shared band for GJR), plus paired CIs and Holm-adjusted
  p-values. `mean_intervals.parquet` records the nine FZG-level intervals, using
  the same joint native-calendar mask, b=9, 9999 draws and seed 225 for this run.
  Source hashes and reconstruction of
  the original global daily scores are checked. Full local evidence lives in
  `artifacts/information_contrasts_20260921`; no new archive document is required.

## Frozen paper figure/table bundle

`paper-bundle` assembles existing evaluation and information-contrast outputs
into `artifacts/paper_bundle_20260921`, with PNG/PDF figures, CSV/LaTeX tables,
captions and source/output hashes. It does not refit models, rescore forecasts,
rerun inference, change admission or select a new reference.

The designated paper bundle is the manuscript figure/table entrypoint for
`n225-open-gap-tail-manuscript`, including future revisions. Keep evaluation,
information-contrast and paper-bundle directories separate; do not assemble
manuscript figures ad hoc from upstream exports. The manuscript's older
`reports/runs` synchronization workflow must be adapted to this entrypoint
before use; that manuscript-side change is not part of this cleanup.

- Sample availability and event-based forecast timing, keeping native,
  external-selection and main-comparison date populations distinct.
- All 22 ML recipes and 12 external models, with failed and unassessable
  scenarios distinguished; external models have two tails, not eight replications.
- Three-model global FZG/QL comparison, stored paired intervals/Holm tests and
  FZG-only MCS, without inventing new uncertainty intervals for aggregate means.
- Existing information-increment figure, including mean-level and paired CIs.
- Admitted native GREM paths, W500 main and W250 sensitivity; all-candidate
  summaries remain available in the tables. Neither pooled e-values nor an
  accuracy ranking is constructed.
- Left/right VaR paths use IQR-D, Gamma-D and GJR on the same 628 common
  dates, retaining calendar holes without filling forecasts. D is selected by
  each ML recipe's two-tail mean FZG for illustration only; global paired tests
  and MCS remain the all-scenario comparisons, not D-only inference.
- Raw-target tail motivation uses 2,206 finite `target_clean_sample` rows,
  independently of predictor coverage and forecast eligibility. Distribution,
  conditional-positive survival, mean-excess and Hill plots are descriptive,
  not proof of regular variation or forecast-model validity.

This is an evidence bundle for subsequent manuscript discussion, not a manuscript
revision or a new holdout evaluation. The older bulk Set-C/FZ0 export is not used.

## Interpretation and evidence boundaries

Separate the lowest sample mean, pairwise comparative evidence and the surviving
MCS set. Multiple survivors do not establish equivalence; one admitted candidate
does not establish statistical superiority. GREM is risk-underestimation evidence,
not an accuracy score.

Inference is approximate/exploratory: expanding refits, joint missingness, moments
and dependence require assumptions not established by implementation tests.
Repeated inspection, gate screening and external-reference selection on this OOS
sample are not corrected by Holm or MCS. Do not claim strict end-to-end 95%
coverage. Bootstrap sensitivity does not repair these limitations.

## Sources

- [Fissler, Ziegel and Gneiting, Expected Shortfall is jointly elicitable with Value at Risk](https://arxiv.org/abs/1507.00244).
- [Hansen, Lunde and Nason (2011), The Model Confidence Set](https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Hansen_Lunde_Nason.pdf), including Section 4.3 and footnote 12.
- [MCS bootstrap supplement](https://www.econometricsociety.org/publications/econometrica/2011/03/01/model-confidence-set/supp/5771_tables_0.pdf).
- [arch basic bootstrap confidence intervals](https://arch.readthedocs.io/en/latest/bootstrap/confidence-intervals.html).
- [Wang, Wang and Ziegel, E-backtesting](https://arxiv.org/html/2209.00991v6).

## Implementation verification boundaries

Test public score/inference functions and frozen reevaluation inputs/outputs:
signed ES, sign reflection and units; all-scenario admission and GREM history;
reference independence from ML missingness; shared dates and equal aggregation;
paired orientation/Holm/basic intervals; joint masked draws and complete-series
MCS parity; insufficient/degenerate cases; source immutability. Keep training
and vendor/data acquisition out of these tests.
