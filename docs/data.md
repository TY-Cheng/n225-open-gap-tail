---
hide:
  - navigation
---

# Data Design and Contract

This page is the canonical source for source roles, source status, target formulas, timestamp policies, contract-roll treatment, and public data lake tiers. The paper plan should reference this page instead of duplicating vendor fields or processing rules.

## Source Status

| Source | Role | Project status | Timing interpretation |
| --- | --- | --- | --- |
| J-Quants Futures OHLC | OSE Nikkei 225 Futures target source and contract metadata source | Premium futures access is configured locally for historical audits | Ex-post historical research target source, not a live pre-open feed. |
| Massive.com | U.S. close-side ETF, equity, sector, FX, and index predictors | Configured licensed API | Predictor source with UTC timestamps converted explicitly to ET. |
| NYSE calendar | U.S. regular close, holiday, and early-close cutoff logic | Core public timing source | Determines the U.S. cash close used for the forecast origin. |
| JPX calendar and trading-hour rules | OSE business-day, day/night session, holiday-trading, roll/SQ context | Core official timing source | Determines OSE target eligibility and holiday/session flags. |
| FRED | Treasury yields, selected rates proxies, and public macro series | Configured public API | Historical control source; vintage-safe work requires ALFRED-style handling where needed. |
| Cboe VIX historical data | U.S. volatility and risk proxy | Core public fallback/check | Daily VIX close is core; high, low, and range are included only when source support is audited. |
| Nikkei Indexes spot OHLC | Spot-market controls or robustness | Optional public or licensed source | Not the futures target source. |
| CME/SGX/OSE intraday Nikkei marks | U.S.-close residual reference and cross-venue robustness | Optional licensed extension | Required before using `residual_usclosemark_to_open` or making intraday cross-venue claims. |

Core variable definitions should be transparent enough for reader evaluation. Public fallback checks should be provided where feasible, but the documentation should not claim that all core results are reproducible without the licensed target and predictor sources.

## Current Environment Contract

The current local `.env` contract uses J-Quants API V2. The run futures
target pipeline requires Premium futures access for the historical derivatives endpoint;
intraday derivatives remain disabled unless a licensed intraday mark is added:

```bash
JQUANTS_API_VERSION="v2"
JQUANTS_API_KEY="replace-me"
JQUANTS_API_BASE_URL="https://api.jquants.com/v2"
JQUANTS_API_PLAN="premium"
JQUANTS_EQUITY_MASTER_ENABLED="true"
JQUANTS_EQUITY_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_INTRADAY_ENABLED="false"
```

Massive and FRED predictor settings are:

```bash
MASSIVE_API_KEY="replace-me"
MASSIVE_BASE_URL="https://api.massive.com"
MASSIVE_DAILY_TICKERS="SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,XLY,XLP,XLB,XLU,XLC,TLT,GLD,USO,EEM,FXI,SMH,HYG,LQD,EWJ,DXJ,EWY,EWT,EWH"
MASSIVE_MINUTE_TICKER="SPY"
MASSIVE_PROBE_TICKERS="I:VIX"

FRED_BASE_URL="https://fred.stlouisfed.org"
FRED_SERIES="VIXCLS,DGS2,DGS10,T10Y2Y,DEXJPUS"
```

These snippets are the run core defaults. Smoke commands can override them with smaller ticker or series lists.

Short-history and robustness-only candidates stay out of `core_full_history`:

```bash
POST_2018_FRED_SERIES="SOFR,EFFR"
FRED_CREDIT_ENRICHED_SERIES="BAMLH0A0HYM2,BAMLC0A0CM"
JAPAN_PROXY_MASSIVE_TICKERS="EWJ,DXJ"
ASIA_PROXY_MASSIVE_TICKERS="EWY,EWT,EWH"
OPTIONAL_MASSIVE_TICKERS="UUP"
```

FRED uses current historical values with conservative availability semantics and is not ALFRED/vintage-safe unless a future run explicitly records realtime or vintage parameters. `DEXJPUS` is handled as a Federal Reserve H.10 weekly-batch as-of FX control: the previous business week's observations are unavailable until the following H.10 release timestamp. Massive FX is not part of the default tail-risk pipeline.

The utility smoke/build commands are engineering checks only:

```bash
n225-open-gap-tail massive-smoke
n225-open-gap-tail fred-smoke
n225-open-gap-tail calendar-build
n225-open-gap-tail contracts-build
```

They use the same cache vocabulary as the run workflow: vendor payloads under
`data/bronze/` and typed normalized outputs under `data/silver/`. Smoke artifacts do not
constitute empirical validation of the forecasting paper.

## Forecast Origins

Every modeling row must state a forecast origin and model cutoff.

| Forecast origin | Nominal timestamp | Known information | Target open | Main use |
| --- | ---: | --- | --- | --- |
| `US_CASH_CLOSE` | Official U.S. cash close, normally 16:00 ET and adjusted for early closes | U.S. ETF, index, sector, FX, VIX, rates, and event information available at the cutoff | Next eligible OSE day open at 08:45 JST | Main pre-open risk forecast origin. |
| `OSE_NIGHT_CLOSE` | 06:00 JST | OSE night close if available as an audited historical field or live licensed feed | Same OSE day open at 08:45 JST | Night-session absorption robustness and residual decomposition. |
| `PREV_OSE_DAY_CLOSE` | 15:45 JST | Previous OSE day-session close and settlement context | Next eligible OSE day open | Full opening-level risk target. |

J-Quants futures OHLC can support historical reconstruction of targets and residual decompositions after the subscription is available. It should not be described as a live source for the `US_CASH_CLOSE` or `OSE_NIGHT_CLOSE` production information set.

## Predictor Universe

The first-paper predictor universe is pre-registered by economic role rather than by feature search. Candidate variables must pass timestamp, availability, and sample-coverage checks before they enter the modeling table.

| Block | Candidate variables | Source | Timing status | Economic justification |
| --- | --- | --- | --- | --- |
| Broad U.S. beta | SPY, DIA, QQQ, IWM returns and ranges | Massive.com | `US_CASH_CLOSE` after official close plus vendor lag | U.S. equity-market direction and risk appetite. |
| U.S. late-session dynamics | SPY last-30-minute return, last-hour return, late-session range, late-60-minute volume surge, final-window reversal or momentum | Massive.com minute bars | `US_CASH_CLOSE` after official close plus vendor lag | Late U.S. trading pressure and closing imbalance proxies that may be more informative than daily close-to-close moves. |
| U.S. sectors | XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLB, XLU, XLC returns and dispersion | Massive.com | `US_CASH_CLOSE` | Sector composition, growth/cyclical rotation, defensives, utilities, and communications exposure. |
| Asia and global risk | EEM, FXI, SMH, HYG, LQD | Massive.com core candidates | `US_CASH_CLOSE` after source audit | Emerging-market, China, semiconductor, and credit-risk channels relevant to Japan. |
| Japan proxy block | EWJ, DXJ | Massive.com ML tail proxy block | `US_CASH_CLOSE` after source audit | U.S.-traded Japan equity proxies used to test whether Japan-exposure trading absorbs incremental signal beyond broad U.S. core. |
| Asia proxy block | EWY, EWT, EWH | Massive.com ML tail proxy block | `US_CASH_CLOSE` after source audit | Korea, Taiwan, and Hong Kong proxies used to test regional and supply-chain information beyond Japan proxies. |
| FX | Canonical USD/JPY from FRED `DEXJPUS` only | FRED H.10 | H.10 weekly-batch as-of release | Conservative lagged currency control without letting optional Massive FX entitlement determine the main sample. |
| Safe-haven and commodity proxies | TLT, GLD, USO | Massive.com planned candidates | `US_CASH_CLOSE` after source audit | Flight-to-quality, dollar-rate duration, and commodity-risk channels. |
| U.S. volatility | VIX close; VIX high/low/range when available | Cboe, FRED, Massive index probe | Historical daily close or audited index timestamp | U.S. implied volatility and volatility-of-risk regime. |
| U.S. tail/skew proxies | Cboe SKEW, VIX9D, VIX3M, VIX6M | Cboe or licensed source | Tier 1.5/Tier 2 depending access and coverage | Option-implied left-tail and volatility-term-structure information. |
| Treasury rates | DGS2, DGS10, T10Y2Y | FRED | Current historical values with +1 U.S. business-day availability lag; not ALFRED/vintage-safe by default | Rate level and curve slope. SOFR/EFFR are post-2018 enriched candidates only. |
| Credit spreads | BAMLH0A0HYM2, BAMLC0A0CM | FRED/ICE BofA | Enriched/robustness block unless coverage supports inclusion | Credit-stress proxy for global downside tail risk without shortening the required core sample by default. |
| Event flags | FOMC, CPI, payrolls, BOJ, major Japan macro releases | Official calendars | Timestamped event flags, no numeric surprises in core design | Scheduled risk-event controls without macro feature fishing. |
| Lagged Japanese futures state | Prior gap, lagged day return, lagged night return, volume/OI changes, roll/SQ flags | J-Quants futures after Premium access | Historical target-side variables, lagged before cutoff | Domestic state, liquidity proxy, and contract-state controls. |

The Massive ticker selection covers U.S. market beta, technology and growth exposure, small-cap risk appetite, sector dispersion, FX, duration, safe-haven demand, commodities, Asia/EM risk, and semiconductors. Japan and Asia proxy tickers are cached with the panel but enter the ML tail nested information-set ladder separately from the broad U.S. core block.

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

`just full` builds a local cache-first data lake before model evaluation. The default start
is `2016-07-19`, treated as a clean-sample candidate rather than a hard empirical claim.
The final modeling start is written to the run manifest as:

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
SQ-day, and central-contract fields. `2008-05-07` remains available for target-history audit
or robustness runs, not as the default clean predictor sample. Because XLC remains a
required U.S. sector control, the final `combined_clean_start` is expected to move to
XLC's post-inception coverage period rather than remain at the 2016 cache lower bound.

Physical layout uses Hive-style Parquet partitions with schema version in the path:

```text
data/bronze/jquants_futures_daily/schema_version=1/year=2016/month=07/data.parquet
data/silver/jquants_nk225f_daily/schema_version=1/year=2016/month=07/data.parquet
data/silver/massive_spy_minute_features/schema_version=2/ticker=spy/year=2016/month=07/data.parquet
data/bronze/calendar_sessions/schema_version=1/start=2016-07-19/end=2026-04-28/metadata.json
data/silver/calendar_sessions/schema_version=1/start=2016-07-19/end=2026-04-28/data.parquet
data/bronze/nikkei_contracts_rule_based/schema_version=1/start=2016-07-19/end=2026-04-28/metadata.json
data/silver/nikkei_contracts_rule_based/schema_version=1/start=2016-07-19/end=2026-04-28/contracts.parquet
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
- Gold joins targets, calendar map, Massive predictors, SPY late-session features, FRED
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
structural gaps such as SPY late-session volume from FRED release-lag handling.

ML tail also writes a result-matrix layer under `metrics/` for model-family audit:
`ml_tail_result_matrix.parquet`, `ml_tail_result_matrix_sample_audit.parquet`,
`ml_tail_result_matrix_dm.parquet`, `ml_tail_result_matrix_mcs.parquet`, and
`ml_tail_result_matrix_notes.md`. This layer separates VaR-only comparisons
(`var_quantile_loss`, coverage, exception diagnostics) from VaR-ES joint scoring
(`var_es_fz_loss`) and uses restricted common samples. It does not replace the headline
ML tail ladder in `ml_tail_metrics.parquet`.

## Target Hierarchy

All target formulas use log gaps.

Main target:

- `full_gap_settle_to_open = log(day_open_t) - log(prev_settlement_{t-1})`.

Secondary target:

- `full_gap_close_to_open = log(day_open_t) - log(prev_day_close_{t-1})`.

Absorption robustness target:

- `residual_nightclose_to_day_open = log(day_open_t) - log(night_close_t)`, when `night_close_t` is available and its timestamp semantics are audited.

Licensed-data extension:

- `residual_usclosemark_to_open = log(day_open_t) - log(nikkei_futures_mark_at_us_cash_close_t)`.

`residual_usclosemark_to_open` is disabled until a licensed intraday OSE, CME, SGX, or equivalent Nikkei futures reference mark exists at the U.S. cash close.

## J-Quants Field-to-Use Contract

| Field | Use | Audit note |
| --- | --- | --- |
| `DaySessionOpen` | Target open for all full-gap and residual targets | Must be present and traceable to raw contract rows. |
| `DaySessionClose` | Reference for `full_gap_close_to_open` and lagged Japanese controls | Must refer to the same contract convention used in target construction. |
| `NightSessionClose` | Reference for `residual_nightclose_to_day_open` and night-session absorption controls | Historical residual source only unless a live licensed feed exists. |
| `SettlementPrice` | Main reference for `full_gap_settle_to_open` | Must be matched to the prior eligible contract/session. |
| `Volume` | Liquidity proxy and data-sanity field | Session-specific volume is used only if available and verified. |
| `OpenInterest` | Liquidity, contract-state, and roll diagnostics | Used as a proxy, not as direct depth. |
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

- Massive U.S. ETF, sector, equity-index, and USD/JPY predictors.
- SPY minute-bar late-session features: last-30-minute return, last-hour return, late-session range, late-60-minute volume surge, and final-window reversal or momentum, all frozen at U.S. close plus the configured vendor-availability lag. The volume-surge baseline is recomputed across loaded cache partitions so monthly Hive chunks do not create artificial first-session missing values.
- Massive core block additions: XLY, XLP, XLB, XLU, XLC, TLT, GLD, USO, EEM, FXI, SMH, HYG, and LQD after source and coverage audit.
- Massive ML tail proxy blocks: Japan proxy (`EWJ`, `DXJ`) and Asia proxy (`EWY`, `EWT`, `EWH`) are cached now but interpreted separately from the core U.S. close block.
- Cboe or FRED VIX close; VIX high, low, and range only when the source supports them.
- FRED 2-year and 10-year Treasury yields, T10Y2Y yield-curve slope, and ICE BofA credit-spread proxies. SOFR/EFFR funding proxies are `post_2018_enriched`, not `core_full_history`.
- Major event flags: FOMC, CPI, payrolls, BOJ policy events, and major Japan macro releases.
- Lagged Japanese futures variables: prior gap, lagged OSE day return, lagged OSE night return when available, volume/open-interest changes, roll/SQ flags, and holiday-adjacent flags.

### Tier 1.5: Tail-Risk Proxy Candidates

- Cboe SKEW or a licensed SKEW proxy.
- VIX term-structure proxies such as VIX9D, VIX3M, and VIX6M.
- Massive index probes such as `I:VIX` and `I:SKEW` only if the plan supports them.

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

Fields required for the DST absorption design:

- `dst_regime`
- `us_close_to_ose_night_close_minutes`
- `absorption_regime`
- `alpha_absorb_group`, optional reporting group for absorption-coefficient tables

Core invariants:

- `target_open_ts_utc > model_cutoff_ts_utc`.
- Feature availability timestamps must be no later than `model_cutoff_ts_utc`.
- Residual target reference prices must satisfy `reference_price_ts_utc <= model_cutoff_ts_utc`.
- Full-gap ex-post reference prices must be labeled as previous-session references, not live U.S.-close residual marks.

## Tail-Risk Labels and EVT Data Requirements

The main paper focuses on downside tail risk:

- define losses as `L_t = -gap_t`;
- define downside exceedances using training-window thresholds only;
- store threshold, exceedance indicator, exceedance severity, VaR forecast, and ES forecast;
- report training-window exceedance counts before reporting POT-GPD VaR/ES forecasts;
- require minimum exceedance diagnostics, with 30 training-window exceedances as the default rolling-window gate for EVT-based ES reporting.

EVT diagnostics should include mean-excess behavior, Hill or tail-index estimates where appropriate, threshold sensitivity, and shape/scale stability.

Upper-tail labels are optional robustness or appendix work, not first-phase implementation.

## Model-Ready Loss Fields

Processed model tables should carry the fields needed to audit the LightGBM-standardized-loss POT-GPD path:

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
| `tail_probability_alpha` | VaR/ES tail probability for the forecast row. |
| `var_forecast` | VaR forecast transformed back to target scale. |
| `es_forecast` | ES forecast transformed back to target scale. |

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
