# Results Snapshot

!!! warning "Smoke-only artifact"
    This page is generated from `20220101_20260428_20260428T034829Z_commit_55d8291c`. It is pipeline evidence only, not manuscript evidence.

## Snapshot

| Field | Value |
| --- | --- |
| Snapshot ID | `20220101_20260428_20260428T034829Z_commit_55d8291c` |
| Artifact root | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c` |
| Claims level | `smoke_only_not_manuscript_evidence` |
| Window | `['2022-01-01', '2026-04-28']` |
| Target rows | `1055` |
| Clean target rows | `969` |
| Roll/SQ excluded rows | `85` |
| Time-alignment failures | `0` |
| Model smoke status | `smoke_metrics_available` |

## Interpretation Boundary

This snapshot validates data access, target construction, timestamp alignment, predictor availability, and smoke-only model wiring. It does **not** support claims about causal spillover, price discovery, trading alpha, live deployment, LightGBM-EVT superiority, or ES improvement.

Regenerate this page with `just snapshot` after material code or schema changes. The snapshot window is intentionally bounded and may start later than the full `just full` default; it is a smoke/access check, not the clean modeling sample.

## Model Smoke

The model layer is deliberately labeled as smoke-only. If LightGBM or EVT gates are unavailable, that is a valid engineering result rather than weak empirical evidence.

```json
{
  "alpha": 0.05,
  "claims_level": "smoke_only_not_manuscript_evidence",
  "evt_loc": 0.0,
  "evt_scale": 0.008869544882098554,
  "evt_shape": 0.18920402319765245,
  "evt_status": "smoke_fit_available",
  "evt_threshold": 0.01609874738650294,
  "evt_threshold_quantile": 0.95,
  "evt_threshold_selection": "empirical_95pct_smoke; final paper requires mean-excess and parameter-stability diagnostics",
  "evt_train_exceedances": 39,
  "historical_quantile_exception_rate": 0.05154639175257732,
  "lightgbm_exception_rate": 0.04639175257731959,
  "lightgbm_status": "smoke_metrics_available",
  "min_test_rows_for_metrics": 20,
  "min_total_rows_for_split": 120,
  "min_train_exceedances_for_evt": 30,
  "min_train_rows_for_lightgbm": 80,
  "no_leaderboard": true,
  "overall_status": "smoke_metrics_available",
  "rolling_quantile_exception_rate": 0.04639175257731959,
  "target": "full_gap_settle_to_open",
  "test_rows": 194,
  "total_clean_rows": 969,
  "train_rows": 775,
  "vol_scaled_exception_rate": 0.05154639175257732
}
```

## Artifact Index

| Artifact | Path |
| --- | --- |
| `manifest` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/manifest.json` |
| `data_vintage` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/data_vintage.json` |
| `schema_probe` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/jquants_schema_probe.json` |
| `audit_header` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/audit_header.json` |
| `normalized_jquants` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/target_audit/jquants_futures_normalized.parquet` |
| `target_audit` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/target_audit/target_audit.parquet` |
| `time_alignment` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/target_audit/time_alignment_check.parquet` |
| `calendar_alignment` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/target_audit/calendar_alignment.parquet` |
| `massive_daily` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/predictors/massive_daily.parquet` |
| `spy_minutes` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/predictors/spy_minutes.parquet` |
| `fred` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/predictors/fred.parquet` |
| `predictor_availability` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/predictors/predictor_availability.parquet` |
| `model_smoke` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/model_smoke/model_smoke_status.json` |
| `narrative` | `reports/snapshots/20220101_20260428_20260428T034829Z_commit_55d8291c/narrative/snapshot_summary.md` |
