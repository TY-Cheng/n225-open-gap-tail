--8<-- "README.md"

## Documentation Map

- [Results Snapshot](results_snapshot.md): current evidence state, smoke outputs, blockers, and artifact map.
- [Paper Plan](paper_plan.md): research design, contribution boundary, empirical contract, and acceptance gates.
- [Data](data.md): source roles, target hierarchy, timestamp contract, and data-source caveats.
- [Audit](audit/index.md): prompts for reviewing implementation and manuscript claims against the research contract.
- [Future Work](future_work.md): deferred extensions that should not dilute the first paper.

## Workflow

### Local Setup

```bash
just setup
```

This loads `.env` and creates the uv environment at `${HOME}/.venvs/n225-open-gap-tail`.

### Daily Development

```bash
just status
just test
just lint
just docs-build
```

`just docs` serves the site on the first available local port at or above `8000`.

### Data Staging

Local data is ignored by git:

- `data/raw`: vendor exports or raw API pulls.
- `data/interim`: cleaned but not final datasets.
- `data/processed`: modeling tables and train/test splits.
- `reports`: figures, tables, and model diagnostics.

Keep source credentials in `.env` only. Commit only code, schemas, docs, and small synthetic test fixtures.

### Paper-Grade P2A

```bash
just paper-panel
just paper-eval
just paper-latex-tables
```

The P2A path builds the full-history modeling panel and baseline-floor artifacts under ignored
`reports/paper_runs/`. These artifacts are paper-grade candidates, not final manuscript claims.
Custom windows and workers use positional recipe arguments, for example
`just paper-panel 2022-01-01 2026-04-28` or `just paper-eval <run_id> 4 p2a`.

## Readiness Snapshot

Layer | Current state | Boundary
--- | --- | ---
U.S. predictors | Massive and FRED smoke ingestion implemented and tested. | These are historical predictor sources, not live production feeds.
Calendar and contract scaffolding | XNYS/JPX calendars, early closes, DST, quarterly contract metadata, roll windows, and central-contract selector implemented. | Rule-based Nikkei futures metadata must be reconciled against J-Quants or JPX metadata before final empirical results.
Target data | J-Quants Premium futures daily OHLC is accessible and the 2022-present target audit snapshot runs. | The snapshot is smoke evidence; final paper results need the full paper-grade rolling evaluation.
Modeling | Historical, rolling, vol-scaled, LightGBM direct-quantile, and EVT smoke wiring runs behind gates. | No paper-grade model ranking, VaR/ES claim, or hedge usefulness claim is active.

## Reading Order

Start with the [results snapshot](results_snapshot.md) for current implementation status. Use the [paper plan](paper_plan.md) as the research contract. Use [data](data.md) before touching ingestion or schemas. Use the [audit section](audit/index.md) when handing work to another coding agent or reviewing a manuscript draft.
