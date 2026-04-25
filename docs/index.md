--8<-- "README.md"

## Documentation Map

- [Data](data.md): data contract, source roles, and target definitions.
- [Paper Plan](paper_plan.md): submission-oriented research plan and manuscript structure.
- [Development Prompt](development_prompt.md): single prompt for the next coding phase.

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
```

### Data Staging

Local data is ignored by git:

- `data/raw`: vendor exports or raw API pulls.
- `data/interim`: cleaned but not final datasets.
- `data/processed`: modeling tables and train/test splits.
- `reports`: figures, tables, and model diagnostics.

Keep source credentials in `.env` only. Commit only code, schemas, docs, and small synthetic test fixtures.
