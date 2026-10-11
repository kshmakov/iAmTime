"""Offline tests for notebooks/build_finance_dataset.py (no network; synthetic OHLCV)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notebooks"))

import build_finance_dataset as bfd  # noqa: E402


def trading_days(start, end, holidays=()):
    days = pd.bdate_range(start, end)
    return days[~days.isin(pd.DatetimeIndex(holidays))]


def synthetic_ohlcv(days, seed=0, volume=1e6):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
    open_ = close * np.exp(rng.normal(0, 0.003, len(days)))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "adj_close": close,
                         "volume": volume * np.exp(rng.normal(0, 0.2, len(days)))}, index=days)


# ------------------------------------------------------------------------------------------------- calendar

def test_opex_shifted_before_good_friday_and_not_on_edge():
    # 2025-04-18 (third Friday of April) is Good Friday: expiry moves to Thursday 2025-04-17.
    days = trading_days("2025-04-01", "2025-05-06", holidays=["2025-04-18"])
    cal = bfd.calendar_covariates(days, [])
    opex_days = list(days[cal["opex"].to_numpy() == 1])
    assert pd.Timestamp("2025-04-17") in opex_days
    # May's third Friday (2025-05-16) is after the index end: no flag on the last day.
    assert cal["opex"].iloc[-1] == 0
    assert len(opex_days) == 1


def test_triple_witching_and_quarter_end_with_holiday():
    # 2024-03-29 is Good Friday, so the quarter's last trading day is 2024-03-28.
    days = trading_days("2024-03-01", "2024-04-30", holidays=["2024-03-29"])
    cal = bfd.calendar_covariates(days, [])
    assert cal.loc["2024-03-15", "triple_witching"] == 1          # third Friday of March
    assert cal.loc["2024-04-19", "opex"] == 1 and cal.loc["2024-04-19", "triple_witching"] == 0
    assert cal.loc["2024-03-28", "quarter_end"] == 1
    assert cal.loc["2024-03-28", "month_end"] == 1
    assert cal["quarter_end"].sum() == 1


def test_fomc_on_sunday_maps_to_next_session():
    days = trading_days("2020-03-02", "2020-03-20")
    cal = bfd.calendar_covariates(days, ["2020-03-03", "2020-03-15", "2019-12-11"])
    assert list(days[cal["fomc"].to_numpy() == 1]) == [pd.Timestamp("2020-03-03"), pd.Timestamp("2020-03-16")]


# ------------------------------------------------------------------------------------------------- earnings

def test_announcement_timing_labels():
    ts = pd.DatetimeIndex(["2024-01-25 07:00", "2024-01-25 16:05", "2024-01-25 12:00", "2024-01-25 00:00"]).tz_localize("America/New_York")
    dates, timing = bfd.announcement_timing(ts)
    assert list(timing) == ["BMO", "AMC", "DMH", "unknown"]
    assert (dates == pd.Timestamp("2024-01-25")).all()


def test_earnings_mapping_weekend_amc_and_out_of_range():
    days = trading_days("2024-01-02", "2024-02-29")
    dates = pd.DataFrame({
        "date": pd.to_datetime(["2023-12-01", "2024-01-13", "2024-01-25", "2024-02-08", "2024-03-05"]),
        "timing": ["BMO", "unknown", "AMC", "BMO", "AMC"],
        "surprise_pct": [1.0, 5.0, -3.0, np.nan, 2.0],
    })
    e = bfd.earnings_covariates(days, dates)
    # Before the first day: ignored (no flag on day 0).
    assert e["earnings_day"].iloc[0] == 0
    # Saturday 2024-01-13 -> Monday 2024-01-15 (the synthetic index has no holidays).
    assert e.loc["2024-01-15", "earnings_day"] == 1 and e.loc["2024-01-15", "earnings_reaction"] == 1
    assert e.loc["2024-01-15", "eps_surprise_pct"] == pytest.approx(5.0)
    # After-close on a trading day: reaction (and surprise) on the next session.
    assert e.loc["2024-01-25", "earnings_day"] == 1 and e.loc["2024-01-25", "earnings_reaction"] == 0
    assert e.loc["2024-01-26", "earnings_reaction"] == 1 and e.loc["2024-01-26", "eps_surprise_pct"] == pytest.approx(-3.0)
    assert e.loc["2024-01-25", "eps_surprise_pct"] == 0
    # NaN surprise -> 0, flag still set.
    assert e.loc["2024-02-08", "earnings_reaction"] == 1 and e.loc["2024-02-08", "eps_surprise_pct"] == 0
    # +-1 window around the announcement day.
    assert e.loc[["2024-02-07", "2024-02-08", "2024-02-09"], "earnings_window"].tolist() == [1, 1, 1]
    # Countdown: 0 on the day, 1 the day before; after the last in-range date it counts to the upcoming 2024-03-05.
    assert e.loc["2024-02-08", "days_to_earnings"] == 0 and e.loc["2024-02-07", "days_to_earnings"] == 1
    assert e["days_to_earnings"].iloc[-1] == np.busday_count(days[-1].date(), pd.Timestamp("2024-03-05").date())
    # Nothing after the index end is flagged.
    assert e["earnings_day"].sum() == 3


def test_earnings_empty_frame():
    days = trading_days("2024-01-02", "2024-01-31")
    e = bfd.earnings_covariates(days, pd.DataFrame(columns=["date", "timing", "surprise_pct"]))
    assert (e["earnings_day"] == 0).all() and (e["days_to_earnings"] == bfd.MAX_DAYS_AHEAD).all()


# ------------------------------------------------------------------------------------------------- targets and macro

def test_targets_have_no_look_ahead():
    days = trading_days("2024-01-02", "2024-06-28")
    px = synthetic_ohlcv(days)
    base = bfd.derive_targets(px)
    shocked = px.copy()
    shocked.iloc[100:] *= 3.0
    after = bfd.derive_targets(shocked)
    pd.testing.assert_frame_equal(base.iloc[:100], after.iloc[:100])
    assert base["rv21"].iloc[:21].isna().all() and base["rv21"].iloc[21:].notna().all()
    assert (base["abs_return"].dropna() >= 0).all()


def test_macro_publication_lags():
    days = trading_days("2024-01-02", "2024-03-29")
    daily = pd.Series(np.arange(len(days), dtype=float), index=days)
    monthly = pd.Series([50.0, 60.0, 70.0], index=pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]))
    macro = bfd.macro_covariates(days, {"DGS10": daily, "UMCSENT": monthly})
    assert np.isnan(macro["us10y_yield"].iloc[0]) and macro["us10y_yield"].iloc[5] == daily.iloc[4]
    assert np.isnan(macro.loc["2024-01-31", "consumer_sentiment"])           # January value not yet published
    assert macro.loc["2024-02-01", "consumer_sentiment"] == 50.0
    assert macro.loc["2024-03-01", "consumer_sentiment"] == 60.0
    assert macro["yield_curve_10y2y"].isna().all()                          # series not supplied -> NaN


# ------------------------------------------------------------------------------------------------- yfinance layouts

@pytest.mark.parametrize("ticker_level", [0, 1])
def test_ohlcv_extraction_from_multiindex(ticker_level):
    days = trading_days("2024-01-02", "2024-01-31")
    px = synthetic_ohlcv(days).rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close",
                                                "adj_close": "Adj Close", "volume": "Volume"})
    frames = {t: px for t in ["AAA", "BBB"]}
    wide = pd.concat(frames, axis=1)                                         # (ticker, field)
    if ticker_level == 1:
        wide = wide.swaplevel(0, 1, axis=1)                                  # (field, ticker)
    out = bfd._ohlcv_for(wide, "BBB")
    assert list(out.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    assert len(out) == len(days)
    assert bfd._ohlcv_for(wide, "CCC") is None


# ------------------------------------------------------------------------------------------------- assembly

@pytest.fixture()
def built(tmp_path):
    days = trading_days("2023-01-03", "2024-12-31")
    prices = {"BBB": synthetic_ohlcv(days, 1), "AAA": synthetic_ohlcv(days, 2),
              "NEW": synthetic_ohlcv(days[-100:], 3), "ZZZ": synthetic_ohlcv(days, 4)}
    constituents = pd.DataFrame({"symbol": ["AAA", "BBB", "NEW"], "sector": ["Energy", "Financials", "Energy"],
                                 "industry": ["Oil", "Banks", "Oil"], "market_cap": [1e9, np.nan, 2e9], "index_weight": np.nan})
    market = {"spx": synthetic_ohlcv(days, 5), "vix": synthetic_ohlcv(days, 6)}
    etfs = {"Energy": synthetic_ohlcv(days, 7)}
    earnings = pd.DataFrame({"symbol": ["AAA", "AAA"], "date": pd.to_datetime(["2024-04-25", "2024-07-25"]),
                             "timing": ["AMC", "BMO"], "surprise_pct": [4.0, -2.0]})
    items, idx, report = bfd.build_items(prices, constituents, market, etfs, earnings, bfd.FOMC_DATES, min_days=250)
    path = bfd.write_outputs(items, idx, report, earnings.assign(eps_estimate=np.nan, eps_actual=np.nan), tmp_path, "t",
                             {"snapshot": "2024-12-31"})
    return items, idx, report, path


def test_build_items_schema_and_drops(built):
    items, idx, report, _ = built
    assert list(items["id"]) == ["AAA", "BBB"]                               # sorted; NEW too short, ZZZ not a constituent
    assert report["dropped"]["ZZZ"] == "not in constituents" and "valid days" in report["dropped"]["NEW"]
    for column in bfd.KNOWN_FUTURE + bfd.PAST_ONLY:
        assert column in items.columns, column
        assert all(len(v) == len(idx) for v in items[column])
    assert items.loc[items["id"] == "BBB", "earnings_day"].iloc[0].sum() == 0
    assert np.isnan(items.loc[items["id"] == "BBB", "sector_etf_log_return"].iloc[0]).all()   # no Financials ETF supplied
    assert report["per_ticker"]["AAA"]["zero_volume_days"] == 0


def test_parquet_round_trip_and_inputs(built):
    items, idx, _, path = built
    loaded = bfd.load_finance(path, complete_from="2023-01-03")
    assert list(loaded["id"]) == ["AAA", "BBB"]
    assert loaded["log_volume"].iloc[0].dtype == np.float32 and loaded["timestamp"].iloc[0].dtype == "datetime64[ns]"
    assert pd.Timestamp(loaded["timestamp"].iloc[0][0]) == idx[0]
    row = loaded.iloc[0]
    item = bfd.make_covariate_input(row, "log_volume", history=252, horizon=20, origin=400,
                                    past_only=["vix_close"], known_future=["earnings_day", "opex"])
    assert item["target"].shape == (252,)
    assert set(item["past_covariates"]) == {"vix_close", "earnings_day", "opex"}
    assert all(v.shape == (252,) for v in item["past_covariates"].values())
    assert set(item["future_covariates"]) == {"earnings_day", "opex"}
    assert all(v.shape == (20,) for v in item["future_covariates"].values())
    manifest = path.with_name("t_manifest.json").read_text()
    assert '"sha256"' in manifest and '"quality"' in manifest
