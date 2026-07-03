"""
collect_trends.py

Part 2 of the FinTech Disruption Index project.
Pulls Google Trends search-interest data for two term groups:
  - Wave 1 terms: simple digital banking ("neobank", "mobile banking app"...)
  - Wave 2 terms: AI-native finance ("AI agent finance", "agentic AI banking"...)

Run locally (needs open internet access to trends.google.com, which a
sandboxed dev environment may block):

    pip install pytrends pandas numpy matplotlib
    python collect_trends.py

Outputs:
    data/raw/wave1_trends.csv
    data/raw/wave2_trends.csv
    data/processed/trends_yearly.csv
    charts/trends_comparison.png

Note: pytrends is an unofficial wrapper around Google Trends and does get
rate-limited (HTTP 429) if you hit it too often in a short window. This
script retries with backoff, but if you see repeated 429s, wait a few
minutes before re-running rather than hammering it.
"""

import os
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pytrends.request import TrendReq
from pytrends.exceptions import ResponseError

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------

# pytrends allows max 5 terms per request, and Google Trends returns
# *relative* interest (0-100) scaled within each request — so terms compared
# together must be pulled in the same call to be comparable to each other.
WAVE1_TERMS = ["neobank", "digital bank app", "mobile banking"]
WAVE2_TERMS = ["AI agent finance", "agentic AI banking", "autonomous wealth management"]

TIMEFRAME = "2018-01-01 2026-07-01"
OUT_DIR_RAW = "data/raw"
OUT_DIR_PROCESSED = "data/processed"
OUT_DIR_CHARTS = "charts"

for d in (OUT_DIR_RAW, OUT_DIR_PROCESSED, OUT_DIR_CHARTS):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# 2. Pull with retry/backoff (pytrends rate-limits aggressively)
# ---------------------------------------------------------------------------

def pull_trends(pytrends: TrendReq, terms: list, timeframe: str = TIMEFRAME,
                 max_retries: int = 4) -> pd.DataFrame:
    """Pulls weekly interest-over-time for up to 5 terms at once, with
    exponential backoff on 429 rate-limit responses."""
    for attempt in range(max_retries):
        try:
            pytrends.build_payload(terms, timeframe=timeframe)
            df = pytrends.interest_over_time()
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            return df
        except ResponseError as e:
            wait = 2 ** attempt * 30  # 30s, 60s, 120s, 240s — Google's 429 cooldown is often minutes, not seconds
            print(f"  Rate limited (attempt {attempt + 1}/{max_retries}): {e}")
            print(f"  Waiting {wait}s before retry...")
            time.sleep(wait)
    raise RuntimeError(f"Failed to pull trends for {terms} after {max_retries} retries")


# ---------------------------------------------------------------------------
# 3. Aggregate weekly -> yearly (mean interest per year, per term)
# ---------------------------------------------------------------------------

def to_yearly(df: pd.DataFrame, wave_label: str) -> pd.DataFrame:
    """Converts weekly interest-over-time into a long-format yearly average,
    tagged with which wave the terms belong to."""
    yearly = df.resample("YE").mean()
    long_df = yearly.reset_index().melt(id_vars="date", var_name="term", value_name="interest")
    long_df["year"] = long_df["date"].dt.year
    long_df["wave"] = wave_label
    return long_df[["year", "term", "wave", "interest"]]


# ---------------------------------------------------------------------------
# 4. Chart: wave1 vs wave2 average interest over time
# ---------------------------------------------------------------------------

def plot_trends_comparison(combined: pd.DataFrame, out_path: str):
    wave_avg = combined.groupby(["year", "wave"])["interest"].mean().unstack()

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(wave_avg.index, wave_avg["wave1"], label="Wave 1: Digital Banking terms",
            color="#4A5568", marker="o", linewidth=2)
    ax.plot(wave_avg.index, wave_avg["wave2"], label="Wave 2: AI-Native Finance terms",
            color="#38B2AC", marker="o", linewidth=2)

    ax.set_title("Search Interest Over Time: Wave 1 vs Wave 2 FinTech Terms\n(Google Trends, relative interest 0-100)", fontsize=13)
    ax.set_xlabel("Year")
    ax.set_ylabel("Average Relative Interest")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    print(f"Saved chart to {out_path}")


# ---------------------------------------------------------------------------
# 5. Run everything
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytrends = TrendReq(hl="en-US", tz=0)

    print("=== Pulling Wave 1 terms ===")
    wave1_weekly = pull_trends(pytrends, WAVE1_TERMS)
    wave1_weekly.to_csv(f"{OUT_DIR_RAW}/wave1_trends.csv")
    print(f"Saved {len(wave1_weekly)} weekly rows to {OUT_DIR_RAW}/wave1_trends.csv")

    time.sleep(5)  # space out requests to avoid rate limiting

    print("\n=== Pulling Wave 2 terms ===")
    wave2_weekly = pull_trends(pytrends, WAVE2_TERMS)
    wave2_weekly.to_csv(f"{OUT_DIR_RAW}/wave2_trends.csv")
    print(f"Saved {len(wave2_weekly)} weekly rows to {OUT_DIR_RAW}/wave2_trends.csv")

    print("\n=== Aggregating to yearly ===")
    wave1_yearly = to_yearly(wave1_weekly, "wave1")
    wave2_yearly = to_yearly(wave2_weekly, "wave2")
    combined = pd.concat([wave1_yearly, wave2_yearly], ignore_index=True)
    combined.to_csv(f"{OUT_DIR_PROCESSED}/trends_yearly.csv", index=False)
    print(f"Saved combined yearly data to {OUT_DIR_PROCESSED}/trends_yearly.csv")

    print("\n=== Plotting ===")
    plot_trends_comparison(combined, f"{OUT_DIR_CHARTS}/trends_comparison.png")

    print("\nDone. Next: collect_edgar.py for the AI-agent disclosure signal, "
          "then build_index.py to combine market + trends + EDGAR into the composite indices.")