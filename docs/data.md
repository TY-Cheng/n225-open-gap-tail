---
hide:
  - navigation
---

# Data Appendix: Sources, Pretreatment, Features, And Source Notes

This page is written as the data appendix for the paper. It is the canonical
source for source roles, source status, target formulas, timestamp policies,
pretreatment rules, contract-roll treatment, feature blocks, source limitations,
and public data lake tiers. The paper plan should reference this page instead of
duplicating vendor fields or processing rules.

## Source Status

| Source | Role | Project status | Timing interpretation |
| --- | --- | --- | --- |
| J-Quants Futures OHLC | OSE Nikkei 225 Futures target source and contract metadata source | Premium futures access is configured locally for historical audits | Ex-post historical research target source, not an operational pre-open feed. |
| Massive.com | U.S. close-side ETF, equity, sector, dollar ETF proxy, Japan proxy, Asia proxy, and index predictors | Configured licensed API | Predictor source with UTC timestamps converted explicitly to ET. Massive is not the canonical USD/JPY source in the current run. |
| NYSE calendar | U.S. regular close, holiday, and early-close cutoff logic | Core public timing source | Determines the U.S. cash close used for the forecast origin. |
| JPX calendar and trading-hour rules | OSE business-day, day/night session, holiday-trading, roll/SQ context | Core official timing source | Determines OSE target eligibility and holiday/session flags. |
| FRED | Treasury yields, selected rates proxies, and public macro series | Configured public API | Historical control source; vintage-safe work requires ALFRED-style handling where needed. |
| Cboe VIX historical data | U.S. volatility and risk proxy | Core public fallback/check | Daily VIX close is core; high, low, and range are included only when source support is audited. |
| CME/SGX/OSE intraday Nikkei marks | U.S.-close residual reference and cross-venue robustness | Optional licensed extension | Required before using `residual_usclosemark_to_open` or making intraday cross-venue claims. |

Core variable definitions should be transparent enough for reader evaluation. Public fallback checks should be provided where feasible, but the documentation should not claim that all core results are reproducible without the licensed target and predictor sources.
Target and residual-reference prices are futures-contract prices. Cash-index OHLC
is not part of the target-data plan for this paper.

## Current Environment Contract

The current local `.env` contract uses J-Quants API V2. The run futures
target pipeline requires Premium futures access for the historical derivatives endpoint;
intraday derivatives remain disabled unless a licensed intraday mark is added:

```bash
JQUANTS_API_KEY_FILE="/path/to/jquants.keyfile"
JQUANTS_API_BASE_URL="https://api.jquants.com/v2"
JQUANTS_EQUITY_MASTER_ENABLED="true"
JQUANTS_EQUITY_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_INTRADAY_ENABLED="false"
```

Massive and FRED predictor settings separate endpoint credentials from the
research-config feature-set blocks. The `.env` file supplies key-file paths
and base URLs, not raw API-key values; `MASSIVE_API_KEY` and `JQUANTS_API_KEY`
are not runtime configuration paths. The run manifest and
`config/research_config.json` record the exact
feature-set universe. For the current clean run, the fetched Massive daily
universe is the union of the core, optional, Japan proxy, Japanese ADR aggregate,
and Asia proxy blocks:

```text
MASSIVE_API_KEY_FILE="/path/to/massive.keyfile"
MASSIVE_FLAT_FILE_KEY_FILE="/path/to/massive-flat-file.keyfile"
MASSIVE_BASE_URL="https://api.massive.com"
MASSIVE_MINUTE_TICKERS="SPY,QQQ,DIA,IWM,EWJ,DXJ,EEM,FXI,EWY,EWT,EWH,TLT,HYG,GLD"
MASSIVE_MINUTE_TICKER="SPY"
MASSIVE_PROBE_TICKERS="I:VIX"
MASSIVE_OPTIONS_HISTORICAL_ENABLED="false"
MASSIVE_OPTIONS_FLAT_FILES_ENABLED="false"
MASSIVE_OPTIONS_CONTRACT_REST_ENABLED="false"
MASSIVE_OPTIONS_UNDERLYINGS="SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLB,XLU,XLC,SMH,EWJ,DXJ,EEM,FXI,EWY,EWT,EWH,TM,SONY,MUFG,SMFG,MFG"

massive_core = SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLB,XLU,XLC,TLT,GLD,USO,SMH,HYG,LQD
massive_optional = UUP
massive_japan_proxy = EWJ,DXJ
massive_japan_adr_primary = TM,SONY,MUFG,SMFG,MFG
massive_asia_proxy = EEM,FXI,EWY,EWT,EWH

FRED_BASE_URL="https://fred.stlouisfed.org"
fred_core = VIXCLS,DGS2,DGS10,T10Y2Y
fred_fallback = DEXJPUS
fred_credit_enriched = BAMLH0A0HYM2,BAMLC0A0CM
```

These snippets describe the full clean-run fetch universe. Smoke commands can
override them with smaller ticker or series lists. The primary ML nested
information sets do not use every fetched field: `UUP` and the credit-spread
series are now B-layer U.S. close candidates, while short-history funding
series, robustness stress indexes, and unaudited event/skew variables remain
outside the registered primary ML table.
The options flags remain disabled in raw settings as a fail-safe for direct CLI
calls, and the standard `just full` recipe now keeps `options=false` by default.
This makes the canonical full-history run independent of the shorter Massive
OPRA entitlement window. U.S.-listed options features are still available through
an explicit `options=true` run for appendix or recent-window diagnostics, where
they are routed by underlying exposure into the nested information sets.

Short-history and robustness-only candidates stay out of the current registered
full-history primary feature set:

```bash
POST_2018_FRED_SERIES="SOFR,EFFR"
FRED_ROBUSTNESS_SERIES="NFCI,ANFCI,STLFSI4"
```

FRED uses current historical values with conservative availability semantics and is not ALFRED/vintage-safe unless a future run explicitly records realtime or vintage parameters. `DEXJPUS` is handled as a Federal Reserve H.10 weekly-batch as-of FX control: the previous business week's observations are unavailable until the following H.10 release timestamp. Massive FX is not part of the default tail-risk pipeline. `UUP`, when fetched, is a U.S.-traded dollar ETF proxy and should not be described as a USD/JPY exchange-rate source.

## Current Clean-Run Data Inventory

The current paper-facing evidence map is generated from:

```text
run_id = tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4
requested window = 2016-07-19 to 2026-05-22
clean forecast sample = 2018-06-20 to 2026-05-22
clean forecast observations = 1,722
```

The clean sample begins after all required target fields, Massive core fields,
FRED core fields, and the canonical FRED H.10 USD/JPY control satisfy the
registered coverage and timing requirements. The gold modeling panel contains
2,403 target-date rows before the clean-sample filter.

### Run Metadata From The Current Results Snapshot

| Field | Value |
| --- | --- |
| Run ID | `tailrisk_20160719_20260522_20260527T083659Z_commit_7f628ff4` |
| Claim level | `research_candidate` |
| Requested window | `2016-07-19` to `2026-05-22` |
| Combined clean start | `2018-06-20` |
| Gold panel dates | `2016-07-19` to `2026-05-22` |
| Forecast sample dates | `2018-06-20` to `2026-05-22` |
| Forecast sample rows | `1,722` |
| FRED vintage safe | `False` |

The clean start is a modeling lower bound. Dates before it remain audit history
rather than forecast evidence. FRED values use conservative release timing but
are current historical observations rather than ALFRED real-time vintages.

### Target Distribution Summary

These rows are copied from the current results snapshot so the data appendix can
stand alone when describing the empirical target.

| Measure | Value |
| --- | --- |
| Clean forecast observations | `1722` |
| Date range | `2018-06-20 to 2026-05-22` |
| Mean gap | `0.000599` log, about `+0.06%` |
| Standard deviation | `0.011039` log, about `+1.11%` |
| Skewness | `-0.066817` |
| Excess kurtosis | `11.159` |
| 1% quantile | `-0.031062` log, about `-3.06%` |
| 5% quantile | `-0.015606` log, about `-1.55%` |
| Median | `0.001031` log, about `+0.10%` |
| 95% quantile | `0.015357` log, about `+1.55%` |
| 99% quantile | `0.027480` log, about `+2.79%` |
| Max drawdown gap | `-0.087513` log, about `-8.38%`, on `2020-03-13` |
| Max upside gap | `0.096937` log, about `+10.18%`, on `2025-04-10` |
| Jarque-Bera p-value | `0` |
| Jarque-Bera statistic | `8962.16` |

The target summary is a raw-target diagnostic. It motivates tail-risk modeling
but does not validate any VaR/ES forecast.

### Raw-Tail EVT Data Diagnostics

| Tail | Threshold probability | Threshold | Exceedances | Mean excess | GPD xi | GPD scale | Hill xi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| left_tail_loss | `0.900` | `0.0160237` | `78` | `0.0104227` | `0.148364` | `0.00886263` | `0.432871` |
| left_tail_loss | `0.925` | `0.0195554` | `59` | `0.00979449` | `0.318986` | `0.00680111` | `0.342056` |
| left_tail_loss | `0.950` | `0.0223228` | `39` | `0.0114201` | `0.232349` | `0.0088172` | `0.354783` |
| left_tail_loss | `0.975` | `0.0293044` | `20` | `0.0127979` | `0.257683` | `0.00960064` | `0.31884` |
| left_tail_loss | `0.990` | `0.0373166` | `8` | `0.0175619` | `0.204438` | `0.0142233` | `0.342351` |
| right_tail_loss | `0.900` | `0.0150066` | `92` | `0.00903798` | `0.403374` | `0.00560621` | `0.381845` |
| right_tail_loss | `0.925` | `0.0169408` | `69` | `0.00984642` | `0.47548` | `0.00563718` | `0.370713` |
| right_tail_loss | `0.950` | `0.0189956` | `46` | `0.0122032` | `0.29399` | `0.00878548` | `0.41336` |
| right_tail_loss | `0.975` | `0.0259629` | `23` | `0.0146916` | `0.225126` | `0.0115191` | `0.383413` |
| right_tail_loss | `0.990` | `0.0369444` | `10` | `0.0171855` | `0.218772` | `0.0136836` | `0.352692` |
| absolute_gap | `0.900` | `0.0155233` | `170` | `0.00965025` | `0.287887` | `0.00694789` | `0.401867` |
| absolute_gap | `0.925` | `0.0175227` | `127` | `0.0106185` | `0.249472` | `0.00801625` | `0.397719` |
| absolute_gap | `0.950` | `0.0208133` | `85` | `0.011767` | `0.256151` | `0.00884033` | `0.383021` |
| absolute_gap | `0.975` | `0.0269986` | `43` | `0.0144273` | `0.164437` | `0.0120976` | `0.372398` |
| absolute_gap | `0.990` | `0.0371795` | `17` | `0.0183049` | `0.0605131` | `0.0172189` | `0.353301` |

These diagnostics are computed on raw left loss, raw right loss, and absolute
gap. They are data diagnostics, not forecast-model diagnostics.

### Gold Panel, Target Audit, And Calendar Map

| Measure | Value |
| --- | --- |
| Gold modeling rows | `2403` |
| Gold columns | `1428` |
| Target-audit rows | `2403` |
| Clean target rows | `2206` |
| Forecast-sample rows | `1722` |
| Rows before combined clean start | `420` |
| Target-not-clean rows | `197` |
| Mapping excluded rows | `64` |

| Target audit reason | Rows |
| --- | --- |
| None | `2206` |
| roll_sq_excluded | `195` |
| missing_previous_jpx_session | `1` |
| missing_reference_price | `1` |

| Timing-map measure | Value |
| --- | --- |
| Normal trading mappings | `2333` |
| U.S./Japan desync mappings | `1` |
| NYSE early-close mappings | `32` |
| EDT rows | `1563` |
| EST rows | `840` |

Roll/SQ exclusions, missing reference prices, early closes, U.S./Japan
desynchronization, and DST regimes are stored as auditable row-level state
rather than applied as hidden filters.

### Feature Coverage From The Current Gold Panel

| Source family | Block | Features | Mean missing | Max missing |
| --- | --- | --- | --- | --- |
| Asia proxy | Asia proxy | `10` | `0.000%` | `0.000%` |
| cboe_volatility | fred_core | `2` | `0.000%` | `0.000%` |
| cross_market_derived | Asia proxy | `1` | `0.000%` | `0.000%` |
| cross_market_derived | fred_core | `2` | `0.000%` | `0.000%` |
| cross_market_derived | JP proxy | `2` | `0.000%` | `0.000%` |
| cross_market_derived | US core | `2` | `0.000%` | `0.000%` |
| event_calendar | calendar_controls | `7` | `0.000%` | `0.000%` |
| fred_core | fred_core | `9` | `0.000%` | `0.000%` |
| FRED credit enriched | FRED credit enriched | `4` | `62.398%` | `62.427%` |
| fx_core | fx_core | `4` | `0.000%` | `0.000%` |
| Japan history | Japan only | `37` | `0.005%` | `0.058%` |
| JP proxy | JP proxy | `8` | `0.000%` | `0.000%` |
| J-Quants N225 options | Japan only | `30` | `1.605%` | `14.634%` |
| massive_daily | US core | `40` | `0.001%` | `0.058%` |
| massive_minute | Asia proxy | `60` | `0.000%` | `0.000%` |
| massive_minute | JP proxy | `24` | `0.348%` | `4.181%` |
| massive_minute | US late session | `84` | `0.000%` | `0.000%` |
| massive_optional | massive_optional | `2` | `0.000%` | `0.000%` |

Feature coverage is an information-transparency diagnostic. A feature is
admissible only when the timestamp availability and feature-matrix gates also
pass.

### Leakage Audit Summary

| Field | Value |
| --- | --- |
| Status | `pass_with_warnings` |
| Rows audited | `783378` |
| Failures | `0` |
| Warnings | `611790` |
| Panel row count | `2403` |
| Panel signature seed | `42` |
| Panel signature | `8094755ffc96b01af6fb904876e0abdd3920370fa1b07e44c2c95681cd3e5431` |

Zero hard failures means no audited row violated the timestamp invariant. The
warnings are retained because conservative-lag and missing-feature situations
can still matter for interpretation.

### Active Target and Calendar Inputs

- Target source: J-Quants Premium historical OSE Nikkei 225 Futures daily/session
  OHLC for the large Nikkei 225 Futures contract.
- Primary target family: `full_gap_settle_to_open`, defined as
  `log(OSE day-session open_t) - log(previous settlement_{t-1})`.
- Additional audited target fields: `full_gap_close_to_open` and
  `residual_nightclose_to_day_open`.
- Disabled target extension: `residual_usclosemark_to_open`, because the current
  run does not include a licensed timestamped intraday OSE, CME, SGX, or
  equivalent Nikkei futures mark at the U.S. cash close.
- Calendar sources: JPX/OSE trading-day and session rules, NYSE holidays and
  early closes, U.S. DST rules, roll-window flags, SQ-window flags, and
  contract-expiry metadata.
- Timing fields recorded in the panel include `model_cutoff_ts_utc`,
  `target_open_ts_utc`, `dst_regime`, `absorption_regime`,
  `us_close_to_ose_night_close_minutes`, `mapping_status`, and
  `join_miss_reason`.

### Active Massive Daily Inputs

The clean run fetches these Massive daily symbols:

| Block | Symbols | Features used or audited |
| --- | --- | --- |
| Broad U.S. beta | `SPY`, `QQQ`, `DIA`, `IWM` | Close-to-close log returns and high-low log ranges. |
| U.S. sectors | `XLK`, `XLF`, `XLE`, `XLV`, `XLI`, `XLY`, `XLP`, `XLB`, `XLU`, `XLC` | Sector returns and ranges. |
| Duration, safe-haven, commodity, semiconductor, and credit-risk proxies | `TLT`, `GLD`, `USO`, `SMH`, `HYG`, `LQD` | Returns and ranges. |
| Dollar ETF proxy | `UUP` | Cached and audited as `massive_optional`; enters the U.S.-close core information set as a dollar-risk proxy, not as USD/JPY. |
| Japan proxy block | `EWJ`, `DXJ` | Returns and ranges; enters the third ML information set. |
| Japanese ADR aggregate block | `TM`, `SONY`, `MUFG`, `SMFG`, `MFG` | Aggregate-only ADR spot returns/ranges; enters the third ML information set without single-name ADR spot features. |
| Asia proxy block | `EEM`, `FXI`, `EWY`, `EWT`, `EWH` | Returns and ranges; enters the fourth ML information set. |

All Massive daily fields are frozen at the `US_CASH_CLOSE` forecast origin after
the configured vendor-availability lag. Massive timestamps are stored in UTC
and converted to U.S. Eastern Time before session alignment.

### Active Massive Intraday Input

The current feature set uses a curated set of U.S.-listed minute-bar ETF
proxies rather than adding more daily ETF controls. `SPY` is retained through a
small compatibility adapter that projects generic SPY minute records into the
canonical `spy_late_*` / `spy_final_*` feature names; the minute pipeline itself
remains multi-ticker. Additional tickers use lower-case ticker prefixes.
The derived minute features include:

- late 30- and 60-minute log returns;
- late 60-minute realized variance and up/down semivariance;
- late 60-minute skewness and excess kurtosis, recorded as noisy small-sample
  estimators rather than asymptotic realized moments;
- late-session range;
- within-ticker late-volume surge, z-score, and percentile using prior rolling
  history only;
- final-window momentum.

These variables proxy late-session U.S. trading pressure and are frozen at the
same U.S. close cutoff as the daily Massive predictors. The deterministic block
map keeps U.S. core minute proxies in `us_late_session`, `EWJ/DXJ` minute
features in `japan_proxy`, and `EEM/FXI/EWY/EWT/EWH` minute features in
`asia_proxy`.

### Registered Options Source Audit

The project can build bounded U.S. options features from Massive OPRA
`day_aggs_v1` flat files only in explicit opt-in runs when
`MASSIVE_OPTIONS_HISTORICAL_ENABLED=true` and
`MASSIVE_OPTIONS_FLAT_FILES_ENABLED=true`. Massive live option snapshots are not
used for historical backfill. The active U.S. options implementation computes
ATM-IV proxies from option daily aggregate close prices, underlying Massive daily
closes, FRED `DGS2`, and a zero-dividend Black-Scholes approximation. It does
not use vendor historical IV, Greeks, quotes, or open interest.

`just source-probe` now performs a nonblocking Massive flat-file check when
`MASSIVE_FLAT_FILE_KEY_FILE` is configured. The live local probe can list and
range-read `us_options_opra/day_aggs_v1`, `minute_aggs_v1`, and `trades_v1`
headers from the S3-compatible flat-file endpoint; those headers contain option
price/volume/timestamp fields but no direct IV, Greeks, or open interest.
`quotes_v1` is listed by the bucket but currently returns `403 Forbidden` on the
sample header read, so quote-based spread/liquidity filters remain disabled
until entitlement is confirmed. The active v1 liquidity audit is therefore based
on day-agg volume, transaction count, valid-contract count, DTE bucket, and
whether an ATM-IV solve succeeds.

The options audit artifacts are:

- `options_source_audit.parquet`;
- `options_feature_coverage.parquet`;
- `options_liquidity_audit.parquet`.

J-Quants Nikkei 225 large-option data are handled separately from U.S.-listed
options. The pipeline now fetches Nikkei 225 Options (`NK225E`)
daily option-chain rows from J-Quants, consistent with the
[J-Quants index-option field specification](https://jpx.gitbook.io/j-quants-en/api-reference/index_option)
and [option product code list](https://jpx.gitbook.io/j-quants-en/api-reference/options/derivativeproductcategory),
normalizes the compact V2 fields
(`Strike`, `IV`, `OI`, `BaseVol`, `UnderPx`, etc.), promotes the night-session
option OHLC fields (`EO`, `EH`, `EL`, `EC`) into silver as
`night_session_open/high/low/close`, and converts volatility percent values to
fractions. These features enter the `japan_only` block only as lagged domestic
option-implied state. Same target-date option rows are not used.
The default aggregate scope is the registered `7-30` and `31-90` DTE window, so
the main predictors are prior available ATM IV, ATM put-call IV skew, base
volatility, OI-weighted IV, put/call OI and volume ratios, total OI/volume, valid
contract count, days to SQ, and lagged night-session ATM option close/return/range
summaries. These night-session option features are deliberately lagged; without
timestamped intraday or quote-chain evidence they are not interpreted as
same-night U.S.-close-cutoff N225 option information.

The candidate options universe is intentionally capped before any data-driven
selection:

| Block | Candidate underlyings | Status |
| --- | --- | --- |
| J-Quants N225 large options | `NK225E` | Active as lagged `japan_only` option-implied and night-session option-state controls after source/schema smoke; not same-date target information. |
| Core U.S. options | `SPY`, `QQQ`, `DIA`, `IWM` | Opt-in computed ATM-IV proxies in `japan_only_plus_us_close_core` only when Massive options flat files are enabled; appendix/recent-window only unless coverage gates later support promotion. |
| Sector/semiconductor option aggregate | `XLK`, `XLF`, `XLE`, `XLV`, `XLI`, `XLY`, `XLP`, `XLB`, `XLU`, `XLC`, `SMH` | Opt-in aggregate median, dispersion, max, and valid-count ATM-IV state; raw sector option fields stay audit/appendix. |
| Japan ETF options | `EWJ`, `DXJ` | Opt-in computed ATM-IV proxies in `japan_only_plus_us_close_core_plus_japan_proxy` only when Massive options flat files are enabled; appendix/recent-window only unless coverage gates later support promotion. |
| ADR aggregate options | `TM`, `SONY`, `MUFG`, `SMFG`, `MFG` | Opt-in median/20% trimmed-mean aggregate; individual ADRs stay audit/appendix unless separately promoted. |
| Asia proxy option aggregate | `EEM`, `FXI`, `EWY`, `EWT`, `EWH` | Opt-in aggregate ATM-IV state; individual Asia option fields stay audit/appendix. |

The registered DTE buckets are short `7-30` calendar days and medium `31-90`
calendar days. ATM selection is delta-neutral when delta is available or
computed; otherwise the method falls back to closest-to-spot or closest-to-forward
and records the method. Primary options features are capped at 45 curated
aggregate features. Raw per-contract, per-sector, per-Asia-ETF, and per-ADR
fields remain audit or appendix outputs.

### Active FRED and Cboe Inputs

The clean run fetches these FRED series:

| Block | Series | Panel variables |
| --- | --- | --- |
| Core rates and volatility | `VIXCLS`, `DGS2`, `DGS10`, `T10Y2Y` | Levels and first differences, plus `fred_rates_staleness_days`. |
| Canonical USD/JPY FX control | `DEXJPUS` | `fx_usdjpy_level`, `fx_usdjpy_return`, `fx_observation_age_days`, `fx_release_age_days`. |
| Credit-spread enriched block | `BAMLH0A0HYM2`, `BAMLC0A0CM` | Levels and first differences; enters the U.S.-close core information set as credit-stress/risk-appetite proxies subject to coverage gates. |

The clean run also uses Cboe VIX historical data:

- `cboe_vix_close`;
- `cboe_vix_range`.

FRED and Cboe volatility fields are both retained because they serve different
audit roles: FRED `VIXCLS` is handled through the same conservative release-lag
machinery as other FRED series, while Cboe VIX supplies the volatility-index
predictor used in the point-in-time U.S. close information set.

### Active ML Nested Information Sets

The registered ML comparison uses four nested information sets. Options are
routed by economic exposure instead of being grouped into a separate primary
layer: domestic N225 options enter A, U.S. core and sector-aggregate options enter
B, Japan-linked ETF/ADR options enter C, and Asia proxy aggregate options enter D.

| Information set | Active blocks |
| --- | --- |
| `japan_only` | Lagged loss and gap history, rolling loss moments, rolling 95% loss quantile, lagged N225 futures session/volume/OI features, lagged J-Quants N225 large-option implied-state and night-session option aggregates, calendar month terms, DST regime, absorption-regime timing, and timestamp-safe BOJ same-OSE-session flags. |
| `japan_only_plus_us_close_core` | `japan_only` plus Massive U.S. core daily features, U.S. core minute features with canonical SPY fields, FRED core rates/VIX features, FRED credit-spread proxies, Cboe VIX features, FRED H.10 USD/JPY, `UUP` as a dollar-risk ETF proxy, timestamp-safe FOMC/CPI/NFP and event-intensity calendar controls, computed ATM-IV proxies for `SPY`, `QQQ`, `DIA`, and `IWM` options, and aggregate sector/semiconductor ATM-IV state when enabled and audit-gated. |
| `japan_only_plus_us_close_core_plus_japan_proxy` | Previous set plus `EWJ` and `DXJ` daily/minute features, computed ATM-IV proxies for `EWJ` and `DXJ` options, Japanese ADR spot aggregate features, and Japanese ADR aggregate options features when enabled and audit-gated. |
| `japan_only_plus_us_close_core_plus_japan_proxy_plus_asia_proxy` | Previous set plus Asia/regional proxy features for `EEM`, `FXI`, `EWY`, `EWT`, and `EWH`, including daily, minute, and aggregate options features routed by underlying exposure. |

The primary ML nested sets do not include SOFR/EFFR, NFCI/ANFCI/STLFSI4, SKEW,
or VIX term-structure proxies in the current clean run. They do include a narrow
timestamp-safe event-calendar layer: BOJ same-OSE-session information in
`japan_only`, and FOMC/CPI/NFP plus major-event intensity controls from
`japan_only_plus_us_close_core` onward.

### Planned or Candidate Inputs Not Active in the Clean Run

- Broader Japan macro event flags beyond the current BOJ policy-session marker
  remain planned candidate controls. The active event layer is limited to
  timestamp-safe FOMC, CPI, NFP/payroll, BOJ, and simple major-event intensity
  controls.
- SOFR and EFFR are post-2018 enriched FRED candidates and are not part of the
  current full-history primary feature set.
- NFCI, ANFCI, and STLFSI4 are FRED robustness candidates and are not active in
  the current clean run.
- Cboe SKEW, VIX9D, VIX3M, VIX6M, option-implied skew, volatility-surface
  measures, and variance-risk-premium proxies require a separate timestamp and
  coverage audit before they can enter core claims.

The utility smoke/build commands are engineering checks only:

```bash
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli massive-smoke
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli fred-smoke
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli calendar-build
PYTHONPATH=src uv run python -m n225_open_gap_tail.cli contracts-build
```

They use the same cache vocabulary as the run workflow: vendor payloads under
`data/bronze/` and typed normalized outputs under `data/silver/`. Smoke artifacts do not
constitute empirical validation of the forecasting paper.

`data/bronze`, `data/silver`, and `data/gold` are logical data-lake locations.
Local machines should map `DATA_DIR` to external storage in `.env`, or use a
repo-local `data/` symlink that resolves outside the cloud-synced repo. `reports/runs`
can remain local because generated run summaries, tables, and figures are small
relative to the vendor cache and gold data lake.

## Forecast Origins

Every modeling row must state a forecast origin and model cutoff.

| Forecast origin | Nominal timestamp | Known information | Target open | Main use |
| --- | ---: | --- | --- | --- |
| `US_CASH_CLOSE` | Official U.S. cash close, normally 16:00 ET and adjusted for early closes | U.S. ETF, index, sector, FX, VIX, rates, and other predictor fields available by the U.S. close cutoff | Next eligible OSE day open at 08:45 JST | Main pre-open risk forecast origin. |
| `OSE_NIGHT_CLOSE` | 06:00 JST | OSE night close if available as an audited historical field or licensed intraday reference | Same OSE day open at 08:45 JST | Night-session absorption robustness and residual decomposition. |
| `PREV_OSE_DAY_CLOSE` | 15:45 JST | Previous OSE day-session close and settlement context | Next eligible OSE day open | Full opening-level risk target. |

J-Quants futures OHLC can support historical reconstruction of targets and residual decompositions after the subscription is available. It should not be described as an operational source for the `US_CASH_CLOSE` or `OSE_NIGHT_CLOSE` information set.

The phrase "U.S. close information" is a cutoff definition, not a claim that
all U.S. after-close or overnight events are observed. A predictor can enter the
`US_CASH_CLOSE` information set only when its source timestamp and configured
availability lag place it at or before the model cutoff.

## Predictor Universe

The first-paper predictor universe is pre-registered by economic role rather than by feature search. Candidate variables must pass timestamp, availability, and sample-coverage checks before they enter the modeling table.

| Block | Candidate variables | Source | Timing status | Economic justification |
| --- | --- | --- | --- | --- |
| Broad U.S. beta | SPY, DIA, QQQ, IWM returns and ranges | Massive.com | `US_CASH_CLOSE` after official close plus vendor lag | U.S. equity-market direction and risk appetite. |
| U.S. late-session dynamics | SPY/QQQ/DIA/IWM/TLT/HYG/GLD last-30-minute return, last-hour return, late-session range, late-60-minute volume surge, final-window reversal or momentum | Massive.com minute bars | `US_CASH_CLOSE` after official close plus vendor lag | Late U.S. trading pressure and closing imbalance proxies that may be more informative than daily close-to-close moves. |
| U.S. sectors | XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLB, XLU, XLC returns and dispersion | Massive.com | `US_CASH_CLOSE` | Sector composition, growth/cyclical rotation, defensives, utilities, and communications exposure. |
| U.S. global-risk proxies | SMH, HYG, LQD | Massive.com core candidates | `US_CASH_CLOSE` after source audit | Semiconductor and credit-risk channels relevant to Japan but treated as U.S. core risk proxies. |
| Japan proxy block | EWJ, DXJ plus aggregate TM/SONY/MUFG/SMFG/MFG ADR spot summaries | Massive.com ML tail proxy block | `US_CASH_CLOSE` after source audit | U.S.-traded Japan equity proxies used to test whether Japan-exposure trading absorbs incremental signal beyond broad U.S. core without exposing primary ML specifications to individual ADR names. |
| Asia proxy block | EEM, FXI, EWY, EWT, EWH | Massive.com ML tail proxy block | `US_CASH_CLOSE` after source audit | Emerging-market, China, Korea, Taiwan, and Hong Kong proxies used to test regional and supply-chain information beyond Japan proxies. |
| FX | Canonical USD/JPY from FRED `DEXJPUS` only | FRED H.10 | H.10 weekly-batch as-of release | Conservative lagged currency control without letting optional Massive FX entitlement determine the main sample. |
| Safe-haven and commodity proxies | TLT, GLD, USO | Massive.com planned candidates | `US_CASH_CLOSE` after source audit | Flight-to-quality, dollar-rate duration, and commodity-risk channels. |
| U.S. volatility | VIX close; VIX high/low/range when available | Cboe, FRED, Massive index probe | Historical daily close or audited index timestamp | U.S. implied volatility and volatility-of-risk regime. |
| U.S. tail/skew proxies | Cboe SKEW, VIX9D, VIX3M, VIX6M | Cboe or licensed source | Tier 1.5/Tier 2 depending access and coverage | Option-implied downside-tail and volatility-term-structure information. |
| Treasury rates | DGS2, DGS10, T10Y2Y | FRED | Current historical values with +1 U.S. business-day availability lag; not ALFRED/vintage-safe by default | Rate level and curve slope. SOFR/EFFR are post-2018 enriched candidates only. |
| Credit spreads | BAMLH0A0HYM2, BAMLC0A0CM | FRED/ICE BofA | B-layer U.S. close candidate with conservative FRED lag; not ALFRED/vintage-safe | Credit-stress proxy for global downside tail risk without shortening the required core sample by default. |
| Event flags | FOMC, CPI, payrolls/NFP, BOJ, simple major-event intensity controls; broader Japan macro releases remain planned | Official calendars | Active timestamp-safe calendar controls for the narrow registered event layer; broader macro-event expansion remains candidate work | Scheduled risk-event controls without macro feature fishing. |
| Lagged Japanese futures state | Prior gap, lagged day return, lagged night return, volume/OI changes, roll/SQ flags | J-Quants futures after Premium access | Historical target-side variables, lagged before cutoff | Domestic state, lagged turnover/activity proxies, and contract-state controls; not direct market-depth measures. |

The Massive ticker selection covers U.S. market beta, technology and growth exposure, small-cap risk appetite, sector dispersion, a U.S. dollar ETF proxy, duration, safe-haven demand, commodities, Asia/EM risk, and semiconductors. Canonical USD/JPY comes from FRED `DEXJPUS`, not Massive. Japan and Asia proxy tickers are cached with the panel but enter the ML tail nested information sets separately from the broad U.S. core block.

## Data Availability Timeline

Before modeling, each predictor block must produce an availability table with:

- source name and vendor;
- candidate variables;
- raw coverage start and end;
- usable coverage after timestamp alignment;
- missingness rate;
- frequency and release/update timing;
- effective sample impact after joining to OSE target dates.

The target audit and predictor timeline jointly determine the final sample period. Variables with short or unstable histories can enter robustness tables, but not the main predictor set if they materially shorten the main sample.

## Cache-First Data Lake Contract

`just full` builds a local cache-first data lake before model evaluation. The command
defaults to `force=false`; use `force=true` only for an intentional, documented
schema/cache invalidation. The recipe also defaults to `options=false`, so the
canonical full-history run skips Massive OPRA `day_aggs_v1` option-feature
ingestion. This avoids making primary claims depend on a shorter OPRA entitlement
window. Use `just full 2016-07-19 "" 6 false true` only for an opt-in appendix or
recent-window run with U.S. options features. When the end argument is blank, the default data
cutoff is the most recent completed Friday rather than the calendar run date; use
an explicit `YYYY-MM-DD` end date to override the paper-freeze default. The default
start is `2016-07-19`, treated as a clean-sample candidate rather than a hard
empirical claim. The final modeling start is written to the run manifest as:

```text
combined_clean_start = max(
  jquants_required_field_coverage_start,
  required_massive_core_coverage_start,
  required_fred_core_coverage_start,
  canonical_fx_coverage_start
)
```

`jquants_required_field_coverage_start` defaults to `2016-07-19` only when
`fields_coverage_audit.parquet` supports required coverage for settlement, last-trading-day,
SQ-day, and central-contract fields. `2008-05-07` remains available for opening-gap-history audit
or robustness runs, not as the default clean predictor sample. Because XLC remains a
required U.S. sector control, the final `combined_clean_start` is expected to move to
XLC's post-inception coverage period rather than remain at the 2016 cache lower bound.

Physical layout uses Hive-style Parquet partitions with schema version in the path:

```text
data/bronze/jquants_futures_daily/schema_version=1/year=2016/month=07/data.parquet
data/silver/jquants_nk225f_daily/schema_version=2/year=2016/month=07/data.parquet
data/silver/massive_minute_features/schema_version=1/ticker=spy/year=2016/month=07/data.parquet
data/bronze/calendar_sessions/schema_version=1/start=2016-07-19/end=2026-05-02/metadata.json
data/silver/calendar_sessions/schema_version=1/start=2016-07-19/end=2026-05-02/data.parquet
data/bronze/nikkei_contracts_rule_based/schema_version=1/start=2016-07-19/end=2026-05-02/metadata.json
data/silver/nikkei_contracts_rule_based/schema_version=1/start=2016-07-19/end=2026-05-02/contracts.parquet
```

All Parquet writes are atomic: write to `.tmp.<pid>.<uuid>`, validate row count and schema,
compute separate `xxhash64` chunk and schema hashes, then `os.replace()` into place. At the
start of `just full`, orphan `.tmp` files older than two hours are removed. Readers use
explicit Hive partition schemas so `year` and `month` are numeric, not inferred strings.

Layer boundaries:

- Bronze stores typed vendor-cache rows and provenance: endpoint, requested range, pull
  timestamps, row counts, schema version, schema hash, and content hash.
- Silver stores canonical research rows. J-Quants silver filters `NK225F`, stores UTC-aware
  timestamps, flags zero or negative prices and OHLC violations, and does not impute.
- Gold joins targets, calendar map, Massive predictors, minute late-session features, FRED
  predictors, roll/SQ flags, and audit columns by `ose_trading_date`.

Rebuild semantics are layer-aware. Rebuilding silver or gold uses existing local cache and
does not call vendor APIs unless bronze is missing or a vendor refresh is explicitly
requested.

## Calendar Map and Join Diagnostics

`calendar_map.parquet` is built before the gold panel. It maps the relevant U.S. close date
to each OSE target date and records:

- U.S. official close UTC and early-close flag;
- EST/EDT regime;
- OSE day open and night close UTC timestamps;
- `us_close_to_ose_night_close_minutes`;
- model cutoff and target open;
- enum-valued `mapping_status`: `normal_trading`, `us_holiday`, `jp_holiday`,
  `us_jp_desync`, `ose_holiday_trading`, or `unmapped`.

Gold joins preserve target rows when predictors are missing. Missing predictors are reported
with enum-valued `join_miss_reason`, including entitlement gaps, missing cache partitions,
FRED release lag, `fred_vintage_not_realtime_safe`, market-calendar desync, and predictor
nulls. This keeps structural missingness separate from random data gaps.

## FRED TTL and Vintage Label

Default FRED ingestion uses current historical values with a conservative availability lag
and is labeled `vintage_safe=false`. The cache has a default 30-day TTL, evaluated exactly
once at run start. Chunks that are stale at run start refresh before use; chunks that are
fresh at run start remain valid for that run even if the TTL would expire mid-run. Each FRED
cache metadata file records the pull timestamp, run-start TTL decision timestamp, vintage
label, revision-risk label, and refresh status.

For ordinary non-FX FRED predictors, the gold panel selects each feature independently using
the latest non-null value whose `feature_available_ts_utc` is no later than the model cutoff.
Forward-filled levels keep their source observation date and availability timestamp; synthetic
filled diffs are set to `0.0` and marked with fill metadata rather than treated as raw
observations. The expanded ML tail block also carries `fred_rates_staleness_days`, computed from
the DGS2/DGS10/T10Y2Y rate block, so release lag can be learned by the model instead of
remaining only a diagnostic.

ML tail writes feature-unavailability diagnostics under `metrics/` for each tail-risk run:
`ml_tail_feature_unavailability.parquet` aggregates missing active features by information set,
and `ml_tail_feature_unavailability_dates.parquet` keeps the date-level trace needed to separate
structural gaps such as late-session minute volume from FRED release-lag handling.

ML tail also writes a result-matrix layer under `metrics/` for model-family audit:
`ml_tail_result_matrix.parquet`, `ml_tail_result_matrix_sample_audit.parquet`,
`ml_tail_result_matrix_dm.parquet`, and
the run-specific `ml_tail_result_matrix_notes.md` artifact. This layer separates VaR-only comparisons
(`var_quantile_loss`, coverage, exception diagnostics) from VaR-ES joint scoring
(`var_es_fz_loss`) and uses restricted common samples. It does not replace the primary
ML tail ladder in `ml_tail_metrics.parquet`.

## Target Hierarchy

All target formulas use log gaps.

Main target:

- `full_gap_settle_to_open = log(day_open_t) - log(prev_settlement_{t-1})`.

Secondary target:

- `full_gap_close_to_open = log(day_open_t) - log(prev_day_close_{t-1})`.

Absorption robustness target:

- `residual_nightclose_to_day_open = log(day_open_t) - log(night_close_t)`, when `night_close_t` is available and its timestamp semantics are audited.

The current locked forecast run evaluates only `full_gap_settle_to_open`.
The close-to-open and night-close-to-open target variants remain deferred; their
presence in the target-audit schema does not make them completed forecast experiments.

Licensed-data extension:

- `residual_usclosemark_to_open = log(day_open_t) - log(nikkei_futures_mark_at_us_cash_close_t)`.

`residual_usclosemark_to_open` is disabled until a licensed intraday OSE, CME, SGX, or equivalent Nikkei futures reference mark exists at the U.S. cash close.

## J-Quants Field-to-Use Contract

| Field | Use | Audit note |
| --- | --- | --- |
| `DaySessionOpen` | Target open for all full-gap and residual targets | Must be present and traceable to raw contract rows. |
| `DaySessionClose` | Reference for `full_gap_close_to_open` and lagged Japanese controls | Must refer to the same contract convention used in target construction. |
| `NightSessionClose` | Reference for `residual_nightclose_to_day_open` and night-session absorption controls | Historical residual source only unless a licensed operational feed exists. |
| `SettlementPrice` | Main reference for `full_gap_settle_to_open` | Must be matched to the prior eligible contract/session. |
| `Volume` | Lagged turnover/activity proxy and data-sanity field | Session-specific volume is used only if available and verified; it is not interpreted as order-book depth. |
| `OpenInterest` | Contract-state, participation, and roll diagnostics | Used with roll/SQ controls; it is not a direct liquidity-depth measure. |
| `LastTradingDay` | Roll-window flag and expiry exclusion logic | Must be reconciled with JPX contract rules. |
| `SpecialQuotationDay` | SQ-window flag and robustness/exclusion rule | Used to prevent SQ-driven artifacts from dominating the tail. |
| `CentralContractMonthFlag` | Main contract selection and roll diagnostics | Must be reconciled against observed liquidity and metadata. |

The main contract is the OSE Nikkei 225 Futures large contract. Mini and micro contracts are robustness or liquidity checks only unless the research design changes.

## Contract Roll Mechanics

Target gaps are calculated intra-contract wherever possible. A target observation should not mechanically join the settlement or close of one contract to the day open of another contract and treat the resulting artificial spread as a market opening gap.

Default policy:

- select the active contract using audited `CentralContractMonthFlag`, contract month, liquidity, and roll metadata;
- exclude target gaps that cross a contract roll, last-trading-day boundary, or SQ exclusion window from the main specification;
- keep roll, SQ, and near-expiry flags for audit and robustness tables;
- use flag-and-include only as a robustness exercise;
- use ratio-adjusted or Panama-style continuous series only for robustness or long-memory volatility features, not for the main opening-gap target.

The target audit must report how many observations are excluded by the roll/SQ policy and whether extreme gaps are traceable to raw same-contract rows.

## Massive Timestamp Policy

Massive raw timestamps are stored in UTC. Preprocessing must convert them explicitly to U.S. Eastern Time before applying U.S. session cutoffs.

The `US_CASH_CLOSE` cutoff is based on the official U.S. cash-market close:

- regular sessions normally use 16:00 ET;
- NYSE early-close sessions use the official early-close time;
- a configurable vendor-availability lag is applied after the close, with a default of 15 minutes for research feature freezing;
- the lag is a conservative research convention, not a live data guarantee;
- `is_us_early_close` and DST regime flags must be stored.

No feature may enter a `US_CASH_CLOSE` forecast row unless its `vendor_available_ts_utc` is no later than `model_cutoff_ts_utc`.

## Public Data Lake Tiers

The data lake is intentionally tiered to prevent feature fishing.

### Tier 0: Calendars and Timing

- JPX/OSE trading hours, holidays, holiday trading, and target-session eligibility.
- NYSE holidays and official early closes.
- U.S. DST transition dates and UTC/ET/JST conversion tables.
- Roll windows, SQ windows, and contract-expiry metadata.

### Tier 1: Core Controls and Predictors

- Massive U.S. ETF, sector, equity-index, dollar ETF proxy, Japan proxy, and Asia proxy predictors. Canonical USD/JPY is the FRED H.10 `DEXJPUS` series.
- U.S.-listed minute-bar late-session features: generic ticker-prefixed fields
  for the curated minute universe, with canonical `spy_late_*` and
  `spy_final_*` fields kept by the SPY compatibility adapter. Features include
  late returns, realized variance, up/down
  semivariance, noisy small-sample skewness/kurtosis, range, volume surge,
  volume z-score, volume percentile, and final-window momentum, all frozen at
  U.S. close plus the configured vendor-availability lag. Volume normalization
  is within ticker and uses prior rolling history only.
- Massive core block additions: XLY, XLP, XLB, XLU, XLC, TLT, GLD, USO, SMH, HYG, and LQD after source and coverage audit.
- Massive ML tail proxy blocks: Japan proxy (`EWJ`, `DXJ`) and Asia proxy (`EEM`, `FXI`, `EWY`, `EWT`, `EWH`) are cached now but interpreted separately from the core U.S. close block.
- Cboe or FRED VIX close; VIX high, low, and range only when the source supports them.
- FRED 2-year and 10-year Treasury yields, T10Y2Y yield-curve slope, and ICE BofA credit-spread proxies. Credit spreads enter the B-layer U.S.-close core as current-historical FRED series with conservative lag controls, not ALFRED/vintage-safe series. SOFR/EFFR funding proxies are `post_2018_enriched`, not part of the current full-history primary feature set.
- Event calendar controls: timestamp-safe FOMC, CPI, NFP/payroll, BOJ policy
  events, and simple major-event intensity controls are active; broader Japan
  macro releases remain planned candidates.
- Lagged Japanese futures variables: prior gap, lagged OSE day return, lagged OSE night return when available, volume/open-interest changes, roll/SQ flags, and holiday-adjacent flags.

### Tier 1.5: Tail-Risk Proxy Candidates

- Cboe SKEW or a licensed SKEW proxy.
- VIX term-structure proxies such as VIX9D, VIX3M, and VIX6M.
- Massive index probes such as `I:VIX` and `I:SKEW` only if the plan supports them.
- U.S.-listed options-risk features from `SPY`, `QQQ`, `DIA`, `IWM`, sector
  ETFs plus `SMH`, `EWJ`, `DXJ`, Asia proxy ETFs, and primary Japanese ADR
  aggregates can be computed from Massive OPRA day aggregates as ATM-IV proxies
  only in explicit `options=true` runs. They are routed by economic exposure:
  U.S. core and sector aggregate options into B, Japan ETF and ADR aggregate
  options into C, and Asia proxy aggregate options into D. Under the current data
  entitlement they are appendix/recent-window diagnostics, not canonical
  full-history primary predictors.
  J-Quants `NK225E` daily options are already active only as lagged domestic
  `japan_only` state, including lagged night-session option OHLC summaries from
  `EO/EH/EL/EC`.

Tier 1.5 variables are natural for a tail-risk paper but must not shorten the main sample or introduce unclear availability timestamps. If they do, they move to Tier 2 robustness.

### Tier 2: Leakage-Safe Extensions

- ALFRED-style real-time vintage macro series.
- CME, SGX, or intraday OSE Nikkei futures marks for `residual_usclosemark_to_open`.
- Options-implied skew, volatility-surface, or tail-risk proxies where licensed.
- Public-source replication checks where a lower-fidelity but academically accessible substitute exists.

Tier 2 variables do not enter first-paper core claims unless their timestamps, availability, and source definitions are audited.

## Timestamp Fields

Data rows should separate the following timestamps:

- `observation_ts_utc`
- `bar_start_ts_utc`
- `bar_end_ts_utc`
- `vendor_available_ts_utc`
- `research_download_ts_utc`
- `model_cutoff_ts_utc`
- `target_open_ts_utc`
- `reference_price_ts_utc`
- `release_ts_utc`, when using scheduled macro or event data
- `vintage_date`, when using revised macro series

Core invariants:

- `target_open_ts_utc > model_cutoff_ts_utc`.
- Feature availability timestamps must be no later than `model_cutoff_ts_utc`.
- Residual target reference prices must satisfy `reference_price_ts_utc <= model_cutoff_ts_utc`.
- Full-gap ex-post reference prices must be labeled as previous-session references, not live U.S.-close residual marks.

## Tail-Risk Labels and EVT Data Requirements

The internal labels `left_tail` and `right_tail` refer to the corresponding
sides of the original opening-gap return distribution. In economic terms, they
represent downside and upside loss, respectively. Both are oriented so that
larger values indicate more adverse outcomes:

- define `left_tail` losses as `L_t = -gap_t`;
- define `right_tail` losses as `L_t = gap_t`;
- define exceedances using training-window thresholds only;
- store threshold, exceedance indicator, exceedance severity, VaR forecast, and ES forecast;
- report training-window standardized-loss counts and exceedance counts before reporting POT-GPD VaR/ES forecasts.

The primary tail level is `0.95`. `LightGBM mean/scale POT-GPD MLE` is the
registered filtered-EVT estimator. `LightGBM mean/scale POT-GPD UniBM` is a restricted
shape-estimator comparison: it uses the same LightGBM mean/log-scale body
filter, the same POT threshold, and a UniBM block-maxima-derived estimate of
the GPD shape `xi`, with scale refit conditional on that fixed `xi`. Here EVI
means the GPD shape convention `xi`; it is the reciprocal of the Pareto tail
index `alpha` when `P(X > x) ~ x^{-alpha}`. UniBM failures are reported as
unavailable rather than replaced by the MLE route. Diagnostics record shape method,
UniBM block-grid diagnostics, threshold sensitivity, shape/scale stability,
shape bins, and whether ES is finite.

Both transformed loss series are evaluated through the upper tail of their
respective loss distributions under the same sample, coverage, and inference
gates. The labels `left_tail` and
`right_tail` continue to identify the corresponding sides of the original
opening-gap return distribution.

## Model-Ready Loss Fields

Processed model tables should carry the fields needed to audit the mean/scale LightGBM-EVT path:

| Field | Meaning |
| --- | --- |
| `gap_t` | Target log gap for the selected target family. |
| `loss_t` | Downside loss, defined as `-gap_t`. |
| `baseline_residual_loss_t` | Residual loss from the selected baseline location or location-scale model. |
| `lgbm_predicted_location_t` | LightGBM conditional location prediction where used. |
| `lgbm_predicted_scale_t` | LightGBM conditional scale prediction used to standardize losses. |
| `scale_smearing_factor` | Pooled Duan retransformation factor computed from out-of-fold scale residuals. |
| `oof_standardized_loss_count` | Number of fully out-of-fold standardized losses available for empirical or EVT tail calibration. |
| `standardized_loss_t` | Loss divided by predicted scale, after any documented location adjustment. |
| `evt_threshold_u` | Training-window POT threshold used for the row's forecast. |
| `exceedance_indicator_t` | Indicator that `standardized_loss_t` exceeds the threshold. |
| `exceedance_severity_t` | Excess over threshold for EVT severity calibration. |
| `evt_variant` | POT-GPD variant label. The registered estimator is MLE; the restricted UniBM comparison is `unibm`. |
| `evt_shape_method` | Shape-estimation method recorded for the row's EVT calibration. |
| `evt_evi_status` | Extreme-value-index status for `xi`, including unavailable or diagnostic-disagreement cases. |
| `evt_ei_status` | Extremal-index status, including unavailable or no-discount fallbacks. |
| `evt_cap_policy` | Shape-cap policy used for the variant. |
| `evt_cap_hit` | Indicator that the fitted shape hit a cap where a cap policy is used. |
| `evt_scale_refit_status` | Status for GPD scale handling. |
| `evt_es_finite` | Whether the row supplies a finite ES under the fitted shape. |
| `tail_probability_alpha` | VaR/ES tail probability for the forecast row. |
| `var_forecast` | VaR forecast transformed back to target scale. |
| `es_forecast` | ES forecast transformed back to target scale. |

The registered primary POT threshold remains fixed at `0.90`. Threshold
sensitivity is written as a diagnostic artifact before any dynamic-threshold
rule is promoted to the registered primary design. The empirical location-scale
and POT-GPD variants use a common final LightGBM location-scale
backbone by construction; diagnostic EVT variants differ in tail calibration rather than
in a variant-specific final location/scale seed.

## Source Notes

- JPX Nikkei 225 Futures contract specifications: [Nikkei 225 Futures | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/products/domestic/225futures/01.html)
- JPX derivatives trading hours: [Trading Hours | Derivatives | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/rules/trading-hours/index.html)
- J-Quants plan coverage: [Available APIs and Data Periods per Plan | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-spec)
- J-Quants update timing: [Update Timing of Provided Data | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-update)
- Massive.com stocks overview: [Stocks Overview | Massive.com](https://massive.com/docs/rest/stocks/overview)
- NYSE trading hours and early closes: [Holidays and Trading Hours | NYSE](https://www.nyse.com/trade/hours-calendars)
- FRED observations API: [fred/series/observations | FRED](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- FRED USD/JPY H.10 series: [DEXJPUS](https://fred.stlouisfed.org/series/DEXJPUS)
- Federal Reserve H.10 release timing: [Foreign Exchange Rates - H.10](https://www.federalreserve.gov/releases/h10/)
- FRED high-yield credit spread candidate: [BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)
- FRED investment-grade credit spread candidate: [BAMLC0A0CM](https://fred.stlouisfed.org/series/BAMLC0A0CM)
- FRED yield-curve slope candidate: [T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y)
- FRED funding-rate candidates: [SOFR](https://fred.stlouisfed.org/series/SOFR), [EFFR](https://fred.stlouisfed.org/series/EFFR)
- Cboe VIX historical data: [VIX Index Historical Data | Cboe](https://www.cboe.com/tradable_products/vix/vix_historical_data)
- Cboe VIX term-structure dashboard: [VIX9D, VIX3M, VIX6M dashboard](https://www.cboe.com/us/indices/dashboard/VIX-VIX1Y-VIX3M-VIX6M-VIX9D/)
- CME Nikkei products: [Nikkei 225 futures | CME Group](https://www.cmegroup.com/nikkei)
