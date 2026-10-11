#!/usr/bin/env python3
"""Assemble a frozen S&P 500 finance dataset in the fev-bench item layout used by the iAmTime demo notebooks.

Output (one row per ticker, every array column aligned to the common trading-day index):

    id, timestamp[], sector, industry, market_cap, index_weight, first_valid,          # static
    close[], adj_close[], volume[], log_volume[], dollar_volume[], log_return[],        # candidate targets
    abs_return[], rv_gk[], rv21[],                                                      #   (annualised vol)
    vix_close[], spx_log_return[], sector_etf_log_return[],                             # past-only market covariates
    us10y_yield[], yield_curve_10y2y[], consumer_sentiment[], news_sentiment[],         # past-only macro / sentiment
    eps_surprise_pct[],                                                                 # past-only (known at the reaction)
    earnings_day[], earnings_reaction[], earnings_window[], days_to_earnings[],         # known-future earnings calendar
    opex[], triple_witching[], fomc[], month_end[], quarter_end[], day_of_week[]        # known-future calendar

Sources (prices through `yfinance`, so the snapshot is reproducible only if you keep the parquet):
    prices / volume          yfinance, all current S&P 500 constituents (survivorship bias: current members only)
    constituents + GICS      Wikipedia "List of S&P 500 companies" (or --companies-csv, e.g. Kaggle sp500_companies.csv)
    index, VIX, sector ETFs  ^GSPC, ^VIX, XLK XLF XLV XLY XLP XLE XLI XLB XLU XLRE XLC
    earnings calendar        yfinance Ticker.get_earnings_dates (past + upcoming; time of day, EPS estimate / actual / surprise %)
    macro / sentiment        FRED CSV endpoint (no API key): DGS10, T10Y2Y, UMCSENT; --skip-fred to leave them NaN
    news sentiment           optional --sentiment-csv (date, symbol, score), e.g. LLM-summarised headlines; NaN otherwise
    FOMC decision dates      built-in list 2015-2026 (checked against the Fed's published calendars) or --fomc-csv

Usage:
    pip install yfinance pandas pyarrow lxml
    python build_finance_dataset.py --snapshot 2026-10-02 --start 2015-01-01 --out data/
    python build_finance_dataset.py --snapshot 2026-10-02 --max-tickers 60 --skip-earnings     # quick test
    python build_finance_dataset.py --snapshot 2026-10-02 --companies-csv sp500_companies.csv   # offline constituents

In a notebook (replaces `load_dataset(DATASET_PATH, config, split="train").to_pandas()`):
    from build_finance_dataset import load_finance
    items = load_finance("data/finance_sp500_2026-10-02.parquet", complete_from="2015-01-05")   # complete series only
    target = np.stack(items["log_volume"])                                                       # (tickers, days)

Everything is clipped to <= --snapshot, so a build on a later day with the same arguments reproduces the file
(up to upstream data revisions), and the manifest records what was built.

No look-ahead: a target or past-only covariate at index t uses only data available by the close of day t.
Daily FRED values are lagged one trading day (they are published the next business day) and monthly consumer
sentiment is available from the first trading day of the following month.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------------------------------------- reference data

SECTOR_ETF = {  # GICS sector -> SPDR sector ETF, used for the sector-return covariate.
    "Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Materials": "XLB", "Utilities": "XLU", "Real Estate": "XLRE",
    "Communication Services": "XLC",
}
# Kaggle sp500_companies.csv and yfinance use slightly different sector names; map them onto GICS.
SECTOR_ALIASES = {"Technology": "Information Technology", "Healthcare": "Health Care",
                  "Financial Services": "Financials", "Consumer Cyclical": "Consumer Discretionary",
                  "Consumer Defensive": "Consumer Staples", "Basic Materials": "Materials"}

# FOMC decision days: second day of each scheduled meeting, plus the 2020 emergency actions (2020-03-03 and
# Sunday 2020-03-15, which calendar_covariates maps to the next trading day). Checked against
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm; pass --fomc-csv to override.
FOMC_DATES = """
2015-01-28 2015-03-18 2015-04-29 2015-06-17 2015-07-29 2015-09-17 2015-10-28 2015-12-16
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-03 2020-03-15 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28 2026-12-09
""".split()

MARKET_TICKERS = {"spx": "^GSPC", "vix": "^VIX"}
# FRED series -> output column, publication handling. "daily": lag one trading day; "monthly": usable from the next month.
FRED_SERIES = {"DGS10": ("us10y_yield", "daily"), "T10Y2Y": ("yield_curve_10y2y", "daily"),
               "UMCSENT": ("consumer_sentiment", "monthly")}
TRADING_DAYS = 252
MAX_DAYS_AHEAD = 30


# ------------------------------------------------------------------------------------------------- download

def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _retry(fn, what: str, attempts: int = 4, first_wait: float = 5.0):
    """Call fn(); on any exception wait 5 s, 15 s, 45 s ... and retry (Yahoo rate-limits bursts)."""
    for k in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - network errors come in many types
            if k == attempts - 1:
                raise
            wait = first_wait * 3 ** k
            log(f"{what}: {type(exc).__name__}: {exc}; retrying in {wait:.0f}s")
            time.sleep(wait)
    return None


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch_constituents(companies_csv: str | None) -> pd.DataFrame:
    """Return columns: symbol, sector, industry, market_cap, index_weight."""
    if companies_csv:
        raw = pd.read_csv(companies_csv)
        cols = {c.lower(): c for c in raw.columns}
        out = pd.DataFrame({
            "symbol": raw[cols["symbol"]],
            "sector": raw[cols["sector"]],
            "industry": raw[cols.get("industry", cols["sector"])],
            "market_cap": raw[cols["marketcap"]] if "marketcap" in cols else np.nan,
            "index_weight": raw[cols["weight"]] if "weight" in cols else np.nan,
        })
    else:
        html = _retry(lambda: _http_get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"), "constituents")
        table = pd.read_html(io.StringIO(html.decode("utf-8")))[0]
        out = pd.DataFrame({
            "symbol": table["Symbol"], "sector": table["GICS Sector"],
            "industry": table["GICS Sub-Industry"], "market_cap": np.nan, "index_weight": np.nan,
        })
    out["symbol"] = out["symbol"].astype(str).str.replace(".", "-", regex=False)   # BRK.B -> BRK-B for yfinance
    out["sector"] = out["sector"].replace(SECTOR_ALIASES)
    return out.drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)


def _ohlcv_for(data: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Pick one ticker's OHLCV out of a yf.download frame, whatever column layout this yfinance version returns."""
    if isinstance(data.columns, pd.MultiIndex):
        for level in range(data.columns.nlevels):
            if ticker in data.columns.get_level_values(level):
                df = data.xs(ticker, axis=1, level=level)
                break
        else:
            return None
    else:
        df = data
    df = df.rename(columns=lambda c: str(c).lower().replace("_", " "))
    needed = ["open", "high", "low", "close", "adj close", "volume"]
    if not set(needed) <= set(df.columns):
        return None
    df = df[needed].dropna(how="all")
    df.columns = ["open", "high", "low", "close", "adj_close", "volume"]
    index = pd.DatetimeIndex(df.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    df.index = index.normalize()
    return df


def fetch_prices(tickers: list[str], start: str, snapshot: str, cache: Path, batch: int = 100) -> dict[str, pd.DataFrame]:
    """Daily OHLCV + adjusted close per ticker, cached as CSV per ticker and snapshot."""
    import yfinance as yf

    end = (pd.Timestamp(snapshot) + timedelta(days=1)).strftime("%Y-%m-%d")   # yfinance end is exclusive
    frames: dict[str, pd.DataFrame] = {}
    todo = []
    for t in tickers:
        f = cache / f"{t}_{snapshot}.csv"
        if f.exists():
            frames[t] = pd.read_csv(f, index_col=0, parse_dates=True)
        else:
            todo.append(t)
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        log(f"prices: downloading {i + len(chunk)}/{len(todo)} new tickers")
        data = _retry(lambda: yf.download(chunk, start=start, end=end, auto_adjust=False, group_by="ticker",
                                          threads=True, progress=False), f"prices batch {i}")
        for t in chunk:
            df = _ohlcv_for(data, t) if data is not None and not data.empty else None
            if df is None or df.empty:
                log(f"prices: no data for {t}")
                continue
            df = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(snapshot))]
            df.to_csv(cache / f"{t}_{snapshot}.csv")
            frames[t] = df
        time.sleep(1.0)
    return frames


EARNINGS_COLUMNS = ["date", "timing", "eps_estimate", "eps_actual", "surprise_pct"]


def announcement_timing(timestamps: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Split yfinance earnings timestamps into the New York calendar date and a timing label:
    BMO (before the open), DMH (during market hours), AMC (after the close) or unknown (no time of day)."""
    ts = pd.DatetimeIndex(timestamps)
    ts = ts.tz_convert("America/New_York") if ts.tz is not None else ts
    minutes = ts.hour * 60 + ts.minute
    timing = np.where(minutes == 0, "unknown",
                      np.where(minutes < 9 * 60 + 30, "BMO", np.where(minutes >= 16 * 60, "AMC", "DMH")))
    return ts.tz_localize(None).normalize() if ts.tz is not None else ts.normalize(), timing


def fetch_earnings(tickers: list[str], snapshot: str, cache: Path, limit: int = 60) -> pd.DataFrame:
    """Long table: symbol, date, timing, eps_estimate, eps_actual, surprise_pct (past and upcoming announcements)."""
    import yfinance as yf

    rows = []
    for n, t in enumerate(tickers, 1):
        f = cache / f"earnings_{t}_{snapshot}.csv"
        if f.exists():
            df = pd.read_csv(f, parse_dates=["date"])
        else:
            try:
                raw = _retry(lambda: yf.Ticker(t).get_earnings_dates(limit=limit), f"earnings {t}", attempts=3)
            except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the build
                log(f"earnings: {t} failed ({exc})")
                raw = None
            if raw is None or raw.empty:
                df = pd.DataFrame(columns=EARNINGS_COLUMNS)
            else:
                raw = raw.rename(columns={"EPS Estimate": "eps_estimate", "Reported EPS": "eps_actual", "Surprise(%)": "surprise_pct"})
                days, timing = announcement_timing(pd.DatetimeIndex(raw.index))
                df = pd.DataFrame({
                    "date": days, "timing": timing,
                    "eps_estimate": pd.to_numeric(raw.get("eps_estimate", np.nan), errors="coerce"),
                    "eps_actual": pd.to_numeric(raw.get("eps_actual", np.nan), errors="coerce"),
                    "surprise_pct": pd.to_numeric(raw.get("surprise_pct", np.nan), errors="coerce"),
                }).drop_duplicates("date").sort_values("date")
            df.to_csv(f, index=False)
            time.sleep(0.5)
        rows.append(df.assign(symbol=t))
        if n % 50 == 0:
            log(f"earnings: {n}/{len(tickers)} tickers")
    if not rows:
        return pd.DataFrame(columns=["symbol", *EARNINGS_COLUMNS])
    out = pd.concat(rows, ignore_index=True)
    out["timing"] = out["timing"].fillna("unknown")
    return out


def fetch_fred(series: list[str], start: str, snapshot: str, cache: Path) -> dict[str, pd.Series]:
    """FRED series through the public CSV endpoint (no API key), cached per series and snapshot."""
    out = {}
    for sid in series:
        f = cache / f"fred_{sid}_{snapshot}.csv"
        if not f.exists():
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}&coed={snapshot}"
            f.write_bytes(_retry(lambda: _http_get(url), f"fred {sid}"))
        raw = pd.read_csv(f)
        date_col = raw.columns[0]
        values = pd.to_numeric(raw[sid], errors="coerce")
        s = pd.Series(values.to_numpy(), index=pd.to_datetime(raw[date_col]))
        out[sid] = s[s.index <= pd.Timestamp(snapshot)].dropna()
    return out


# ------------------------------------------------------------------------------------------------- derive

def _first_trading_day_on_or_after(days: pd.DatetimeIndex, dates) -> np.ndarray:
    """Index positions in `days`; dates outside [days[0], days[-1]] get -1."""
    dates = pd.DatetimeIndex(dates)
    pos = days.searchsorted(dates, side="left")
    valid = (dates >= days[0]) & (pos < len(days))
    return np.where(valid, pos, -1)


def calendar_covariates(days: pd.DatetimeIndex, fomc_dates: list[str]) -> pd.DataFrame:
    """Known-in-advance calendar flags on the trading-day index."""
    cal = pd.DataFrame(index=days)
    cal["day_of_week"] = days.dayofweek.astype(np.float32)
    month = days.to_period("M").astype(str).to_numpy()
    quarter = days.to_period("Q").astype(str).to_numpy()
    month_end = np.append(month[:-1] != month[1:], days[-1] == days[-1] + pd.offsets.BMonthEnd(0))
    quarter_end = np.append(quarter[:-1] != quarter[1:], days[-1] == days[-1] + pd.offsets.BQuarterEnd(0))
    cal["month_end"] = month_end.astype(np.float32)
    cal["quarter_end"] = quarter_end.astype(np.float32)
    # Options expiry: third Friday of the month, or the last trading day before it if it is a holiday.
    third_fridays = []
    for y, m in sorted({(d.year, d.month) for d in days}):
        first = pd.Timestamp(y, m, 1)
        friday = first + timedelta(days=(4 - first.weekday()) % 7 + 14)
        if days[0] <= friday <= days[-1]:  # Outside the index the expiry is unknown, not the edge day.
            third_fridays.append(friday)
    opex = np.zeros(len(days), dtype=np.float32)
    if third_fridays:
        pos = days.searchsorted(pd.DatetimeIndex(third_fridays), side="right") - 1
        opex[np.unique(pos[pos >= 0])] = 1.0
    cal["opex"] = opex
    cal["triple_witching"] = (opex * days.month.isin([3, 6, 9, 12])).astype(np.float32)
    fomc = np.zeros(len(days), dtype=np.float32)
    pos = _first_trading_day_on_or_after(days, fomc_dates)
    fomc[pos[pos >= 0]] = 1.0  # A decision on a non-trading day (2020-03-15) counts on the next session.
    cal["fomc"] = fomc
    return cal


def earnings_covariates(days: pd.DatetimeIndex, dates: pd.DataFrame, window: int = 1,
                        max_days_ahead: int = MAX_DAYS_AHEAD) -> pd.DataFrame:
    """Per-ticker earnings columns on the trading-day index.

    earnings_day       first trading day on or after the announcement date
    earnings_reaction  first session that can trade on the news: the same day for BMO / DMH / unknown timing,
                       the next trading day for AMC announcements
    earnings_window    earnings_day +- `window` trading days (absorbs remaining timing uncertainty)
    days_to_earnings   trading days until the next earnings_day, clipped at `max_days_ahead`; announcements after
                       the last index day (upcoming dates known at the snapshot) count through weekdays
    eps_surprise_pct   surprise % on the reaction day (past-only: known once the market can trade on it), else 0
    """
    n = len(days)
    out = pd.DataFrame({
        "earnings_day": np.zeros(n, np.float32), "earnings_reaction": np.zeros(n, np.float32),
        "earnings_window": np.zeros(n, np.float32), "days_to_earnings": np.full(n, float(max_days_ahead), np.float32),
        "eps_surprise_pct": np.zeros(n, np.float32),
    }, index=days)
    if dates is None or dates.empty:
        return out
    dates = dates.dropna(subset=["date"]).sort_values("date")
    ann = pd.DatetimeIndex(dates["date"])
    timing = dates["timing"].fillna("unknown").to_numpy() if "timing" in dates else np.full(len(dates), "unknown")
    surprise = pd.to_numeric(dates["surprise_pct"], errors="coerce").to_numpy(dtype=float)

    pos = _first_trading_day_on_or_after(days, ann)
    inside = pos >= 0
    for d, p, t, s in zip(ann[inside], pos[inside], timing[inside], surprise[inside]):
        out.iloc[p, out.columns.get_loc("earnings_day")] = 1.0
        out.iloc[max(0, p - window):min(n, p + window + 1), out.columns.get_loc("earnings_window")] = 1.0
        # After-close news on a trading day trades next session; news on a non-trading day already maps forward.
        reaction = p + 1 if (t == "AMC" and days[p] == d) else p
        if reaction < n:
            out.iloc[reaction, out.columns.get_loc("earnings_reaction")] = 1.0
            if np.isfinite(s):
                out.iloc[reaction, out.columns.get_loc("eps_surprise_pct")] = float(s)

    # Countdown to the next announcement. Dates after the index (upcoming, already published) count weekdays.
    future = ann[ann > days[-1]]
    next_pos = np.full(n, n + max_days_ahead, dtype=float)
    if len(future):
        next_pos[:] = (n - 1) + np.busday_count(days[-1].date(), future[0].date())
    for p in sorted(pos[inside], reverse=True):
        next_pos[:p + 1] = p
    out["days_to_earnings"] = np.minimum(next_pos - np.arange(n), max_days_ahead).astype(np.float32)
    return out


def derive_targets(px: pd.DataFrame) -> pd.DataFrame:
    """Candidate targets from OHLCV. Everything at index t uses data up to and including t."""
    d = pd.DataFrame(index=px.index)
    d["close"] = px["close"]
    d["adj_close"] = px["adj_close"]
    d["volume"] = px["volume"]
    d["log_volume"] = np.log1p(px["volume"])
    d["dollar_volume"] = px["volume"] * px["close"]
    d["log_return"] = np.log(px["adj_close"]).diff()
    d["abs_return"] = d["log_return"].abs()
    with np.errstate(divide="ignore", invalid="ignore"):
        gk = 0.5 * np.log(px["high"] / px["low"]) ** 2 - (2 * np.log(2) - 1) * np.log(px["close"] / px["open"]) ** 2
    d["rv_gk"] = np.sqrt(gk.clip(lower=0) * TRADING_DAYS)                      # annualised Garman-Klass vol, daily
    d["rv21"] = d["log_return"].rolling(21).std() * np.sqrt(TRADING_DAYS)       # trailing 21-day realised vol
    return d.replace([np.inf, -np.inf], np.nan)


def macro_covariates(days: pd.DatetimeIndex, fred: dict[str, pd.Series]) -> pd.DataFrame:
    """FRED series on the trading-day index without look-ahead (see FRED_SERIES for the publication rule)."""
    out = pd.DataFrame(index=days)
    for sid, (column, kind) in FRED_SERIES.items():
        s = fred.get(sid)
        if s is None or s.empty:
            out[column] = np.float32(np.nan)
            continue
        if kind == "daily":
            values = s.reindex(days.union(s.index)).ffill().reindex(days).shift(1)   # published next business day
        else:
            available = s.copy()
            available.index = available.index + pd.offsets.MonthBegin(1)            # usable from the next month
            values = available.reindex(days.union(available.index)).ffill().reindex(days)
        out[column] = values.astype(np.float32)
    return out


def sentiment_covariate(days: pd.DatetimeIndex, sentiment: pd.DataFrame | None, symbol: str) -> np.ndarray:
    """Per-ticker daily news-sentiment score from an optional CSV (date, symbol, score); NaN where absent.
    A score dated d must summarise news available by the close of d."""
    if sentiment is None or sentiment.empty:
        return np.full(len(days), np.nan, np.float32)
    s = sentiment[sentiment["symbol"] == symbol]
    series = pd.Series(s["score"].to_numpy(dtype=float), index=pd.DatetimeIndex(s["date"]))
    series = series.groupby(level=0).mean()
    return series.reindex(days).to_numpy(dtype=np.float32)


def build_items(prices: dict[str, pd.DataFrame], constituents: pd.DataFrame, market: dict[str, pd.DataFrame],
                sector_etfs: dict[str, pd.DataFrame], earnings: pd.DataFrame, fomc_dates: list[str],
                min_days: int, fred: dict[str, pd.Series] | None = None,
                sentiment: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DatetimeIndex, dict]:
    """Assemble the item frame (the only place that knows the output schema) and a data-quality report."""
    days = pd.DatetimeIndex(market["spx"].index)                              # common trading-day index
    cal = calendar_covariates(days, fomc_dates)
    macro = macro_covariates(days, fred or {})
    vix = market["vix"]["close"].reindex(days).ffill().astype(np.float32)
    spx_ret = np.log(market["spx"]["adj_close"]).diff().reindex(days).astype(np.float32)
    etf_ret = {s: np.log(df["adj_close"]).diff().reindex(days).astype(np.float32) for s, df in sector_etfs.items()}
    meta = constituents.set_index("symbol")

    rows, dropped, quality = [], {}, {}
    for symbol in sorted(prices):
        px = prices[symbol]
        if symbol not in meta.index:
            dropped[symbol] = "not in constituents"
            continue
        px = px.reindex(days)
        valid = int(px["close"].notna().sum())
        if valid < min_days:
            dropped[symbol] = f"only {valid} valid days (< {min_days})"
            continue
        tgt = derive_targets(px)
        if tgt["log_volume"].notna().sum() == 0:
            dropped[symbol] = "no volume"
            continue
        first_valid = px["close"].first_valid_index()
        live = px.loc[first_valid:]
        ratio_jump = np.abs(np.diff(np.log((live["adj_close"] / live["close"]).dropna().to_numpy())))
        quality[symbol] = {
            "valid_days": valid,
            "missing_days_after_first_valid": int(live["close"].isna().sum()),
            "zero_volume_days": int((live["volume"] == 0).sum()),
            "adjustment_jumps_over_10pct": int((ratio_jump > np.log(1.1)).sum()),
        }
        sector = meta.loc[symbol, "sector"]
        etf = SECTOR_ETF.get(sector)
        sym_earnings = earnings[earnings["symbol"] == symbol] if not earnings.empty else earnings
        earn = earnings_covariates(days, sym_earnings)
        row = {
            "id": symbol, "timestamp": days.to_numpy(),
            "sector": sector, "industry": meta.loc[symbol, "industry"],
            "market_cap": float(meta.loc[symbol, "market_cap"]) if pd.notna(meta.loc[symbol, "market_cap"]) else np.nan,
            "index_weight": float(meta.loc[symbol, "index_weight"]) if pd.notna(meta.loc[symbol, "index_weight"]) else np.nan,
            "first_valid": first_valid,
        }
        for c in tgt.columns:
            row[c] = tgt[c].to_numpy(dtype=np.float32)
        row["vix_close"] = vix.to_numpy()
        row["spx_log_return"] = spx_ret.to_numpy()
        row["sector_etf_log_return"] = etf_ret[etf].to_numpy() if etf in etf_ret else np.full(len(days), np.nan, np.float32)
        for c in macro.columns:
            row[c] = macro[c].to_numpy(dtype=np.float32)
        row["news_sentiment"] = sentiment_covariate(days, sentiment, symbol)
        for c in earn.columns:
            row[c] = earn[c].to_numpy(dtype=np.float32)
        for c in cal.columns:
            row[c] = cal[c].to_numpy(dtype=np.float32)
        rows.append(row)
    items = pd.DataFrame(rows)
    report = {"dropped": dropped, "per_ticker": quality,
              "summary": {"tickers_with_zero_volume_days": sum(q["zero_volume_days"] > 0 for q in quality.values()),
                          "tickers_with_missing_days": sum(q["missing_days_after_first_valid"] > 0 for q in quality.values()),
                          "tickers_with_adjustment_jumps": sum(q["adjustment_jumps_over_10pct"] > 0 for q in quality.values())}}
    return items, days, report


# ------------------------------------------------------------------------------------------------- load (notebook side)

KNOWN_FUTURE = ["earnings_day", "earnings_reaction", "earnings_window", "days_to_earnings", "opex", "triple_witching",
                "fomc", "month_end", "quarter_end", "day_of_week"]
PAST_ONLY = ["vix_close", "spx_log_return", "sector_etf_log_return", "us10y_yield", "yield_curve_10y2y",
             "consumer_sentiment", "news_sentiment", "eps_surprise_pct", "log_return", "abs_return", "rv_gk", "rv21",
             "volume", "log_volume", "dollar_volume", "close", "adj_close"]
STATIC = ["sector", "industry", "market_cap", "index_weight", "first_valid"]


def load_finance(path: str | Path, complete_from: str | None = None) -> pd.DataFrame:
    """Load the parquet into the fev-bench item layout (one row per ticker, numpy arrays per column).

    complete_from: keep only tickers whose history starts on or before this date (drops recent listings)."""
    items = pd.read_parquet(path)
    array_cols = [c for c in items.columns if c not in STATIC + ["id"]]
    for c in array_cols:
        items[c] = items[c].apply(lambda v: np.asarray(v, dtype="datetime64[ns]" if c == "timestamp" else np.float32))
    items["first_valid"] = pd.to_datetime(items["first_valid"])
    if complete_from is not None:
        items = items[items["first_valid"] <= pd.Timestamp(complete_from)]
    return items.reset_index(drop=True)


def make_covariate_input(row: pd.Series, target: str, history: int, horizon: int, origin: int,
                         past_only: list[str] = (), known_future: list[str] = ()) -> dict:
    """One `predict_quantiles` dict for the window ending at index `origin` (exclusive), in the notebooks' format."""
    h0, h1, f1 = origin - history, origin, origin + horizon
    item = {"target": row[target][h0:h1]}
    past = {c: row[c][h0:h1] for c in list(past_only) + list(known_future)}
    future = {c: row[c][h1:f1] for c in known_future}
    if past:
        item["past_covariates"] = past
    if future:
        item["future_covariates"] = future
    return item


# ------------------------------------------------------------------------------------------------- main

def write_outputs(items: pd.DataFrame, days: pd.DatetimeIndex, report: dict, earnings: pd.DataFrame,
                  out_dir: Path, stem: str, manifest_extra: dict) -> Path:
    parquet = out_dir / f"{stem}.parquet"
    items.to_parquet(parquet, index=False)
    if not earnings.empty:
        last = days[-1]
        upcoming = earnings[earnings["date"] > last].sort_values(["date", "symbol"])
        upcoming.to_csv(out_dir / f"{stem}_upcoming_earnings.csv", index=False)
    manifest = {
        **manifest_extra,
        "tickers": int(len(items)), "trading_days": int(len(days)),
        "first_day": str(days[0].date()), "last_day": str(days[-1].date()),
        "sectors": items["sector"].value_counts().sort_index().to_dict() if len(items) else {},
        "earnings_rows": int(len(earnings)),
        "earnings_timing": earnings["timing"].value_counts().to_dict() if "timing" in earnings and len(earnings) else {},
        "sha256": hashlib.sha256(parquet.read_bytes()).hexdigest(),
        "columns": {"static": STATIC, "known_future": KNOWN_FUTURE, "past_only": PAST_ONLY},
        "quality": report,
    }
    (out_dir / f"{stem}_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return parquet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=date.today().isoformat(), help="last date included (YYYY-MM-DD); names the output")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--out", default="data")
    ap.add_argument("--cache", default="data/cache")
    ap.add_argument("--companies-csv", default=None, help="Kaggle sp500_companies.csv instead of Wikipedia")
    ap.add_argument("--tickers", default=None, help="comma-separated subset")
    ap.add_argument("--max-tickers", type=int, default=None, help="first N constituents (quick test)")
    ap.add_argument("--min-days", type=int, default=250, help="drop tickers with fewer valid days")
    ap.add_argument("--skip-earnings", action="store_true", help="skip the per-ticker earnings calendar (slow)")
    ap.add_argument("--skip-fred", action="store_true", help="skip the FRED macro / sentiment series")
    ap.add_argument("--sentiment-csv", default=None, help="optional per-ticker daily sentiment: date, symbol, score")
    ap.add_argument("--fomc-csv", default=None, help="CSV with a 'date' column overriding the built-in FOMC list")
    args = ap.parse_args()

    out_dir, cache = Path(args.out), Path(args.cache)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    constituents = fetch_constituents(args.companies_csv)
    tickers = list(constituents["symbol"])
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]
    log(f"{len(tickers)} tickers, {args.start} .. {args.snapshot}")

    market = fetch_prices(list(MARKET_TICKERS.values()), args.start, args.snapshot, cache)
    missing = [v for v in MARKET_TICKERS.values() if v not in market]
    if missing:
        sys.exit(f"market series missing: {missing}")
    market = {k: market[v] for k, v in MARKET_TICKERS.items()}
    sector_etfs = fetch_prices(sorted(set(SECTOR_ETF.values())), args.start, args.snapshot, cache)
    prices = fetch_prices(tickers, args.start, args.snapshot, cache)
    earnings = (pd.DataFrame(columns=["symbol", *EARNINGS_COLUMNS])
                if args.skip_earnings else fetch_earnings(sorted(prices), args.snapshot, cache))
    fred = {} if args.skip_fred else fetch_fred(list(FRED_SERIES), args.start, args.snapshot, cache)
    sentiment = pd.read_csv(args.sentiment_csv, parse_dates=["date"]) if args.sentiment_csv else None
    fomc_dates = list(pd.read_csv(args.fomc_csv)["date"].astype(str)) if args.fomc_csv else FOMC_DATES

    items, days, report = build_items(prices, constituents, market, sector_etfs, earnings, fomc_dates,
                                      args.min_days, fred=fred, sentiment=sentiment)
    stem = f"finance_sp500_{args.snapshot}"
    parquet = write_outputs(items, days, report, earnings, out_dir, stem, {
        "snapshot": args.snapshot, "start": args.start, "built_on": date.today().isoformat(),
        "requested_tickers": len(tickers), "fomc_source": args.fomc_csv or "built-in",
        "fred": "skipped" if args.skip_fred else sorted(FRED_SERIES), "sentiment_source": args.sentiment_csv or "none",
    })
    log(f"wrote {parquet} ({len(items)} tickers x {len(days)} days, {len(report['dropped'])} dropped) and manifest")


if __name__ == "__main__":
    main()
