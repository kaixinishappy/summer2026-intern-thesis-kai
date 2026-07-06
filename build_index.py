"""
build_index.py
==============
Builds the Fintech Disruption Index (FDI) from three collected data sources and
tests the "two-wave" thesis: that Wave 1 (payments / neobanks / embedded finance
taking share) has plateaued while Wave 2 (AI-native financial services) is only
now accelerating.

Pipeline
--------
1. Load three sources produced by the collector scripts:
     - collect_market_data.py -> data/raw/prices.csv (prices for legacy vs fintech tickers)
     - collect_trends.py -> data/raw/wave1_trends.csv, data/raw/wave2_trends.csv
     - collect_edgar.py  -> data/raw/edgar_mentions.csv (AI-language frequency in filings)
2. Resample everything to a common monthly frequency and z-score normalise.
3. Build two sub-indices:
     - Wave 1 sub-index  = fintech-vs-legacy market momentum + Wave-1 search interest
     - Wave 2 sub-index  = Wave-2 search interest + EDGAR AI-language intensity
4. Combine into the composite FDI (weight is configurable -> Streamlit slider later).
5. Run structural break detection (ruptures / PELT) on the *momentum* of each
   sub-index, plus a classical Chow test at the detected break for significance.
6. Save output/fdi.csv and output/break_results.json.

Requires the three collector scripts to have already been run -- fails loudly
(FileNotFoundError) if any of their output CSVs is missing. There is no
automatic fallback to synthetic data: an earlier version of this script fell
back silently whenever a real CSV was missing, which meant it ran on fake
data for a while without anyone noticing. Synthetic mode now only runs when
explicitly requested with --synthetic, and always writes to separate
output/*_synthetic.* files so it can never be mistaken for, or overwrite, a
real result.

Run:  python build_index.py               (real data only, fails if missing)
      python build_index.py --synthetic    (demo mode, placeholder data,
                                             writes output/fdi_synthetic.csv +
                                             output/break_results_synthetic.json)
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import ruptures as rpt
from scipy import stats

# --------------------------------------------------------------------------- #
# CONFIG  --  the only section you should normally need to touch
# --------------------------------------------------------------------------- #

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "output")

MARKET_CSV = os.path.join(DATA_DIR, "raw", "prices.csv")
WAVE1_TRENDS_CSV = os.path.join(DATA_DIR, "raw", "wave1_trends.csv")
WAVE2_TRENDS_CSV = os.path.join(DATA_DIR, "raw", "wave2_trends.csv")
EDGAR_CSV = os.path.join(DATA_DIR, "raw", "edgar_mentions.csv")

# Ticker baskets -- must match the categories collect_market_data.py actually
# pulled (see its TICKERS dict): traditional_bank vs. neobank + embedded_finance.
LEGACY_TICKERS = ["JPM", "HSBC", "BCS"]
FINTECH_TICKERS = ["SOFI", "NU", "PYPL", "XYZ"]

# Search-interest keyword groups -- must match the column names collect_trends.py
# actually wrote to wave1_trends.csv / wave2_trends.csv.
WAVE1_TREND_TERMS = ["neobank", "digital bank app", "mobile banking"]
WAVE2_TREND_TERMS = ["AI agent finance", "agentic AI banking",
                     "autonomous wealth management"]

# Composite weight: FDI = W1_WEIGHT * wave1 + (1 - W1_WEIGHT) * wave2.
# Exposed here so the Streamlit app can make it a live slider.
W1_WEIGHT = 0.5

# Resampling frequency for the combined index.
FREQ = "ME"  # month-end

# ruptures penalty for PELT (higher -> fewer breakpoints). Tune per data length.
PELT_PENALTY = 3.0

# Momentum window (months) used before break detection.
MOMENTUM_WINDOW = 12


# --------------------------------------------------------------------------- #
# LOADERS  --  flexible column detection so real CSVs drop in with few edits
# --------------------------------------------------------------------------- #

def _find_date_col(df: pd.DataFrame) -> str:
    for c in df.columns:
        if c.lower() in ("date", "datetime", "timestamp", "week", "month", "period"):
            return c
    # fall back to the first column that parses as datetime
    for c in df.columns:
        try:
            pd.to_datetime(df[c])
            return c
        except (ValueError, TypeError):
            continue
    raise ValueError("No date-like column found.")


def load_market(path: str) -> pd.Series:
    """Return a monthly 'fintech-minus-legacy' relative total-return momentum series.

    Expected long format: date, ticker, close  (adj_close also accepted).
    Falls back gracefully if columns differ.
    """
    df = pd.read_csv(path)
    date_col = _find_date_col(df)
    df[date_col] = pd.to_datetime(df[date_col])

    price_col = next((c for c in ("adj_close", "close", "price", "adjclose")
                      if c in [x.lower() for x in df.columns]), None)
    # normalise column case
    lower = {c.lower(): c for c in df.columns}
    price_col = lower.get(price_col) if price_col else None
    ticker_col = lower.get("ticker") or lower.get("symbol")
    if price_col is None or ticker_col is None:
        raise ValueError("market.csv needs ticker + price columns (long format).")

    df = df[[date_col, ticker_col, price_col]].dropna()
    wide = df.pivot_table(index=date_col, columns=ticker_col, values=price_col)
    wide = wide.resample(FREQ).last()

    def basket_return_index(tickers):
        cols = [t for t in tickers if t in wide.columns]
        if not cols:
            return None
        # equal-weight total-return index rebased to 100
        rets = wide[cols].pct_change().mean(axis=1)
        return (1 + rets.fillna(0)).cumprod() * 100

    legacy = basket_return_index(LEGACY_TICKERS)
    fintech = basket_return_index(FINTECH_TICKERS)
    if legacy is None or fintech is None:
        raise ValueError("Could not build both legacy and fintech baskets.")

    # relative strength: fintech basket / legacy basket
    rel = (fintech / legacy)
    rel.name = "market_rel_strength"
    return rel


def load_trends(path: str, terms: list[str], name: str) -> pd.Series:
    """Average monthly search interest across a group of keywords."""
    df = pd.read_csv(path)
    date_col = _find_date_col(df)
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)

    lower = {c.lower().strip(): c for c in df.columns}
    cols = [lower[t.lower()] for t in terms if t.lower() in lower]
    if not cols:
        raise ValueError(f"None of the {name} trend terms found in trends.csv.")
    s = df[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    s = s.resample(FREQ).mean()
    s.name = name
    return s


def load_edgar(path: str, query: str = "ai_broad") -> pd.Series:
    """AI-language intensity from filings.

    collect_edgar.py writes long format: one row per company/year/query
    (ticker, name, category, year, date, query, mentions). `query` selects
    which of the two collected series to use -- "ai_broad" ("artificial
    intelligence") is the workhorse baseline per collect_edgar.py's own
    docstring, since "agentic" is near-zero before ~2023 and too sparse to
    z-score over the full history. Summed across all companies per date,
    since one row per year-end repeats across tickers/queries.
    """
    df = pd.read_csv(path)
    date_col = _find_date_col(df)
    df[date_col] = pd.to_datetime(df[date_col])

    if "query" not in df.columns or "mentions" not in df.columns:
        raise ValueError("edgar_mentions.csv needs 'query' and 'mentions' columns.")
    sub = df[df["query"] == query]
    if sub.empty:
        raise ValueError(f"No rows for query={query!r} in edgar_mentions.csv.")

    s = sub.groupby(date_col)["mentions"].sum().resample(FREQ).mean()
    s.name = "edgar_ai_intensity"
    return s


# --------------------------------------------------------------------------- #
# SYNTHETIC DEMO DATA  --  opt-in only (--synthetic), never an automatic
# fallback. Exists so the method can be demoed without live API access (both
# collect_trends.py and collect_edgar.py note their APIs may be unreachable
# from a sandboxed environment). The 'finding' it produces is by construction,
# NOT evidence -- every output it touches is tagged SYNTHETIC.
# --------------------------------------------------------------------------- #

def synthetic_sources(seed: int = 7):
    """Generate the three sources with the two-wave shape baked in.

    Wave 1 signals rise 2015-2021 then plateau/decline. Wave 2 signals stay flat
    then accelerate from ~2023. This exists so the pipeline runs end-to-end for
    demo purposes; the 'finding' it produces is by construction, NOT evidence.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-31", "2025-12-31", freq=FREQ)
    n = len(idx)
    t = np.arange(n)

    def logistic(t, mid, rate, top=1.0):
        return top / (1 + np.exp(-rate * (t - mid)))

    # Wave 1: logistic rise saturating ~2021 (month ~72), then mild decline
    w1_shape = logistic(t, mid=48, rate=0.12) - 0.15 * logistic(t, mid=84, rate=0.08)
    # Wave 2: flat until ~2023 (month ~96) then sharp logistic acceleration
    w2_shape = logistic(t, mid=104, rate=0.22)

    # market relative strength ~ tracks wave1 with noise
    market = pd.Series(1.0 + 1.4 * w1_shape + rng.normal(0, 0.05, n),
                       index=idx, name="market_rel_strength")
    wave1_trend = pd.Series(35 + 55 * w1_shape + rng.normal(0, 3, n),
                            index=idx, name="wave1_trend")
    wave2_trend = pd.Series(20 + 70 * w2_shape + rng.normal(0, 3, n),
                            index=idx, name="wave2_trend")
    edgar = pd.Series(0.5 + 6.0 * w2_shape + 0.6 * w1_shape + rng.normal(0, 0.15, n),
                      index=idx, name="edgar_ai_intensity")
    return market, wave1_trend, wave2_trend, edgar


# --------------------------------------------------------------------------- #
# INDEX CONSTRUCTION
# --------------------------------------------------------------------------- #

def zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std(ddof=0)


@dataclass
class IndexResult:
    df: pd.DataFrame
    weight_w1: float = W1_WEIGHT
    used_synthetic: bool = False


def build_indices(weight_w1: float = W1_WEIGHT, use_synthetic: bool = False) -> IndexResult:
    if use_synthetic:
        market, w1_trend, w2_trend, edgar = synthetic_sources()
    else:
        market = load_market(MARKET_CSV)
        w1_trend = load_trends(WAVE1_TRENDS_CSV, WAVE1_TREND_TERMS, "wave1_trend")
        w2_trend = load_trends(WAVE2_TRENDS_CSV, WAVE2_TREND_TERMS, "wave2_trend")
        edgar = load_edgar(EDGAR_CSV)

    df = pd.concat([market, w1_trend, w2_trend, edgar], axis=1)

    # Clip to the range every source actually covers before filling gaps.
    # Sources have different true end dates (e.g. edgar_mentions.csv labels a
    # still-in-progress year with a Dec-31 date, past where market/trends data
    # actually ends) -- without this, interpolate(limit_direction="both") would
    # flat-fill trailing months with a stale duplicate of the last real value.
    start = max(s.first_valid_index() for s in (market, w1_trend, w2_trend, edgar))
    end = min(s.last_valid_index() for s in (market, w1_trend, w2_trend, edgar))
    df = df.loc[start:end]
    df = df.interpolate(limit_direction="both").dropna()

    # z-score every input so units are comparable
    z = df.apply(zscore)

    # sub-indices (equal weight within each wave; easy to re-weight later)
    z["wave1"] = z[["market_rel_strength", "wave1_trend"]].mean(axis=1)
    z["wave2"] = z[["wave2_trend", "edgar_ai_intensity"]].mean(axis=1)

    # composite FDI
    z["FDI"] = weight_w1 * z["wave1"] + (1 - weight_w1) * z["wave2"]

    out = pd.concat([df, z[["wave1", "wave2", "FDI"]]], axis=1)
    return IndexResult(df=out, weight_w1=weight_w1, used_synthetic=use_synthetic)


# --------------------------------------------------------------------------- #
# STRUCTURAL BREAK TESTS
# --------------------------------------------------------------------------- #

def detect_breaks(series: pd.Series, window: int = MOMENTUM_WINDOW,
                  penalty: float = PELT_PENALTY) -> dict:
    """Detect regime changes in the MOMENTUM of a series.

    We difference over `window` months so a plateau shows up as a mean shift in
    momentum (from positive to ~zero), which PELT/l2 detects cleanly and which is
    easy to defend verbally ('growth stopped here').
    """
    mom = series.diff(window).dropna()
    signal = mom.values.reshape(-1, 1)
    algo = rpt.Pelt(model="l2").fit(signal)
    bkps = algo.predict(pen=penalty)  # indices into `mom`, last is len(mom)
    break_dates = [mom.index[i - 1].strftime("%Y-%m-%d")
                   for i in bkps[:-1] if 0 < i <= len(mom)]
    return {"break_dates": break_dates,
            "momentum_index": mom.index,
            "n_breaks": len(break_dates)}


def chow_test(series: pd.Series, break_date: str) -> dict:
    """Classical Chow test for a structural break in a linear time trend.

    Regresses value ~ time on the full sample vs. two sub-samples split at
    break_date, and returns the F-statistic and p-value.
    """
    s = series.dropna()
    t = np.arange(len(s))
    y = s.values
    bd = pd.Timestamp(break_date)
    split = int((s.index < bd).sum())
    if split < 3 or (len(s) - split) < 3:
        return {"break_date": break_date, "note": "too few points to test"}

    def ssr(tt, yy):
        X = np.column_stack([np.ones_like(tt), tt])
        beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        resid = yy - X @ beta
        return float(resid @ resid)

    ssr_pooled = ssr(t, y)
    ssr1 = ssr(t[:split], y[:split])
    ssr2 = ssr(t[split:], y[split:])
    k = 2
    n = len(s)
    num = (ssr_pooled - (ssr1 + ssr2)) / k
    den = (ssr1 + ssr2) / (n - 2 * k)
    F = num / den if den > 0 else np.nan
    p = 1 - stats.f.cdf(F, k, n - 2 * k) if np.isfinite(F) else np.nan
    return {"break_date": break_date, "F_stat": round(float(F), 3),
            "p_value": round(float(p), 5), "significant_5pct": bool(p < 0.05)}


def run_break_analysis(res: IndexResult) -> dict:
    df = res.df
    out = {"used_synthetic": res.used_synthetic, "weight_w1": res.weight_w1, "series": {}}
    for col in ("wave1", "wave2", "FDI"):
        det = detect_breaks(df[col])
        chow = [chow_test(df[col], bd) for bd in det["break_dates"]]
        out["series"][col] = {"break_dates": det["break_dates"],
                              "n_breaks": det["n_breaks"],
                              "chow_tests": chow}
    return out


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w1", type=float, default=W1_WEIGHT,
                    help="Wave 1 weight in composite (0..1)")
    ap.add_argument("--synthetic", action="store_true",
                    help="use placeholder demo data instead of the real collector "
                         "output; writes to output/*_synthetic.* instead of "
                         "overwriting the real output/fdi.csv, so it can never be "
                         "mistaken for or clobber a real result")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    res = build_indices(weight_w1=args.w1, use_synthetic=args.synthetic)

    suffix = "_synthetic" if args.synthetic else ""
    fdi_path = os.path.join(OUT_DIR, f"fdi{suffix}.csv")
    res.df.to_csv(fdi_path)

    breaks = run_break_analysis(res)
    breaks_path = os.path.join(OUT_DIR, f"break_results{suffix}.json")
    with open(breaks_path, "w") as f:
        json.dump({k: v for k, v in breaks.items() if k != "series"} |
                  {"series": breaks["series"]}, f, indent=2)

    print("=" * 66)
    if args.synthetic:
        print("  *** SYNTHETIC PLACEHOLDER DATA -- NOT A REAL RESULT ***")
    print(f"  Rows        : {len(res.df)}  ({res.df.index.min().date()} -> {res.df.index.max().date()})")
    print(f"  W1 weight   : {res.weight_w1}")
    print("-" * 66)
    for col in ("wave1", "wave2", "FDI"):
        s = breaks["series"][col]
        print(f"  {col:6s} breaks: {s['break_dates'] or 'none'}")
        for ct in s["chow_tests"]:
            if "F_stat" in ct:
                sig = "**" if ct["significant_5pct"] else "  "
                print(f"          Chow @ {ct['break_date']}: "
                      f"F={ct['F_stat']}, p={ct['p_value']} {sig}")
    print("-" * 66)
    print(f"  Saved: {fdi_path}")
    print(f"  Saved: {breaks_path}")
    print("=" * 66)


if __name__ == "__main__":
    main()