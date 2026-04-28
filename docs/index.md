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
just status
just check
```

This loads `.env`, syncs the uv environment declared by `UV_PROJECT_ENVIRONMENT`, formats
and checks the code, runs tests, and performs a strict docs build.

### Daily Development

```bash
just status
just check
just docs
```

`just check` formats/fixes `src` and `tests`, runs the test suite, and performs a strict docs
build. `just docs` performs the same strict docs build before serving the site on the first
available local port at or above `8000`.

### Data Staging

Local data is ignored by git:

- `data/bronze`: vendor payloads and first typed vendor caches.
- `data/silver`: canonical cleaned/cacheable research rows.
- `data/gold`: reserved durable cross-run gold tables.
- `reports`: figures, tables, and model diagnostics.

Keep source credentials in `.env` only. Commit only code, schemas, docs, and small synthetic test fixtures.

### Paper-Grade Workflow

```bash
just full
```

The unified path runs local checks, builds the cache-first modeling panel, runs the P2A
baseline floor, audits leakage timestamps, and exports provenance-bearing table fragments
under ignored `reports/paper_runs/`. P2B/P2C commands are explicit nonblocking gates until
their registered model implementations produce evidence. These artifacts are paper
candidates, not final manuscript claims.

`just full` defaults to `2016-07-19` as a cache lower bound. The run manifest computes
`combined_clean_start` from required J-Quants field coverage, XLC-inclusive Massive core
coverage, required FRED core coverage, and the canonical USD/JPY fallback. J-Quants
target-history audit can still be run from `2008-05-07`, but it is not the default clean
predictor sample.

The data path is cache-first: Hive-style Parquet partitions under ignored `data/bronze/`
and `data/silver/`, run-scoped gold panel artifacts under `reports/paper_runs/<run_id>/panel/`,
atomic writes with `xxhash64` chunk hashes, run-start cleanup of orphan temp files,
early-close-aware Massive daily and SPY late-session features, and FRED current-historical
caches labeled `vintage_safe=false` with TTL decisions made once at run start. `DEXJPUS`
uses H.10 batch-release as-of timing; Massive `C:USDJPY` is optional FX fallback evidence.

Custom windows and workers use positional recipe arguments, for example
`just full 2022-01-01 "" 4`. The lower-level recipes remain available for debugging:
`_paper-panel`, `_paper-eval`, `_paper-leakage-check`, and `_paper-latex-tables`.

## Readiness Snapshot

Layer | Current state | Boundary
--- | --- | ---
U.S. predictors | Massive and FRED smoke ingestion implemented and tested. | These are historical predictor sources, not live production feeds.
Calendar and contract scaffolding | XNYS/JPX calendars, early closes, DST, quarterly contract metadata, roll windows, and central-contract selector implemented. | Rule-based Nikkei futures metadata must be reconciled against J-Quants or JPX metadata before final empirical results.
Target data | J-Quants Premium futures daily OHLC is accessible and the 2022-present target audit snapshot runs. | The snapshot is smoke evidence; final paper results need the full paper-grade rolling evaluation.
Modeling | P2A historical, rolling, vol-scaled, GARCH/GJR, and GJR-EVT baseline floor runs behind gates. | P2B/P2C and inference outputs must be marked unavailable until their registered implementations complete.

## Reading Order

Start with the [results snapshot](results_snapshot.md) for current implementation status. Use the [paper plan](paper_plan.md) as the research contract. Use [data](data.md) before touching ingestion or schemas. Use the [audit section](audit/index.md) when handing work to another coding agent or reviewing a manuscript draft.
