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

    pip install requests pandas numpy
    python collect_edgar.py

Outputs:
    data/raw/edgar_mentions.csv   (long format: one row per company/year/query)

No chart of its own -- run collect_edgar_marketwide.py next, which reads this
CSV and produces charts/edgar_marketwide.png (7-company sample vs. entire
market, for the "agentic" query).
"""

import os
import time
import requests
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------

# REQUIRED by SEC: identify yourself with a real name/email. Generic or
# missing User-Agents get rate-limited or blocked outright.
HEADERS = {"User-Agent": "Kaixin Independent Research Project teekaixin28@gmail.com"}

# HSBC, Barclays, and Nu Holdings are foreign private issuers and file an
# annual report on Form 20-F, not 10-K -- everyone else here files a
# standard 10-K. Confirmed per-company via SEC submissions history
# (data.sec.gov/submissions/CIK##########.json), not assumed -- BCS and NU
# were originally left out of this dict despite being in the market-price
# ticker basket (build_index.py's LEGACY_TICKERS/FINTECH_TICKERS); both
# resolve to valid CIKs and both file 20-F, so there was no technical reason
# to exclude them. Added to match the full 7-ticker market universe.
COMPANIES = {
    "JPM":  {"name": "JPMorgan Chase",     "category": "traditional_bank",   "forms": "10-K"},
    "HSBC": {"name": "HSBC Holdings",      "category": "traditional_bank",   "forms": "20-F"},
    "BCS":  {"name": "Barclays",           "category": "traditional_bank",   "forms": "20-F"},
    "SOFI": {"name": "SoFi Technologies",  "category": "neobank",            "forms": "10-K"},
    "NU":   {"name": "Nubank",             "category": "neobank",            "forms": "20-F"},
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
START_YEAR = 2019
END_YEAR = 2026

OUT_DIR_RAW = "data/raw"
os.makedirs(OUT_DIR_RAW, exist_ok=True)

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
# 4. Run everything
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

    print("\nDone. Next: collect_edgar_marketwide.py for the 7-company-vs-market chart, "
          "then build_index.py to combine market + trends + EDGAR signals into the "
          "two composite indices (Wave 1 Stagnation / Wave 2 AI-Native).")