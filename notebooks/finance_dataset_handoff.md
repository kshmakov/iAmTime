# `build_finance_dataset.py`: usage and development brief

Hand this file to Claude Code together with `build_finance_dataset.py` and one of the demo notebooks (e.g. `iamtime_rossmann_forecasting_demo.ipynb`) as the format reference.

## 1. Purpose

Produce a **frozen, reproducible S&P 500 dataset** in the exact item layout the iAmTime demo notebooks consume (the `autogluon/fev_datasets` layout: one row per series, equal-length arrays per column, static columns as scalars), so that the four forecasting demos (univariate, multivariate, covariates / what-if, in-context examples) can be run on finance data with a three-line change. fev-bench has no finance task; this script fills that gap.

Design choices that are deliberate, keep them:

- **Targets with structure, not prices.** Daily returns are near-martingales (MASE ≈ 1 for everything). The intended targets are `log_volume`, `rv_gk` / `rv21` (realised volatility) and `dollar_volume`; `log_return` is kept as a sanity row only.
- **Earnings announcements play the role of retail promotions**: `earnings_day` is the known-future flag, `eps_surprise_pct` is the "strength" for dose–response scenarios, `earnings_window` (±1 day) absorbs the before-open / after-close ambiguity.
- **Snapshot discipline**: `--snapshot YYYY-MM-DD` clips every download, names the output and goes into the manifest with a SHA-256; a rerun with the same arguments must reproduce the file up to upstream revisions.
- **Static metadata for grouping**: `sector`, `industry` (GICS), `market_cap`, `index_weight`, `first_valid` — for industry-based multivariate groups, sibling examples and cold-start selection.

## 2. How to use

```bash
pip install yfinance pandas pyarrow lxml
python build_finance_dataset.py --snapshot 2026-10-03 --start 2015-01-01 --out data/
# fast smoke build:
python build_finance_dataset.py --snapshot 2026-10-03 --max-tickers 60 --skip-earnings
# offline constituents with market cap / weight (Kaggle andrewmvd/sp-500-stocks):
python build_finance_dataset.py --snapshot 2026-10-03 --companies-csv sp500_companies.csv
```

Outputs in `--out`: `finance_sp500_<snapshot>.parquet`, `finance_sp500_<snapshot>_manifest.json`, `finance_sp500_<snapshot>_upcoming_earnings.csv`. Per-ticker downloads are cached in `--cache` (`<TICKER>_<snapshot>.csv`, `earnings_<TICKER>_<snapshot>.csv`), so interrupted builds resume.

Notebook side:

```python
from build_finance_dataset import load_finance, make_covariate_input, KNOWN_FUTURE, PAST_ONLY, STATIC
items = load_finance("data/finance_sp500_2026-10-03.parquet", complete_from="2015-01-05")   # complete series only
target = np.stack(items["log_volume"])                                                     # (tickers, days)
inputs = [make_covariate_input(row, "log_volume", history=252, horizon=20, origin=o,
                               past_only=["vix_close"], known_future=["earnings_day", "opex", "fomc"])
          for _, row in items.iterrows()]
```

`load_finance` returns the same frame shape as `load_dataset(path, config, split="train").to_pandas()` in the existing notebooks, so the per-notebook `load(config)` helper is the only thing to swap.

### Column reference

| Group | Columns | Notes |
|---|---|---|
| Keys / static | `id`, `timestamp[]`, `sector`, `industry`, `market_cap`, `index_weight`, `first_valid` | `first_valid` = first trading day with a price; use it for cold-start selection |
| Targets | `close`, `adj_close`, `volume`, `log_volume` (log1p), `dollar_volume`, `log_return`, `abs_return`, `rv_gk`, `rv21` | `rv_gk` annualised Garman–Klass from OHLC (daily, no look-ahead); `rv21` trailing 21-day std × √252 (first 21 values NaN) |
| Past-only covariates | `vix_close`, `spx_log_return`, `sector_etf_log_return`, `us10y_yield`, `yield_curve_10y2y`, `consumer_sentiment`, `news_sentiment`, `eps_surprise_pct` | sector ETF via the GICS→SPDR map `SECTOR_ETF`; FRED `DGS10` / `T10Y2Y` lagged one trading day (published next business day), `UMCSENT` usable from the first trading day of the following month; `news_sentiment` from `--sentiment-csv` (date, symbol, score), NaN otherwise; `eps_surprise_pct` is 0 except on the reaction day |
| Known-future covariates | `earnings_day`, `earnings_reaction`, `earnings_window`, `days_to_earnings` (clipped at 30), `opex`, `triple_witching`, `fomc`, `month_end`, `quarter_end`, `day_of_week` | all computed on the common trading-day index (the `^GSPC` calendar); `earnings_reaction` = first session that can trade on the news (next day for after-close announcements, from yfinance's timestamp; same day when the time is unknown); `days_to_earnings` also counts down to upcoming dates published before the snapshot; FOMC dates on non-trading days map to the next session |

All arrays are `float32`, aligned to the same `timestamp[]`; tickers listed after `--start` have NaN before `first_valid`. Tickers with fewer than `--min-days` valid days are dropped.

## 3. Module layout (for editing)

| Function | Role |
|---|---|
| `fetch_constituents(companies_csv)` | Wikipedia table or Kaggle CSV → `symbol, sector, industry, market_cap, index_weight`; normalises `BRK.B → BRK-B` and sector aliases |
| `fetch_prices(tickers, start, snapshot, cache)` | batched `yfinance.download`, per-ticker CSV cache, clipped to snapshot |
| `fetch_earnings(tickers, snapshot, cache)` | `Ticker.get_earnings_dates(limit=60)` per ticker → long table with past and upcoming dates and `timing` (BMO / DMH / AMC / unknown, from `announcement_timing`) |
| `fetch_fred(series, start, snapshot, cache)` | FRED CSV endpoint (no API key), cached per series; `macro_covariates` applies the publication lags |
| `calendar_covariates(days, fomc_dates)` | opex (third Friday, holiday-shifted back), triple witching, FOMC, month/quarter end, weekday |
| `earnings_covariates(days, dates)` | maps each announcement to the first trading day ≥ its date; flags, window, countdown, surprise |
| `derive_targets(px)` | the target columns above |
| `build_items(...)` | assembles the item frame and the data-quality report; the only place that knows the output schema |
| `write_outputs(...)` | parquet, manifest (with SHA-256 and the quality report) and upcoming-earnings CSV |
| `load_finance`, `make_covariate_input`, `KNOWN_FUTURE`, `PAST_ONLY`, `STATIC` | notebook-side helpers; keep their signatures stable |

Tested so far (synthetic OHLCV, no network): assembly, parquet round trip, holiday-shifted opex, Good-Friday quarter end, weekend earnings dates mapped to Monday, announcements after the snapshot excluded, NaN surprise handled, the input-dict shapes. **Not yet exercised: the live `yfinance` calls.** Run the smoke build first and fix whatever the current yfinance version returns differently (column names, time-zone-aware index, `get_earnings_dates` schema).

## 4. Known gaps and caveats

1. **FOMC dates are a built-in list (2015–2026)** typed from memory. Verify against federalreserve.gov or supply `--fomc-csv`; the manifest records which source was used.
2. **Before-open vs after-close** is not available from yfinance, so the reaction day can be one trading day after `earnings_day`. `earnings_window` covers ±1 day; a better source (see roadmap) would fix this.
3. **Survivorship bias**: only current constituents. Cold-start cases are recent index entrants, not true IPOs.
4. `--companies-csv` is needed for `market_cap` and `index_weight`; the Wikipedia route leaves them NaN.
5. yfinance terms are personal/research use; keep the parquet private or check terms before publishing data (figures are fine).
6. `days_to_earnings` after the last known announcement is clipped to 30; upcoming dates beyond the snapshot live only in `_upcoming_earnings.csv`.

## 5. Development roadmap (in priority order)

Each item lists a definition of done so it can be worked on independently.

1. **Live-run hardening.** Run `--max-tickers 60 --skip-earnings`, then a full build. Done when: the full build completes, the manifest shows ≥ 480 tickers, no ticker has an all-NaN target, and a second run with identical arguments produces the same SHA-256 (or a documented reason why not).
2. **Unit tests** (`tests/test_build_finance_dataset.py`, pytest). Port the synthetic smoke test: calendar flags on a fixed index, earnings mapping incl. weekends and NaN surprise, `build_items` dropping short tickers, round trip through `load_finance`, `make_covariate_input` shapes. Done when `pytest` passes without network.
3. **Finance demo notebook** `iamtime_finance_forecasting_demo.ipynb`, same three-part format and section numbering as the Rossmann notebook: §1 `log_volume` and `rv21` vs seasonal naive / random walk; §2 within-ticker (volume, vol, |return|) and same-industry triples + cross-industry random control; §3 calendar covariates (ablation: none → opex/FOMC/month-end → + earnings), earnings what-if, dose–response on `eps_surprise_pct`; §4 event-aligned examples (own last 4–8 earnings + industry peers), cold start (`first_valid` recent) with industry siblings, shuffled-futures control, k-shot curve. Reuse `scorecard`, `plot_ladder`, `plot_prompt_anatomy` from the existing notebooks. Done when every scorecard runs on ≥ 64 ticker-origin pairs and figures are saved to `docs/figures/`.
4. **Better earnings source.** Add a pluggable provider with announcement timing (BMO/AMC) and surprise history: candidates are the Kaggle earnings-calendar datasets, Nasdaq's earnings API, or FirstRate. Interface: `fetch_earnings(...) -> DataFrame[symbol, date, timing, eps_estimate, eps_actual, surprise_pct]`; `earnings_covariates` uses `timing` to pick the reaction day. Done when `earnings_window` can be narrowed to the exact reaction day for providers that give timing.
5. **Point-in-time constituents** to remove survivorship bias: ingest a historical membership file (Wikipedia "Selected changes" table or a Kaggle constituent-history dataset) and add `member_from`, `member_to` static columns; `load_finance(..., as_of=...)` filters membership at the forecast origin. Done when the 2020 universe differs from the 2026 universe in the expected way.
6. **Intraday option** (`--interval 1h`, yfinance gives 730 days): intraday volume curve as a target with strong daily seasonality; calendar covariates gain `minute_of_day`; opex/earnings flags extended to intraday. Done when the hourly parquet loads through the same `load_finance`.
7. **More macro covariates** from FRED (`pandas_datareader`): 10-year yield, policy-rate changes on `fomc` days (the "strength" of an FOMC event), CPI release days. Keep them in `PAST_ONLY` unless they are scheduled releases (then `KNOWN_FUTURE` flag + past-only value).
8. **fev task YAML export**: write `finance_tasks.yaml` entries (`dataset_path` = local parquet, `target`, `known_dynamic_columns`, `past_dynamic_columns`, `static_columns`, `horizon`, `seasonality` = 5 for daily, `num_windows`) so the dataset can be evaluated with the `fev` package next to fev-bench tasks. Done when `fev.Task` loads it and scores a seasonal-naive baseline.
9. **Data-quality report** in the manifest: per-ticker count of zero-volume days, split-adjustment sanity (`close`/`adj_close` ratio jumps), missing-day counts, and a list of tickers dropped and why.

## 6. Conventions

- Python ≥ 3.10, type hints, `log()` to stderr; no new heavy dependencies beyond `yfinance`, `pandas`, `pyarrow`, `lxml` (optional: `pandas_datareader` for FRED).
- Never introduce look-ahead into a target or past-only covariate: anything at index `t` may use data up to and including `t` only. Known-future columns must be deterministic calendar information or dates that are public before the forecast origin.
- Keep `build_items` as the single owner of the schema; add new columns there and in `KNOWN_FUTURE` / `PAST_ONLY` / `STATIC` in the same change.
- Every new covariate gets one line in the column reference above and a test.

## 7. Status (2026-10-06)

- Fixed in `build_finance_dataset.py`: announcements dated before the first day were flagged on day 0; a third Friday after the last day was flagged as opex on the last day; recent yfinance versions return MultiIndex columns even for one ticker (`_ohlcv_for` handles both layouts); no retry on Yahoo rate limits (`_retry`); output rows in download order (now sorted, so the SHA-256 is reproducible); `pd.read_html` on raw bytes (deprecated).
- Roadmap 2 (unit tests): done, `tests/test_build_finance_dataset.py`, offline.
- Roadmap 3 (demo notebook): done, `iamtime_finance_forecasting_demo.ipynb`; checked end to end on a synthetic stand-in, not yet on the real build.
- Roadmap 4 (earnings timing): partly done from yfinance timestamps (`earnings_reaction`); a provider with reliable BMO/AMC flags would still help where Yahoo gives no time.
- Roadmap 7 (macro covariates): done through the FRED CSV endpoint (no `pandas_datareader` needed).
- Roadmap 9 (data-quality report): done, `quality` in the manifest.
- Roadmap 1 (live run): **not yet run**; the build needs network access to Yahoo Finance, Wikipedia and FRED.
