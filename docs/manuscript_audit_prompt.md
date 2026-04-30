# Manuscript Audit Prompt

Use this prompt when the LaTeX manuscript exists and needs to be checked against the evidence.

```text
You are auditing the manuscript for:

"The Incremental Content of U.S. Close Information for Pre-Open Downside Tail Risk: Evidence from OSE Nikkei 225 Futures."

Read:

1. docs/results_snapshot.md
2. docs/paper_plan.md
3. docs/data.md
4. the manuscript source in the manuscript repository
5. available tables, figures, and report artifacts

Audit the manuscript as a journal referee would.

Check:

- Does the paper describe the empirical object as OSE Nikkei 225 Futures day-session pre-open downside tail risk, not generic Japanese equity overnight spillover?
- Does it explain that OSE futures have a night session and that U.S. close information may already be partly reflected before the day-session open?
- Does every empirical table state forecast origin, target family, reference price, and information cutoff?
- Does the paper distinguish full opening-gap targets from residual night-close or U.S.-close-mark targets?
- Are J-Quants, Massive, FRED, calendar, and contract metadata roles described accurately?
- Are FRED VIX and rates variables labeled as historical predictors rather than live production inputs?
- Are rule-based contract metadata and calendar outputs reconciled or clearly marked as scaffolding?
- Are LightGBM and EVT described as conditional-learning and tail-calibration layers, not as an algorithmic novelty claim?
- Are GARCH-EVT, CAViaR, historical quantiles, LightGBM-only, and VaR-ES benchmarks treated as peer comparators where feasible?
- Are VaR coverage, ES diagnostics, joint VaR-ES scoring, and tail-ranking metrics reported without substituting generic accuracy measures?
- Are hedge-trigger results framed as risk-management diagnostics, not trading alpha?
- Are negative or attenuated results after night-session controls interpreted as informative rather than as failure?

Report:

1. Overclaims.
2. Missing identification controls.
3. Missing benchmark comparability.
4. Data-availability or leakage risks.
5. Tables or figures needed before circulation.
6. Recommended wording changes.

Keep the critique direct, evidence-based, and manuscript-facing.
```
