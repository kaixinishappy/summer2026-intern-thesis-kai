"""
collect_rates.py

Tests the "disruptors lost money when rates rose" claim in VERDICT.md Part 1
directly, instead of just asserting the 2022 timing from memory. Pulls the
effective Fed funds rate (monthly, no API key needed -- FRED's fredgraph.csv
endpoint is open) and overlays it against each company's actual net income
from collect_market_data.py's already-collected fundamentals.csv.

Run locally (needs open internet access to fred.stlouisfed.org; run
collect_market_data.py first so data/raw/fundamentals.csv exists):

    python collect_rates.py

Outputs:
    data/raw/fed_funds_rate.csv
    charts/rates_vs_netincome.png
"""

import os

import pandas as pd
import matplotlib.pyplot as plt

from collect_market_data import TICKERS

OUT_DIR_RAW = "data/raw"
OUT_DIR_CHARTS = "charts"
for d in (OUT_DIR_RAW, OUT_DIR_CHARTS):
    os.makedirs(d, exist_ok=True)

# FRED's plain CSV export -- no API key required, unlike the FRED REST API.
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS&cosd=2018-01-01"

# Same 7-color per-ticker palette used in collect_market_data.py's
# indexed_performance chart, so a reader sees the same company = same color
# across every chart in this project.
TICKER_ORDER = [sym for tickers in TICKERS.values() for sym in tickers]
TICKER_COLORS = dict(zip(
    TICKER_ORDER,
    ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4"],
))


def pull_fed_funds_rate() -> pd.DataFrame:
    df = pd.read_csv(FRED_CSV_URL)
    df.columns = ["date", "fed_funds_rate"]
    df["date"] = pd.to_datetime(df["date"])
    df["fed_funds_rate"] = pd.to_numeric(df["fed_funds_rate"], errors="coerce")
    return df.dropna()


def plot_rates_vs_netincome(rates: pd.DataFrame, fundamentals: pd.DataFrame, out_path: str):
    """Fed funds rate vs. per-company net income, in three stacked panels
    sharing an x-position (not a dual-axis overlay). Banks and disruptors get
    separate panels, not just separate colors on one axis: JPM's ~$58B net
    income vs. SOFI's -$320M are two orders of magnitude apart, so sharing a
    linear y-axis would flatten every disruptor into an unreadable band near
    zero -- exactly the kind of different-scale measure that belongs in small
    multiples, not one shared axis."""
    banks = {"JPM", "HSBC", "BCS"}
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(11, 10), sharex=False,
        gridspec_kw={"height_ratios": [0.8, 1, 1]})

    ax1.plot(rates["date"], rates["fed_funds_rate"], color="#2a78d6", lw=2.2)
    ax1.axvspan(pd.Timestamp("2022-01-01"), pd.Timestamp("2023-07-01"),
                color="#e34948", alpha=0.08)
    ax1.annotate("fastest hiking\ncycle in decades", xy=(pd.Timestamp("2022-06-01"), 4.5),
                fontsize=8.5, color="#B03A2E", ha="center")
    ax1.set_ylabel("Effective Fed\nfunds rate (%)")
    ax1.set_title("Rate-hike cycle vs. company net income: did disruptors get hit harder?",
                  fontweight="bold", loc="left", fontsize=12)
    ax1.grid(alpha=0.2)
    ax1.set_xlim(rates["date"].min(), rates["date"].max())

    for ticker, g in fundamentals.groupby("ticker"):
        g = g.sort_values("fiscal_year")
        ax = ax2 if ticker in banks else ax3
        ax.plot(g["fiscal_year"], g["net_income"] / 1e9, marker="o",
                color=TICKER_COLORS.get(ticker, "black"), lw=1.8,
                label=f"{g['name'].iloc[0]} ({ticker})")

    for ax, ylabel, title in (
        (ax2, "Net income ($B)", "Traditional banks"),
        (ax3, "Net income ($B)", "Neobanks + embedded finance (\"disruptors\")"),
    ):
        ax.axhline(0, color="black", lw=0.7, alpha=0.5)
        ax.axvspan(2022, 2023, color="#e34948", alpha=0.08)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontsize=10, color="#52514e")
        ax.legend(loc="upper left", fontsize=8, ncol=2)
        ax.grid(alpha=0.2)
    ax3.set_xlabel("Fiscal year")

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    print(f"Saved chart to {out_path}")


if __name__ == "__main__":
    print("=== Pulling effective Fed funds rate (FRED, no key needed) ===")
    rates = pull_fed_funds_rate()
    rates.to_csv(f"{OUT_DIR_RAW}/fed_funds_rate.csv", index=False)
    print(f"Saved {len(rates)} monthly rows to {OUT_DIR_RAW}/fed_funds_rate.csv")
    print(f"    2022 range: {rates[rates['date'].dt.year == 2022]['fed_funds_rate'].min():.2f}%"
          f" -> {rates[rates['date'].dt.year == 2022]['fed_funds_rate'].max():.2f}%")

    fundamentals_path = f"{OUT_DIR_RAW}/fundamentals.csv"
    if os.path.exists(fundamentals_path):
        print("\n=== Plotting rate cycle vs. net income ===")
        fundamentals = pd.read_csv(fundamentals_path)
        plot_rates_vs_netincome(rates, fundamentals, f"{OUT_DIR_CHARTS}/rates_vs_netincome.png")
    else:
        print(f"\nNOTE: {fundamentals_path} not found -- run collect_market_data.py first "
              "to get the comparison chart (rate data is still saved).")
