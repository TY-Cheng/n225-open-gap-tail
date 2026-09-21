---
hide:
  - navigation
---

# FAQ

Current reader-facing summary, 2026-09-21. See the [Paper Plan](paper_plan.md)
for the design and [Results Snapshot](results_snapshot.md) for numerical evidence.
Run-generated historical FAQs remain with their own artifacts, not on this page.

## What is the paper asking?

Can a LightGBM center/spread filter combined with tail calibration produce useful
Nikkei 225 futures VaR/ES forecasts across sparse and rich information sets and
both tails? A related question is whether U.S.-close information adds predictive
content beyond Japanese history. A global model comparison alone cannot answer
that incremental-information question.

## What is the target?

The current run forecasts `full_gap_settle_to_open`:
`log(next OSE day-session open) - log(previous settlement)`.
Left-tail loss is minus this gap; right-tail loss is the gap. An exception is
`realized_loss > VaR`. The primary level is 95%, with nominal exception rate 5%.

Losses, VaR and ES are signed. Negative ES is not automatically invalid:
joint scoring requires finite ES >= VaR. FZG handles this domain; FZ0 does not
handle nonpositive ES. GREM separately requires ES > VaR.
Close-to-open, night-close-to-open and a latest-mark residual-risk forecast
are not substitutes for the current target.

## Why study the full gap when OSE has a night session?

The forecast is a late update to a settlement-anchored loss, not a claim that
the entire loss accrues after the cutoff. Night trading makes the economic
information question more demanding: offshore information may already be
incorporated in OSE prices. Contemporaneous target-date OSE marks and a separate
residual-risk target require their own timestamped data and design.

## What data enter the forecasts?

A–D add Japan-only history, U.S.-close core variables, Japan proxy ETFs and Asia
proxy ETFs in that order. External benchmarks use target-loss histories.
All predictors must satisfy the point-in-time availability cutoff, normally the
matched NYSE close plus the declared 15-minute availability lag, before the next
OSE day-session open. Lagged OSE night-session fields do not mean that the
contemporaneous target-date night path is included.

[Data](data.md) gives source roles, release timing, roll/SQ exclusions and
missingness rules. FRED inputs are not a verified ALFRED real-time-vintage panel;
conservative lags alone do not establish vintage safety.

## How are models trained and tuned?

There are 22 ML specifications: seven bodies × empirical/POT-MLE/UniBM tails,
plus direct quantile; there are 12 external candidates.
Monthly outer expanding-history tests remain separate from training.
Inner expanding OOF supplies center/spread residuals and bounded candidate
selection. Parameters are shared across A–D and both tails within each refit,
but may change between months. Six capacity profiles and 79/139/199 tree prefixes
are evaluated without a separate continuous early-stopping search.

OOF points are held out of their fitted trees; selecting parameters over the
whole outer training history is not strict historical hyperparameter replay.
External models fit their own distributional/dynamic parameters where required.
The paper is not a contest to maximize every model's individual tuning budget.

## How do the body and tail stages differ?

LightGBM estimates a conditional center and spread; standardized OOF residuals
provide the tail-calibration sample. Empirical tails are matched controls.
POT-MLE fits a generalized Pareto tail; UniBM supplies an alternative shape
estimate. The POT threshold is 0.90, distinct from the reported 0.95 VaR level.
The ML shape upper bound is 0.99. This combination is not a new learning algorithm,
nor is superiority of EVT or UniBM guaranteed.

## What does robust-satisficing mean here?

A recipe must pass every A–D/left–right scenario, not merely pass on average.
Native gates require N >= 450, Kupiec p >= 0.05, Christoffersen independence
p >= 0.05, and an assessable W500 ES-GREM sequence with at least 450 eligible
observations and historical maximum below 20. External models must pass both
distinct tails. Breach rates remain descriptive; the fixed band is not a gate.

No recipe-level 5% guarantee or proof of calibration follows from this practical
screen. W250 GREM is sensitivity only. An earlier alarm cannot be erased by a
later fall in cumulative evidence.

## How are admitted models compared?

Select one external reference by average two-tail FZG on external-only common
dates. Then fix the roster and one shared panel across every admitted ML model,
the reference and all eight scenarios. Average equally within date, then across
dates. This is a global deployment objective, not an assumption that left/right
risk mechanisms are identical.

FZG is primary and quantile loss secondary, both in percentage-point units for
evaluation only. All pairs receive two-sided centered block-bootstrap tests,
pointwise basic intervals and Holm-adjusted p-values within each score family.
Only FZG receives an MCS. GREM is a risk-underestimation screen, not an accuracy
score added to FZG.

## What do the current results support?

Two ML models pass all eight scenarios: Median–IQR–UniBM and
Mean–RMS-Gamma–POT-MLE. Direct quantile passes none. GJR-GARCH-EVT is selected
from four admitted external models. The old Mean–RMS-L2–POT-MLE VaR-gate winner
is excluded because five scenarios crossed the GREM threshold.

On 628 common dates, IQR has the lowest average FZG and Gamma the lowest
quantile loss. IQR-versus-GJR FZG has Holm p=0.0003; IQR-versus-Gamma has
p=0.7288. FZG MCS retains both ML models. These results do not establish
equivalence, a unique best ML recipe or superiority in every individual scenario.

## What should not be claimed?

This is same-inspected-OOS exploratory evidence, not fresh-holdout confirmation.
Screening, reference selection and repeated inspection are not corrected by
Holm or MCS. No causal spillover, price discovery, trading-profit or live-deployment
claim follows. Global scores do not establish information-set increments.
Future residual-risk and intraday extensions remain in [Future Work](future_work.md).
