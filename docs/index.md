---
hide:
  - navigation
---

--8<-- "README.md"

## Documentation Map

- [Paper Plan](paper_plan.md): research questions, empirical design, model families,
  evaluation metrics, and manuscript-level caveats.
- [Data](data.md): source roles, target hierarchy, point-in-time controls, and data-source
  limitations.
- [Results Snapshot](results_snapshot.md): generated evidence map for the completed run,
  including figures, tables, inference outputs, and claim boundaries.
- [FAQ](faq.md): short reader-facing framing for the research
  question, target, data, models, metrics, and current evidence.
- [Development Audit Prompt](development_audit_prompt.md): implementation review prompt for
  checking code, data, timing, tests, and reporting against the research design.
- [Manuscript Audit Prompt](manuscript_audit_prompt.md): JFM/Wiley-facing review prompt
  for checking draft claims, evidence locks, and submission-style build readiness.
- [Future Work](future_work.md): deferred extensions that should not dilute the current
  paper.

## Reading Order

1. Start with the [Paper Plan](paper_plan.md) as the research contract.
2. Read [Data](data.md) before changing ingestion, schemas, or point-in-time controls.
3. Use the [Results Snapshot](results_snapshot.md) to inspect the current evidence.
4. Use the [FAQ](faq.md) for the plain research framing.
5. Use the [Development Audit Prompt](development_audit_prompt.md) before implementation
   handoffs or code review.
6. Use the [Manuscript Audit Prompt](manuscript_audit_prompt.md) before circulating a draft.
7. Use [Future Work](future_work.md) to keep deferred extensions out of the current paper.
