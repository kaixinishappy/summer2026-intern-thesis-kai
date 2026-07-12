"""
collect_edgar_marketwide.py

Extends collect_edgar.py's per-company "agentic" / "ai_broad" filing counts
with a market-wide baseline: the same two queries, same form type (10-K),
same years, but across ALL SEC filers -- no CIK filter. Answers a question
the 5-company sample in collect_edgar.py can't: is "0 agentic mentions until
2026" a fact about JPM/HSBC/SOFI/PYPL/XYZ specifically, or a fact about the
entire market?

Run locally (needs open internet access to efts.sec.gov):

    python collect_edgar_marketwide.py

Outputs:
    data/raw/edgar_marketwide.csv   (year, query, total_filings -- market-wide)
    charts/edgar_marketwide.png     (5-company sample vs. market-wide, agentic query)

Synthetic demo mode (no internet needed, matches build_index.py/make_charts.py):

    python collect_edgar_marketwide.py --synthetic

Fabricates both the market-wide series and the 5-company sample with the same
near-zero-then-spike shape as the real data, entirely by construction -- NOT
evidence for or against the two-wave thesis, same caveat as build_index.py's
synthetic_sources(). Writes data/raw/edgar_marketwide_synthetic.csv and
charts/edgar_marketwide_synthetic.png (watermarked), and never touches the
real edgar_marketwide.csv / edgar_marketwide.png.
"""

import argparse
import os
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from collect_edgar import QUERIES, START_YEAR, END_YEAR, count_mentions

OUT_DIR_RAW = "data/raw"
OUT_DIR_CHARTS = "charts"
for d in (OUT_DIR_RAW, OUT_DIR_CHARTS):
    os.makedirs(d, exist_ok=True)

FORMS = "10-K"  # matches the form type used for all 5 sample companies except HSBC's 20-F

# NOTE: unscoped (no-CIK) queries are noticeably flakier than the per-company
# queries in collect_edgar.py -- observed both routine HTTP 500s (retried
# automatically below) AND, once, a 200 response with a spuriously-empty
# result (0 total) for a query that returned 3640+ on retry moments later.
# The retry logic here only catches non-200 failures, so a suspiciously low
# or zero count for a query that has nonzero counts in adjacent years is
# worth manually re-querying before trusting it -- don't take a market-wide
# 0 at face value the way you reasonably can for the 5-company sample.


def collect_marketwide(queries: dict, start_year: int, end_year: int) -> pd.DataFrame:
    rows = []
    for qkey, qstr in queries.items():
        print(f"Querying market-wide '{qkey}'...")
        for year in range(start_year, end_year + 1):
            count = count_mentions(None, FORMS, qstr, year)
            print(f"    {year}: {count}")
            rows.append({"year": year, "query": qkey, "total_filings": count})
            time.sleep(0.3)  # stay well under SEC's 10 req/sec limit
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Synthetic demo data -- opt-in only (--synthetic), never an automatic
# fallback. Mirrors build_index.py's synthetic_sources(): fabricates both
# series with the near-zero-then-spike shape baked in by construction, so the
# pipeline can be demoed with zero internet access. NOT evidence.
# ---------------------------------------------------------------------------

def synthetic_marketwide_and_sample(start_year: int = START_YEAR, end_year: int = END_YEAR,
                                    seed: int = 7):
    """Fabricate a (marketwide_df, sample_df) pair shaped like the real
    'near-zero for years, then a late spike' agentic-language evidence --
    entirely by construction, not derived from any real filings. Lets this
    script run and produce a chart with zero internet access."""
    rng = np.random.default_rng(seed)
    years = list(range(start_year, end_year + 1))
    companies = ["JPM", "HSBC", "SOFI", "PYPL", "XYZ"]

    mw_rows, smp_rows = [], []
    for year in years:
        late = year >= end_year - 1  # last two years "take off", like the real data
        mw_rows.append({"year": year, "query": "agentic",
                        "total_filings": int(rng.integers(80, 400)) if late else int(rng.integers(0, 6))})
        mw_rows.append({"year": year, "query": "ai_broad",
                        "total_filings": int(rng.integers(2000, 4000)) if late else int(rng.integers(200, 1500))})
        for ticker in companies:
            agentic_hit = late and rng.random() < 0.6
            smp_rows.append({"ticker": ticker, "year": year, "query": "agentic",
                             "mentions": 1 if agentic_hit else 0})
            smp_rows.append({"ticker": ticker, "year": year, "query": "ai_broad",
                             "mentions": int(rng.integers(0, 2))})

    return pd.DataFrame(mw_rows), pd.DataFrame(smp_rows)


def plot_comparison(marketwide: pd.DataFrame, sample: pd.DataFrame, out_path: str,
                    watermark: bool = False):
    """Agentic-query filing counts: the 5-company sample vs. every 10-K filer.

    Two panels sharing an x-axis (not a dual-axis overlay) since the two
    series are on wildly different scales -- market-wide 10-K filer count is
    in the thousands, the 5-company sample tops out in single digits.
    """
    mw = marketwide[marketwide["query"] == "agentic"].set_index("year")["total_filings"]
    smp = (sample[sample["query"] == "agentic"]
           .groupby("year")["mentions"].sum())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.bar(mw.index, mw.values, color="#4a3aa7", alpha=0.85)
    ax1.set_ylabel("Market-wide 10-K filings\n(all SEC filers)")
    ax1.set_title('"Agentic AI" language in SEC 10-K filings: 5-company sample vs. entire market',
                  fontweight="bold", loc="left", fontsize=12)
    ax1.grid(alpha=0.2, axis="y")

    ax2.bar(smp.index, smp.values, color="#e34948", alpha=0.85)
    ax2.set_ylabel("5-company sample\n(JPM/HSBC/SOFI/PYPL/XYZ)")
    ax2.set_xlabel("Year")
    ax2.grid(alpha=0.2, axis="y")

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
                    help="skip live EDGAR queries and use fabricated placeholder data "
                         "instead; writes data/raw/edgar_marketwide_synthetic.csv and "
                         "charts/edgar_marketwide_synthetic.png (watermarked) instead of "
                         "the real files, so it can never be mistaken for or overwrite "
                         "a real result")
    args = ap.parse_args()
    suffix = "_synthetic" if args.synthetic else ""

    if args.synthetic:
        print("*** SYNTHETIC PLACEHOLDER DATA -- NOT A REAL RESULT ***")
        print(f"=== Fabricating market-wide + 5-company EDGAR data, {START_YEAR}-{END_YEAR} ===")
        marketwide, sample = synthetic_marketwide_and_sample(START_YEAR, END_YEAR)
    else:
        print(f"=== Counting market-wide EDGAR 10-K filings, {START_YEAR}-{END_YEAR} ===")
        print(f"    queries: {list(QUERIES)}  forms: {FORMS}  (no CIK filter -- ALL filers)")
        marketwide = collect_marketwide(QUERIES, START_YEAR, END_YEAR)
        sample = None

    marketwide.to_csv(f"{OUT_DIR_RAW}/edgar_marketwide{suffix}.csv", index=False)
    print(f"\nSaved {len(marketwide)} rows to {OUT_DIR_RAW}/edgar_marketwide{suffix}.csv")

    totals = marketwide.groupby("query")["total_filings"].sum()
    print("\nTotal market-wide filings by query (all years, all filers):")
    for q in QUERIES:
        print(f"    {q:10s}: {int(totals.get(q, 0))}")

    if args.synthetic:
        print("\n=== Plotting sample vs. market-wide comparison (synthetic) ===")
        plot_comparison(marketwide, sample, f"{OUT_DIR_CHARTS}/edgar_marketwide{suffix}.png",
                        watermark=True)
    else:
        sample_path = f"{OUT_DIR_RAW}/edgar_mentions.csv"
        if os.path.exists(sample_path):
            print("\n=== Plotting sample vs. market-wide comparison ===")
            sample = pd.read_csv(sample_path)
            plot_comparison(marketwide, sample, f"{OUT_DIR_CHARTS}/edgar_marketwide.png")
        else:
            print(f"\nNOTE: {sample_path} not found -- run collect_edgar.py first "
                  "to get the comparison chart (market-wide data is still saved).")
