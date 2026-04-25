# Data Contract

## Source Roles

J-Quants is the primary research source for OSE Nikkei 225 Futures target construction. New development should use J-Quants API V2 with API-key authentication. It should be treated as an ex-post daily/session OHLC source for reproducible historical research, not as a live pre-open production feed.

Massive.com is the primary source for U.S. close-side predictors. Massive timestamps must be treated as UTC and explicitly converted to ET before U.S. session alignment.

Nikkei Indexes spot OHLC can support spot-market controls or robustness checks, but it is not the futures target.

## Target Data

The preferred target source is OSE Nikkei 225 Futures data from JPX/J-Quants. The first implementation should use daily/session-level J-Quants futures OHLC after the subscription includes that endpoint. The current free plan is useful for V2 API smoke tests with equity master and equity daily bars, but it does not include the futures daily OHLC target. J-Quants DataCube or another licensed intraday feed is only needed if the paper implements a U.S.-close Nikkei futures reference mark or validates intraday opening mechanics.

The current `.env` contract for J-Quants is:

```bash
JQUANTS_API_VERSION="v2"
JQUANTS_API_KEY="replace-me"
JQUANTS_API_BASE_URL="https://api.jquants.com/v2"
JQUANTS_API_PLAN="free"
JQUANTS_EQUITY_MASTER_ENABLED="true"
JQUANTS_EQUITY_DAILY_ENABLED="true"
JQUANTS_DERIVATIVES_DAILY_ENABLED="false"
JQUANTS_DERIVATIVES_INTRADAY_ENABLED="false"
```

Required J-Quants fields:

- Trading date, contract code, derivative product category, contract month, and central contract flag.
- Day-session open, high, low, and close.
- Night-session open, high, low, and close where available.
- Whole-day open, high, low, and close.
- Settlement price, volume, open interest, last trading day, and special quotation day.

The main contract is OSE Nikkei 225 Futures large contract. Mini and micro contracts are robustness or liquidity checks only unless the research design changes.

## Forecast Origins

Every target and feature table must state the forecast origin and model cutoff:

- `US_CASH_CLOSE`: U.S. predictors frozen at the regular U.S. cash close.
- `OSE_NIGHT_CLOSE`: OSE night close used only when available and timestamp-valid.
- `PREV_OSE_DAY_CLOSE`: previous OSE day-session close or settlement context.

The research must not claim that U.S. close information mechanically identifies U.S.-to-Japan spillover without accounting for the OSE night session.

## Target Hierarchy

Primary target with daily/session J-Quants:

- `full_gap_settle_to_open`: `log(day_open_t) - log(prev_settlement_{t-1})`.

Secondary full-gap target:

- `full_gap_close_to_open`: `log(day_open_t) - log(prev_day_close_{t-1})`.

Residual robustness target:

- `residual_nightclose_to_day_open`: `log(day_open_t) - log(night_close_t)`, when the night close is available and timestamp-valid.

Ideal pre-open residual target:

- `residual_usclosemark_to_open`: `log(day_open_t) - log(nikkei_futures_mark_at_us_cash_close_t)`.

`residual_usclosemark_to_open` is unavailable unless a licensed intraday OSE, CME, SGX, or equivalent Nikkei futures reference mark is available at the U.S. cash close. It should be documented as an extension until that data exists.

## Predictor Data

The Massive.com API configuration is:

```bash
MASSIVE_API_KEY="replace-me"
MASSIVE_BASE_URL="https://api.massive.com"
MASSIVE_DAILY_TICKERS="SPY,QQQ,DIA,IWM,XLK,XLF,XLE,XLV,XLI,C:USDJPY"
MASSIVE_MINUTE_TICKER="SPY"
MASSIVE_PROBE_TICKERS="I:VIX"
```

The first Massive data-engineering command is:

```bash
n225-open-gap-tail massive-smoke
```

It writes raw API responses to ignored `data/raw/massive/` and normalized parquet files to ignored `data/interim/massive/`. These artifacts are smoke and schema checks only; they are not empirical validation of the paper's forecasting claims.

FRED is the free historical source for VIX and Treasury-rate proxies:

```bash
FRED_BASE_URL="https://fred.stlouisfed.org"
FRED_SERIES="VIXCLS,DGS2,DGS10"
```

```bash
n225-open-gap-tail fred-smoke
```

`VIXCLS` is treated as a historical Cboe-sourced daily close predictor. `DGS2` and `DGS10` are historical rate proxies. These series are acceptable for a historical backtest, but their rows carry a `historical_daily_close_proxy_not_live_availability` note and should not be used to claim real-time deployability.

Calendar and contract scaffolding are built locally:

```bash
CALENDAR_US_EXCHANGE="XNYS"
CALENDAR_JPX_EXCHANGE="JPX"
NIKKEI_CONTRACT_ROLL_DAYS_BEFORE_LAST_TRADE="5"
NIKKEI_CONTRACT_MONTHS="3,6,9,12"
```

```bash
n225-open-gap-tail calendar-build
n225-open-gap-tail contracts-build
```

The calendar table uses `exchange-calendars` for XNYS and JPX/XTKS sessions, U.S. early closes, weekday holidays, and U.S. DST. It is an alignment scaffold; OSE derivatives holiday trading and night-session edge cases still need a futures-source audit.

The contract metadata table is rule-based: quarterly Nikkei 225 futures months, second-Friday SQ dates, JPX-calendar-adjusted last trading days, a configurable roll window, and a central-contract selector that rolls from the front contract to the next contract during the roll window. It must be reconciled against J-Quants or JPX contract metadata before final empirical results.

U.S. close-side features should be timestamped and frozen before the model cutoff:

- Broad U.S. equity ETFs and indexes: SPY, QQQ, DIA, IWM, and major index proxies.
- Sector ETFs and cross-sector dispersion signals.
- Volatility and tail-risk proxies: VIX, VIX futures, VVIX, SKEW, MOVE, or similar proxies where licensed.
- U.S. futures, rates, FX, and commodities where the subscribed data plan supports them.
- USD/JPY and U.S. rates proxies where available.
- Calendar and event controls: U.S./Japan holidays, U.S. early closes, FOMC, CPI, payrolls, BOJ, major Japan macro releases, DST regime, roll windows, SQ windows, and OSE holiday trading.

Lagged Japanese futures variables should include prior gap, lagged OSE day returns, lagged OSE night returns where available, volume/open-interest changes, and market-structure flags.

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

Core invariants:

- `target_open_ts_utc > model_cutoff_ts_utc`.
- Feature availability timestamps must be no later than `model_cutoff_ts_utc`.
- Residual target reference prices must have `reference_price_ts_utc <= model_cutoff_ts_utc`.
- Full-gap ex-post reference prices must be labeled as previous-session references, not live U.S.-close residual marks.

## Tail-Risk Labels

The main paper focuses on downside tail risk:

- Define losses as `L_t = -gap_t`.
- Define downside exceedances using training-window thresholds only.
- Store threshold, exceedance indicator, exceedance severity, VaR forecast, and ES forecast.

Upper-tail labels are optional robustness or appendix work, not first-phase implementation.

## Source Notes

- JPX derivatives trading hours: [Trading Hours | Derivatives | Japan Exchange Group](https://www.jpx.co.jp/english/derivatives/rules/trading-hours/index.html)
- J-Quants update timing: [Update Timing of Provided Data | J-Quants API](https://jpx.gitbook.io/j-quants-en/outline/data-update)
- Massive.com stocks overview: [Stocks Overview | Massive.com](https://massive.com/docs/rest/stocks/overview)
