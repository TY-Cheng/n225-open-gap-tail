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

## Readiness Snapshot

Layer | Current state | Boundary
--- | --- | ---
U.S. predictors | Massive and FRED smoke ingestion implemented and tested. | These are historical predictor sources, not live production feeds.
Calendar and contract scaffolding | XNYS/JPX calendars, early closes, DST, quarterly contract metadata, roll windows, and central-contract selector implemented. | Rule-based Nikkei futures metadata must be reconciled against J-Quants or JPX metadata before final empirical results.
Target data | J-Quants V2 free-plan smoke works for equity endpoints. | OSE Nikkei 225 Futures target data still requires a futures-capable subscription.
Modeling | Baselines, LightGBM, EVT, and evaluation are planned. | No paper-grade model result exists until the target builder and feature table are built.

## Reading Order

Start with the [results snapshot](results_snapshot.md) for current implementation status. Use the [paper plan](paper_plan.md) as the research contract. Use [data](data.md) before touching ingestion or schemas. Use the [audit section](audit/index.md) when handing work to another coding agent or reviewing a manuscript draft.
