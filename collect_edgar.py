"""
collect_edgar.py

Part 3 of the FinTech Disruption Index project.
Counts how often AI-agent / agentic-AI language appears in each company's
annual filings, per year -- a proxy for who's actually disclosing AI-native
investment to regulators, as opposed to just marketing it. Regulatory
disclosure carries legal weight, unlike a press release, so this is the
strongest evidence layer in the project.

Two search series are collected per company-year:
  * "agentic"  -- the bleeding-edge phrase set ("AI agent", "agentic AI", ...).
                  Expected to be near-zero before ~2023; its late lift-off is
                  itself Wave-2 "just beginning" evidence.
  * "ai_broad" -- "artificial intelligence", the baseline incumbents have used
                  for years. Guarantees a non-empty signal and is the workhorse
                  input for build_index.py.

Uses the SEC EDGAR full-text search API (efts.sec.gov), which indexes filing
text since 2001. No API key needed, but SEC requires a descriptive User-Agent
header on every request and rate-limits to 10 requests/second across all EDGAR
endpoints (temporary IP block if exceeded). CIKs must be 10-digit zero-padded.

Run locally (needs open internet access to sec.gov / efts.sec.gov, which a
sandboxed dev environment may block):

    pip install requests pandas numpy matplotlib
    python collect_edgar.py

Outputs:
    data/raw/edgar_mentions.csv   (long format: one row per company/year/query)
    charts/edgar_mentions.png
"""

import os
import time
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------

# REQUIRED by SEC: identify yourself with a real name/email. Generic or
# missing User-Agents get rate-limited or blocked outright.
HEADERS = {"User-Agent": "Kaixin Independent Research Project kaixin@example.com"}

# HSBC is a foreign private issuer and files an annual report on Form 20-F,
# not 10-K -- everyone else here files a standard 10-K.
COMPANIES = {
    "JPM":  {"name": "JPMorgan Chase",     "category": "traditional_bank",   "forms": "10-K"},
    "HSBC": {"name": "HSBC Holdings",      "category": "traditional_bank",   "forms": "20-F"},
    "SOFI": {"name": "SoFi Technologies",  "category": "neobank",            "forms": "10-K"},
    "PYPL": {"name": "PayPal Holdings",    "category": "embedded_finance",   "forms": "10-K"},
    "XYZ":  {"name": "Block, Inc.",        "category": "embedded_finance",   "forms": "10-K"},
}

# Full-text queries. Values are raw EDGAR query strings (boolean OR + quoted
# phrases), sent as-is -- do NOT wrap these in extra quotes. An exact phrase
# like "AI agent" only matches that precise bigram, so a single narrow phrase
# returns near-zero for formal annual reports; the OR set casts a wider net.
QUERIES = {
    "agentic":  '"AI agent" OR "AI agents" OR "agentic AI" OR "agentic" OR "AI-powered agent"',
    "ai_broad": '"artificial intelligence"',
}
QUERY_LABELS = {
    "agentic":  "AI-agent / agentic-AI language",
    "ai_broad": '"artificial intelligence"',
}
# Which series to chart. If it comes back empty, the run auto-falls back to
# whichever query actually had hits, so the chart is never silently blank.
PLOT_QUERY = "ai_broad"

START_YEAR = 2019
END_YEAR = 2026

OUT_DIR_RAW = "data/raw"
OUT_DIR_CHARTS = "charts"
for d in (OUT_DIR_RAW, OUT_DIR_CHARTS):
    os.makedirs(d, exist_ok=True)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

# HTTP statuses worth retrying: 429 = rate limit, 5xx = transient server errors.
# EDGAR full-text search intermittently returns 500s under load; retrying the
# identical request almost always succeeds.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# 2. Resolve tickers to CIKs
# ---------------------------------------------------------------------------
# The search API's entityName filter does fuzzy text matching on company name,
# which is unreliable. SEC publishes one JSON file mapping every ticker to its
# CIK -- pulling that once and filtering by exact 10-digit CIK is far more
# robust. (Un-padded CIKs return HTTP 500 from the FTS endpoint.)

def build_ticker_to_cik_map() -> dict:
    resp = requests.get(TICKER_MAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()  # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    return {row["ticker"]: str(row["cik_str"]).zfill(10) for row in data.values()}


# ---------------------------------------------------------------------------
# 3. Count matching filings per company per year per query
# ---------------------------------------------------------------------------

def count_mentions(cik: str | None, forms: str, query: str, year: int,
                   max_retries: int = 4, timeout: int = 30) -> float:
    """Number of filings (not raw text occurrences) matching `query`, for one
    company (or, if cik is None, across ALL SEC filers), one form type, one
    calendar year.

    `query` is passed to EDGAR verbatim, so it may contain quoted phrases and
    boolean OR/AND/NOT operators. Retries on rate-limits (429), transient
    server errors (5xx), and network failures; after exhausting retries returns
    NaN rather than raising, so one flaky cell doesn't discard the whole run.
    """
    params = {
        "q": query,                       # sent as-is: supports OR + quoted phrases
        "forms": forms,
        # NOTE: do NOT add "dateRange": "custom" here -- efts.sec.gov 500s on
        # every request that includes it, even though startdt/enddt alone
        # work fine. Confirmed via curl: identical query only differs by the
        # presence of this param.
        "startdt": f"{year}-01-01",
        "enddt": f"{year}-12-31",
    }
    if cik:
        params["ciks"] = cik
    label = cik or "ALL FILERS"
    for attempt in range(max_retries):
        try:
            resp = requests.get(SEARCH_URL, params=params,
                                headers=HEADERS, timeout=timeout)
        except requests.exceptions.RequestException as e:
            wait = 3 * (2 ** attempt)
            print(f"    Network error ({e.__class__.__name__}) for {label} {year}, "
                  f"retry in {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code in RETRYABLE_STATUS:
            base = 15 if resp.status_code == 429 else 3  # back off harder on real rate limits
            wait = base * (2 ** attempt)
            print(f"    HTTP {resp.status_code} for {label} {year}, retry in {wait}s "
                  f"(attempt {attempt + 1}/{max_retries})...")
            time.sleep(wait)
            continue

        resp.raise_for_status()  # a real 4xx (e.g. 400) is a bug -- fail loud
        data = resp.json()
        return data.get("hits", {}).get("total", {}).get("value", 0)

    print(f"    GAVE UP on {label} {year} after {max_retries} retries -> recording NaN")
    return np.nan


def collect_all_mentions(companies: dict, ticker_to_cik: dict, queries: dict,
                          start_year: int, end_year: int) -> pd.DataFrame:
    rows = []
    for ticker, info in companies.items():
        cik = ticker_to_cik.get(ticker)
        if cik is None:
            print(f"  WARNING: could not resolve CIK for {ticker}, skipping")
            continue
        print(f"Querying {ticker} ({info['name']}), CIK {cik}...")
        for year in range(start_year, end_year + 1):
            for qkey, qstr in queries.items():
                count = count_mentions(cik, info["forms"], qstr, year)
                rows.append({
                    "ticker": ticker,
                    "name": info["name"],
                    "category": info["category"],
                    "year": year,
                    "date": f"{year}-12-31",   # year-end, so downstream can parse a date
                    "query": qkey,
                    "mentions": count,
                })
                time.sleep(0.3)  # stay well under SEC's 10 req/sec limit
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. Chart: matching filings per year, grouped by company category
# ---------------------------------------------------------------------------

def plot_mentions(df: pd.DataFrame, out_path: str, query_key: str):
    """Plot one query's series as grouped bars by category. Renders a labelled
    'no matches' panel instead of a blank chart if the series is all zero."""
    sub = df[df["query"] == query_key]
    category_totals = (sub.groupby(["year", "category"])["mentions"]
                          .sum().unstack(fill_value=0))

    colors = {"traditional_bank": "#4A5568", "neobank": "#38B2AC", "embedded_finance": "#DD6B20"}
    ordered_cols = [c for c in ["traditional_bank", "neobank", "embedded_finance"]
                    if c in category_totals.columns]
    category_totals = category_totals[ordered_cols]

    fig, ax = plt.subplots(figsize=(11, 6))
    total_hits = float(category_totals.to_numpy().sum())

    if total_hits == 0:
        # Never emit a silently-empty chart: say so on the figure itself.
        ax.text(0.5, 0.5,
                "No matching filings found for this query\n"
                "across all companies and years.",
                ha="center", va="center", fontsize=13, color="#B03A2E",
                transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        category_totals.plot(kind="bar", ax=ax,
                             color=[colors[c] for c in ordered_cols])
        ax.set_xlabel("Year")
        ax.set_ylabel("Number of Matching Filings")
        ax.legend(title="Category")
        ax.grid(alpha=0.2, axis="y")

    label = QUERY_LABELS.get(query_key, query_key)
    ax.set_title(f"SEC Filings Mentioning {label}\nby Year and Company Type", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    print(f"Saved chart to {out_path}")


# ---------------------------------------------------------------------------
# 5. Run everything
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Resolving tickers to CIKs ===")
    ticker_to_cik = build_ticker_to_cik_map()
    print(f"Loaded {len(ticker_to_cik)} ticker->CIK mappings\n")

    print(f"=== Counting filings, {START_YEAR}-{END_YEAR} ===")
    print(f"    queries: {list(QUERIES)}")
    mentions = collect_all_mentions(COMPANIES, ticker_to_cik, QUERIES, START_YEAR, END_YEAR)
    mentions.to_csv(f"{OUT_DIR_RAW}/edgar_mentions.csv", index=False)
    print(f"\nSaved {len(mentions)} rows to {OUT_DIR_RAW}/edgar_mentions.csv")

    # Report totals per query and per-query failures.
    totals = mentions.groupby("query")["mentions"].sum()
    print("\nTotal matching filings by query:")
    for q in QUERIES:
        print(f"    {q:10s}: {int(totals.get(q, 0))}")
    n_missing = int(mentions["mentions"].isna().sum())
    if n_missing:
        print(f"NOTE: {n_missing} cell(s) failed after retries and are NaN. Re-run to fill gaps.")

    # Choose what to chart, and never fall through to an empty chart in silence.
    plot_query = PLOT_QUERY
    if totals.get(plot_query, 0) == 0:
        if totals.max() > 0:
            plot_query = totals.idxmax()
            print(f"\nWARNING: '{PLOT_QUERY}' had 0 hits; charting '{plot_query}' instead.")
        else:
            print("\nWARNING: every query returned 0 hits. Check the probe script / "
                  "your User-Agent before trusting this as a real result.")

    print("\n=== Plotting ===")
    plot_mentions(mentions, f"{OUT_DIR_CHARTS}/edgar_mentions.png", plot_query)

    print("\nDone. Next: build_index.py to combine market + trends + EDGAR signals "
          "into the two composite indices (Wave 1 Stagnation / Wave 2 AI-Native).")