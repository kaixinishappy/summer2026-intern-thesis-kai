"""
make_charts.py
==============
Produces the three charts that carry the written verdict. Run build_index.py
first (it writes output/fdi.csv and output/break_results.json).

    python build_index.py
    python make_charts.py

    python build_index.py --synthetic   # demo mode, placeholder data
    python make_charts.py --synthetic   # reads output/*_synthetic.*, writes
                                         # charts/*_synthetic.png, watermarked

Charts
------
1. two_wave_index.png   -- Wave 1 / Wave 2 sub-indices + composite FDI, with
                           detected break points annotated. The headline chart.
2. momentum_handoff.png -- 12-month momentum of each wave; shows Wave 1 rolling
                           over as Wave 2 accelerates (the 'handoff').
3. incumbent_response.png -- raw fintech-vs-legacy market strength (Wave 1 proxy)
                           against EDGAR AI-language intensity (Wave 2 proxy),
                           dual axis: 'are incumbents actually responding?'
"""

import argparse
import json
import os

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# --- paths (edit if your build_index.py writes elsewhere) ---
IN_DIR = os.path.join(HERE, "output")   # where fdi.csv + break_results.json live
CHART_DIR = os.path.join(HERE, "charts") # where the PNGs are saved
os.makedirs(CHART_DIR, exist_ok=True)
OUT = IN_DIR  # backward-compat: load() reads from here

# muted, presentation-friendly palette
C_W1 = "#c0392b"    # wave 1  (warm red)
C_W2 = "#1f6feb"    # wave 2  (blue)
C_FDI = "#5c5c5c"   # composite (grey)
C_MKT = "#c0392b"
C_EDGAR = "#1f6feb"

plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
})


def load(suffix=""):
    df = pd.read_csv(os.path.join(OUT, f"fdi{suffix}.csv"), index_col=0, parse_dates=True)
    with open(os.path.join(OUT, f"break_results{suffix}.json")) as f:
        breaks = json.load(f)
    return df, breaks


def _annotate_breaks(ax, dates, color, label_prefix):
    for d in dates:
        ts = pd.Timestamp(d)
        ax.axvline(ts, color=color, ls="--", lw=1.1, alpha=0.7)
        ax.annotate(f"{label_prefix}\n{ts.strftime('%b %Y')}",
                    xy=(ts, ax.get_ylim()[1]), xytext=(4, -4),
                    textcoords="offset points", fontsize=8,
                    color=color, va="top", ha="left")


def _maybe_watermark(ax, breaks):
    if breaks.get("used_synthetic"):
        ax.text(0.99, 0.02, "SYNTHETIC DEMO DATA -- NOT A REAL RESULT",
                transform=ax.transAxes, ha="right", fontsize=8.5,
                color="#B03A2E", style="italic", fontweight="bold")


def chart_two_wave(df, breaks, suffix=""):
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(df.index, df["wave1"], color=C_W1, lw=2.2, label="Wave 1 sub-index (payments / neobanks)")
    ax.plot(df.index, df["wave2"], color=C_W2, lw=2.2, label="Wave 2 sub-index (AI-native finance)")
    ax.plot(df.index, df["FDI"], color=C_FDI, lw=1.6, ls=":", label="Composite FDI")

    _annotate_breaks(ax, breaks["series"]["wave1"]["break_dates"], C_W1, "W1 break")
    _annotate_breaks(ax, breaks["series"]["wave2"]["break_dates"], C_W2, "W2 break")

    ax.axhline(0, color="black", lw=0.6, alpha=0.4)
    ax.set_title("The Two Waves of Fintech Disruption", fontweight="bold", loc="left")
    ax.set_ylabel("Standardised index (z-score)")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _maybe_watermark(ax, breaks)
    fig.tight_layout()
    p = os.path.join(CHART_DIR, f"two_wave_index{suffix}.png")
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def chart_momentum(df, breaks, window=12, suffix=""):
    m1 = df["wave1"].diff(window)
    m2 = df["wave2"].diff(window)
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.plot(df.index, m1, color=C_W1, lw=2.2, label="Wave 1 momentum (12m)")
    ax.plot(df.index, m2, color=C_W2, lw=2.2, label="Wave 2 momentum (12m)")
    ax.fill_between(df.index, 0, m1, where=(m1 < 0), color=C_W1, alpha=0.10)
    ax.axhline(0, color="black", lw=0.7, alpha=0.5)
    ax.set_title("Momentum Handoff: Wave 1 Rolls Over as Wave 2 Accelerates",
                 fontweight="bold", loc="left")
    ax.set_ylabel("12-month change in sub-index")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _maybe_watermark(ax, breaks)
    fig.tight_layout()
    p = os.path.join(CHART_DIR, f"momentum_handoff{suffix}.png")
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def chart_incumbent(df, breaks, suffix=""):
    fig, ax1 = plt.subplots(figsize=(10, 5.4))
    ax1.plot(df.index, df["market_rel_strength"], color=C_MKT, lw=2.2)
    ax1.set_ylabel("Fintech / legacy relative strength", color=C_MKT)
    ax1.tick_params(axis="y", labelcolor=C_MKT)

    ax2 = ax1.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.plot(df.index, df["edgar_ai_intensity"], color=C_EDGAR, lw=2.2)
    ax2.set_ylabel("EDGAR AI-language intensity (per filing)", color=C_EDGAR)
    ax2.tick_params(axis="y", labelcolor=C_EDGAR)

    ax1.set_title("Are Incumbents Responding? Market Pressure vs. AI Language in Filings",
                  fontweight="bold", loc="left")
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _maybe_watermark(ax1, breaks)
    fig.tight_layout()
    p = os.path.join(CHART_DIR, f"incumbent_response{suffix}.png")
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true",
                    help="read output/*_synthetic.* instead of the real fdi.csv / "
                         "break_results.json, and write watermarked charts/*_synthetic.png")
    args = ap.parse_args()

    suffix = "_synthetic" if args.synthetic else ""
    df, breaks = load(suffix)
    paths = [chart_two_wave(df, breaks, suffix),
             chart_momentum(df, breaks, suffix=suffix),
             chart_incumbent(df, breaks, suffix)]
    for p in paths:
        print("saved", p)


if __name__ == "__main__":
    main()