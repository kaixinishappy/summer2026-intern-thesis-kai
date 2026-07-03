"""
collect_market.py

Pulls stock price history + annual fundamentals for three groups of companies,
builds an indexed-performance comparison, and produces the first chart.

Outputs:
    data/raw/prices.csv
    data/raw/fundamentals.csv
    charts/indexed_performance.png
"""

import os
import time
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# 1. Config: which tickers represent which side of the disruption story
# ---------------------------------------------------------------------------

TICKERS = {
    "traditional_bank": {
        "JPM": "JPMorgan Chase",
        "HSBC": "HSBC",
        "BCS": "Barclays (ADR)",
    },
    "neobank": {
        "SOFI": "SoFi Technologies",
        "NU": "Nubank",
    },
    "embedded_finance": {
        "PYPL": "PayPal",
        "XYZ": "Block (Square/Cash App)",  # NYSE ticker changed from SQ to XYZ, effective Jan 22 2025
    },
}
# Note: Revolut and Monzo are privately held — no public ticker exists.
# Supplement those two manually from their published annual reports if you
# want them in the neobank group (see README section 3a).

START_DATE = "2018-01-01"
OUT_DIR_RAW = "data/raw"
OUT_DIR_CHARTS = "charts"

os.makedirs(OUT_DIR_RAW, exist_ok=True)
os.makedirs(OUT_DIR_CHARTS, exist_ok=True)


# ---------------------------------------------------------------------------
# 2. Pull daily price history for every ticker
# ---------------------------------------------------------------------------

def pull_prices(ticker_groups: dict, start: str = START_DATE) -> pd.DataFrame:
    """Downloads daily Close prices for every ticker, tags each row with its
    category (traditional_bank / neobank / embedded_finance), and returns one
    long-format dataframe: columns = [Date, ticker, category, close]."""
    frames = []
    for category, tickers in ticker_groups.items():
        for symbol, display_name in tickers.items():
            print(f"Pulling {symbol} ({display_name})...")
            try:
                hist = yf.download(symbol, start=start, auto_adjust=True, progress=False)
                if hist.empty:
                    # Yahoo occasionally returns an empty/"delisted" response as a
                    # transient hiccup rather than a real delisting. One retry
                    # after a short pause usually resolves it.
                    print(f"  Empty response for {symbol}, retrying once...")
                    time.sleep(2)
                    hist = yf.download(symbol, start=start, auto_adjust=True, progress=False)
                if hist.empty:
                    print(f"  WARNING: no data returned for {symbol} after retry, skipping")
                    continue
                # Recent yfinance returns MultiIndex columns like ('Close', 'JPM')
                # even for a single ticker. Flatten to level 0 so "Close" is a
                # plain column name and df["close"] returns a Series, not a
                # DataFrame with a stray ticker sub-column.
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.get_level_values(0)
                df = hist[["Close"]].rename(columns={"Close": "close"}).reset_index()
                df["ticker"] = symbol
                df["name"] = display_name
                df["category"] = category
                frames.append(df)
            except Exception as e:
                print(f"  ERROR pulling {symbol}: {e}")
            time.sleep(0.5)  # be polite to the API
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# 3. Pull annual fundamentals (net income) for the profitability comparison
# ---------------------------------------------------------------------------

def pull_fundamentals(ticker_groups: dict) -> pd.DataFrame:
    """Pulls annual net income from each company's income statement."""
    rows = []
    for category, tickers in ticker_groups.items():
        for symbol, display_name in tickers.items():
            try:
                t = yf.Ticker(symbol)
                fin = t.financials  # rows = line items, columns = fiscal years
                if fin.empty or "Net Income" not in fin.index:
                    print(f"  WARNING: no net income data for {symbol}")
                    continue
                net_income = fin.loc["Net Income"]
                for year, value in net_income.items():
                    rows.append({
                        "ticker": symbol,
                        "name": display_name,
                        "category": category,
                        "fiscal_year": pd.to_datetime(year).year,
                        "net_income": value,
                    })
            except Exception as e:
                print(f"  ERROR pulling fundamentals for {symbol}: {e}")
            time.sleep(0.5)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Build indexed performance (rebase every ticker to 100 at start date)
# ---------------------------------------------------------------------------

def build_indexed_performance(prices: pd.DataFrame) -> pd.DataFrame:
    """For each ticker, rebase its close price series to start at 100.
    This lets you compare companies at wildly different price levels
    (e.g. a $15 stock vs a $200 stock) on the same axis."""
    indexed = []
    for ticker, group in prices.groupby("ticker"):
        group = group.sort_values("Date").copy()
        base = group["close"].iloc[0]
        group["indexed"] = 100 * group["close"] / base
        indexed.append(group)
    return pd.concat(indexed, ignore_index=True)


# ---------------------------------------------------------------------------
# 5. Chart: indexed performance by category
# ---------------------------------------------------------------------------

def plot_indexed_performance(indexed_df: pd.DataFrame, out_path: str):
    category_colors = {
        "traditional_bank": "#4A5568",   # slate grey
        "neobank": "#38B2AC",            # teal
        "embedded_finance": "#DD6B20",   # orange
    }

    fig, ax = plt.subplots(figsize=(12, 7))

    for ticker, group in indexed_df.groupby("ticker"):
        category = group["category"].iloc[0]
        name = group["name"].iloc[0]
        ax.plot(
            group["Date"], group["indexed"],
            label=f"{name} ({ticker})",
            color=category_colors.get(category, "black"),
            alpha=0.85,
            linewidth=1.6,
        )

    ax.axhline(100, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.set_title("Indexed Stock Performance: Traditional Banks vs Neobanks vs Embedded Finance\n(rebased to 100 at start date)", fontsize=13)
    ax.set_xlabel("Date")
    ax.set_ylabel("Indexed Price (start = 100)")
    ax.legend(loc="upper left", fontsize=9, ncol=2)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    print(f"Saved chart to {out_path}")


# ---------------------------------------------------------------------------
# 6. Run everything
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Pulling price history ===")
    prices = pull_prices(TICKERS)
    prices.to_csv(f"{OUT_DIR_RAW}/prices.csv", index=False)
    print(f"Saved {len(prices)} price rows to {OUT_DIR_RAW}/prices.csv\n")

    print("=== Pulling fundamentals (net income) ===")
    fundamentals = pull_fundamentals(TICKERS)
    fundamentals.to_csv(f"{OUT_DIR_RAW}/fundamentals.csv", index=False)
    print(f"Saved {len(fundamentals)} fundamentals rows to {OUT_DIR_RAW}/fundamentals.csv\n")

    print("=== Building indexed performance ===")
    indexed = build_indexed_performance(prices)
    indexed.to_csv(f"{OUT_DIR_RAW}/indexed_performance.csv", index=False)

    print("=== Plotting ===")
    plot_indexed_performance(indexed, f"{OUT_DIR_CHARTS}/indexed_performance.png")

    print("\nDone. Next: run collect_trends.py and collect_edgar.py, then build_index.py to combine everything.")