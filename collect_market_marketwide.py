"""
collect_market_marketwide.py

Extends collect_market_data.py's 7-ticker fintech-vs-legacy price comparison
with a market-wide baseline: two sector ETFs -- FINX (Global X FinTech ETF,
a broad basket of fintech/payments companies) vs KBWB (Invesco KBW Bank ETF,
a broad basket of large-cap US banks) -- instead of the 7 hand-picked names.
Answers a question the 7-ticker sample in collect_market_data.py can't: is
"fintech underperformed banks since 2021" a fact about
JPM/HSBC/BCS/SOFI/NU/PYPL/XYZ specifically, or a fact about the fintech
sector broadly. Same "sample vs. market-wide" check
collect_edgar_marketwide.py already runs for the EDGAR signal.

Run locally (needs open internet access to Yahoo Finance):

    python collect_market_marketwide.py

Outputs:
    data/raw/market_marketwide.csv   (date, ticker[FINX/KBWB], close, indexed)
    charts/market_marketwide.png     (ETF indexed prices + 7-ticker sample vs.
                                       ETF relative-strength overlay)

Synthetic demo mode (no internet needed, matches build_index.py/make_charts.py):

    python collect_market_marketwide.py --synthetic

Fabricates the ETF series with the same rise-then-rollover shape as the real
data, entirely by construction -- NOT evidence for or against the two-wave
thesis, same caveat as build_index.py's synthetic_sources(). Writes
data/raw/market_marketwide_synthetic.csv and
charts/market_marketwide_synthetic.png (watermarked), and never touches the
real market_marketwide.csv / market_marketwide.png.
"""

import argparse
import os
import time

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

from collect_market_data import TICKERS, START_DATE, build_indexed_performance

OUT_DIR_RAW = "data/raw"
OUT_DIR_CHARTS = "charts"
for d in (OUT_DIR_RAW, OUT_DIR_CHARTS):
    os.makedirs(d, exist_ok=True)

ETFS = {
    "FINX": "Global X FinTech ETF",
    "KBWB": "Invesco KBW Bank ETF",
}
FREQ = "ME"  # month-end, matches build_index.py's resampling frequency

# The same legacy/fintech split collect_market_data.py's TICKERS dict encodes
# (traditional_bank vs. neobank + embedded_finance) -- kept local instead of
# importing build_index.py's LEGACY_TICKERS/FINTECH_TICKERS, since collector
# scripts here only depend on sibling collectors, never on build_index.py.
LEGACY_TICKERS = list(TICKERS["traditional_bank"])
FINTECH_TICKERS = list(TICKERS["neobank"]) + list(TICKERS["embedded_finance"])


# ---------------------------------------------------------------------------
# 1. Pull daily ETF prices
# ---------------------------------------------------------------------------

def pull_etf_prices(etfs: dict, start: str = START_DATE) -> pd.DataFrame:
    """Same shape as collect_market_data.py's pull_prices(), for the two ETFs."""
    frames = []
    for symbol, display_name in etfs.items():
        print(f"Pulling {symbol} ({display_name})...")
        hist = yf.download(symbol, start=start, auto_adjust=True, progress=False)
        if hist.empty:
            print(f"  Empty response for {symbol}, retrying once...")
            time.sleep(2)
            hist = yf.download(symbol, start=start, auto_adjust=True, progress=False)
        if hist.empty:
            print(f"  WARNING: no data returned for {symbol} after retry, skipping")
            continue
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        df = hist[["Close"]].rename(columns={"Close": "close"}).reset_index()
        df["ticker"] = symbol
        df["name"] = display_name
        frames.append(df)
        time.sleep(0.5)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 2. Relative strength: fintech basket / legacy basket, monthly
# ---------------------------------------------------------------------------

def relative_strength(prices_long: pd.DataFrame, group_a: list[str], group_b: list[str],
                      date_col: str = "Date", ticker_col: str = "ticker",
                      price_col: str = "close") -> pd.Series | None:
    """Equal-weight total-return basket ratio group_a / group_b, resampled
    monthly -- same construction as build_index.py's load_market(), so the
    7-ticker sample line and the ETF line are directly comparable in shape."""
    wide = prices_long.pivot_table(index=date_col, columns=ticker_col, values=price_col)
    wide = wide.resample(FREQ).last()

    def basket_index(tickers):
        cols = [t for t in tickers if t in wide.columns]
        if not cols:
            return None
        rets = wide[cols].pct_change().mean(axis=1)
        return (1 + rets.fillna(0)).cumprod() * 100

    a, b = basket_index(group_a), basket_index(group_b)
    if a is None or b is None:
        return None
    rel = (a / b).dropna()
    return 100 * rel / rel.iloc[0]


# ---------------------------------------------------------------------------
# Synthetic demo data -- opt-in only (--synthetic), never an automatic
# fallback. Mirrors build_index.py's synthetic_sources() rise-then-rollover
# shape so the pipeline can be demoed with zero internet access. NOT evidence.
# ---------------------------------------------------------------------------

def synthetic_etf_and_sample(start: str = START_DATE, seed: int = 7):
    """Fabricate (etf_prices_df, sample_ratio, etf_ratio) shaped like the real
    'fintech surges then rolls over vs. banks' story -- entirely by
    construction, not derived from any real prices."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, "2026-07-31", freq=FREQ)
    n = len(idx)
    t = np.arange(n)

    def logistic(t, mid, rate, top=1.0):
        return top / (1 + np.exp(-rate * (t - mid)))

    shape = logistic(t, mid=36, rate=0.15) - 0.35 * logistic(t, mid=72, rate=0.08)
    etf_ratio = pd.Series(100 * (1 + 0.9 * shape) + rng.normal(0, 2, n), index=idx)
    sample_ratio = pd.Series(100 * (1 + 1.1 * shape) + rng.normal(0, 3, n), index=idx)
    etf_ratio = 100 * etf_ratio / etf_ratio.iloc[0]
    sample_ratio = 100 * sample_ratio / sample_ratio.iloc[0]

    finx = pd.DataFrame({"Date": idx, "ticker": "FINX", "name": ETFS["FINX"],
                         "close": 20 * (1 + 0.7 * shape) + rng.normal(0, 0.5, n)})
    kbwb = pd.DataFrame({"Date": idx, "ticker": "KBWB", "name": ETFS["KBWB"],
                         "close": 40 * (1 + 0.2 * shape * -1 + 0.15 * t / n) + rng.normal(0, 0.5, n)})
    etf_prices = pd.concat([finx, kbwb], ignore_index=True)
    return etf_prices, sample_ratio, etf_ratio


# ---------------------------------------------------------------------------
# 3. Chart
# ---------------------------------------------------------------------------

def plot_comparison(indexed_etf: pd.DataFrame, sample_ratio, etf_ratio, out_path: str,
                    watermark: bool = False):
    """Two panels sharing an x-axis: ETF indexed prices for context (top),
    and the 7-ticker sample's relative-strength shape vs. the ETF basket's
    (bottom) -- does the 'fintech rose then rolled over vs. banks' story
    generalize past the 7 hand-picked names?"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    colors = {"FINX": "#1baf7a", "KBWB": "#2a78d6"}
    for ticker, group in indexed_etf.groupby("ticker"):
        ax1.plot(group["Date"], group["indexed"], label=f'{group["name"].iloc[0]} ({ticker})',
                 color=colors.get(ticker), lw=2.0)
    ax1.axhline(100, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax1.set_ylabel("Indexed price\n(start = 100)")
    ax1.set_title("Fintech vs. bank sector ETFs: does the 7-ticker sample generalize?",
                  fontweight="bold", loc="left", fontsize=12)
    ax1.legend(loc="upper left", fontsize=9, frameon=False)
    ax1.grid(alpha=0.2)

    if sample_ratio is not None:
        ax2.plot(sample_ratio.index, sample_ratio.values, color="#e34948", lw=2.0,
                 label="7-ticker sample (fintech / legacy)")
    ax2.plot(etf_ratio.index, etf_ratio.values, color="#4a3aa7", lw=2.0, ls="--",
             label="Sector ETFs (FINX / KBWB)")
    ax2.axhline(100, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax2.set_ylabel("Relative strength\n(rebased to 100)")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper left", fontsize=9, frameon=False)
    ax2.grid(alpha=0.2)

    if watermark:
        ax2.text(0.99, 0.04, "SYNTHETIC DEMO DATA -- NOT A REAL RESULT",
                 transform=ax2.transAxes, ha="right", fontsize=8.5,
                 color="#B03A2E", style="italic", fontweight="bold")

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    print(f"Saved chart to {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true",
                    help="skip live Yahoo Finance pulls and use fabricated placeholder "
                         "data instead; writes data/raw/market_marketwide_synthetic.csv "
                         "and charts/market_marketwide_synthetic.png (watermarked) "
                         "instead of the real files, so it can never be mistaken for or "
                         "overwrite a real result")
    args = ap.parse_args()
    suffix = "_synthetic" if args.synthetic else ""

    if args.synthetic:
        print("*** SYNTHETIC PLACEHOLDER DATA -- NOT A REAL RESULT ***")
        print("=== Fabricating ETF + 7-ticker sample comparison ===")
        etf_prices, sample_ratio, etf_ratio = synthetic_etf_and_sample()
    else:
        print(f"=== Pulling ETF price history: {list(ETFS)} ===")
        etf_prices = pull_etf_prices(ETFS)
        etf_ratio = relative_strength(etf_prices, ["FINX"], ["KBWB"])
        if etf_ratio is None:
            raise RuntimeError("Could not build FINX/KBWB relative strength -- check pull above.")

        sample_path = f"{OUT_DIR_RAW}/prices.csv"
        sample_ratio = None
        if os.path.exists(sample_path):
            sample_prices = pd.read_csv(sample_path, parse_dates=["Date"])
            sample_ratio = relative_strength(sample_prices, FINTECH_TICKERS, LEGACY_TICKERS)
        else:
            print(f"\nNOTE: {sample_path} not found -- run collect_market_data.py first "
                  "to get the sample-vs-ETF comparison chart (ETF data is still saved).")

    indexed_etf = build_indexed_performance(etf_prices)
    indexed_etf.to_csv(f"{OUT_DIR_RAW}/market_marketwide{suffix}.csv", index=False)
    print(f"\nSaved {len(indexed_etf)} rows to {OUT_DIR_RAW}/market_marketwide{suffix}.csv")

    print("\n=== Plotting sample vs. ETF comparison ===")
    plot_comparison(indexed_etf, sample_ratio, etf_ratio,
                    f"{OUT_DIR_CHARTS}/market_marketwide{suffix}.png",
                    watermark=args.synthetic)
