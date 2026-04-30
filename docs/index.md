---
hide:
  - navigation
---

--8<-- "README.md"

## Documentation Map

- [Results Snapshot](results_snapshot.md): generated evidence map for the completed run,
  including figures, tables, inference outputs, and claim boundaries.
- [Paper Plan](paper_plan.md): research questions, empirical design, model families,
  evaluation metrics, and manuscript-level caveats.
- [Data](data.md): source roles, target hierarchy, point-in-time controls, and data-source
  limitations.
- [Development Audit Prompt](development_audit_prompt.md): implementation review prompt for
  checking code, data, timing, tests, and reporting against the research design.
- [Manuscript Audit Prompt](manuscript_audit_prompt.md): paper-facing review prompt for
  checking draft claims against available evidence.
- [Future Work](future_work.md): deferred extensions that should not dilute the current
  paper.

## Reading Order

1. Start with the [Results Snapshot](results_snapshot.md) to see the current evidence.
2. Use the [Paper Plan](paper_plan.md) as the research contract.
3. Read [Data](data.md) before changing ingestion, schemas, or point-in-time controls.
4. Use the [Development Audit Prompt](development_audit_prompt.md) before implementation
   handoffs or code review.
5. Use the [Manuscript Audit Prompt](manuscript_audit_prompt.md) before circulating a draft.
6. Use [Future Work](future_work.md) to keep deferred extensions out of the current paper.
