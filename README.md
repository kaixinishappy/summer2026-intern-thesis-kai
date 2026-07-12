# Fintech Two-Wave Disruption Index

Empirically testing whether fintech disruption of traditional banking has run its
course, or whether a **second wave of AI-native financial services** is only now
beginning.

Rather than asking the trivial question ("did fintech disrupt banking?" — yes),
this project tests for **two separate structural breaks**: the maturation of
Wave 1 (payments, neobanks, embedded finance) and the onset of Wave 2 (AI-native
underwriting and advisory).

## How it works

Three independent data sources are collected, normalised to a monthly frequency,
and combined into a **Fintech Disruption Index (FDI)** with two sub-indices:

| Source | Script | Signal | Wave |
|--------|--------|--------|------|
| Market prices | `collect_market_data.py` | fintech-vs-legacy relative strength | 1 |
| Google Trends | `collect_trends.py` | search interest per keyword group | 1 & 2 |
| SEC EDGAR filings | `collect_edgar.py` | AI-language intensity per filing | 2 |

- **Wave 1 sub-index** = market relative strength + Wave-1 search interest
- **Wave 2 sub-index** = Wave-2 search interest + EDGAR AI intensity
- **Composite FDI** = weighted blend (weight configurable)

Structural breaks are detected on each sub-index's **12-month momentum** using
PELT (`ruptures`), then confirmed with a classical **Chow test** for a break in
the linear trend.

## Repository layout

```
.
├── collect_market_data.py # data collection: prices, fundamentals, indexed performance
├── collect_trends.py      # data collection: Google Trends, Wave 1 & 2 keyword groups
├── collect_edgar.py       # data collection: SEC EDGAR filing mentions
├── build_index.py         # builds sub-indices + composite, runs break tests
├── make_charts.py         # the three headline charts (reads output/, writes charts/)
├── data/
│   ├── raw/                   # prices.csv, fundamentals.csv, indexed_performance.csv,
│   │                          # wave1_trends.csv, wave2_trends.csv, edgar_mentions.csv
│   └── processed/             # trends_yearly.csv
├── charts/                # per-collector charts + the three headline charts (*.png)
├── output/                # fdi.csv, break_results.json (from build_index.py)
├── VERDICT.md             # written verdict
└── README.md
```

## What each file does

**`collect_market_data.py`** — pulls daily close prices (via `yfinance`, since
2018) and annual net income for 7 tickers split into three categories:
`traditional_bank` (JPM, HSBC, BCS), `neobank` (SOFI, NU), `embedded_finance`
(PYPL, XYZ). Rebases every ticker's price series to 100 at its start date so
wildly different price levels are comparable on one axis, and writes:
- `data/raw/prices.csv` — daily close, long format
- `data/raw/fundamentals.csv` — annual net income per company
- `data/raw/indexed_performance.csv` — the rebased-to-100 series
- `charts/indexed_performance.png`

**`collect_trends.py`** — pulls Google Trends search-interest (via `pytrends`)
for two term groups: Wave 1 ("neobank", "digital bank app", "mobile banking")
and Wave 2 ("AI agent finance", "agentic AI banking", "autonomous wealth
management"), weekly since 2018. Aggregates to yearly averages and writes:
- `data/raw/wave1_trends.csv`, `data/raw/wave2_trends.csv` — weekly, per term
- `data/processed/trends_yearly.csv` — yearly average, long format
- `charts/trends_comparison.png`

**`collect_edgar.py`** — queries SEC EDGAR's full-text search API for how
often each company's annual filing (10-K, or 20-F for HSBC) matches two query
sets per year since 2019: `"agentic"` (the "AI agent" / "agentic AI" phrase
family — near-zero until it isn't) and `"ai_broad"` (`"artificial
intelligence"` — the saturated baseline). Regulatory disclosure carries legal
weight, unlike a press release, so this is the strongest evidence layer in the
project. Writes:
- `data/raw/edgar_mentions.csv` — long format, one row per company/year/query

No chart of its own — see `collect_edgar_marketwide.py` below, which reads
this CSV and charts the `agentic` series against the entire market.

**`collect_edgar_marketwide.py`** — extends `collect_edgar.py`'s `agentic`
query with no company filter, across every 10-K filer in EDGAR, to check
whether the 5-company sample's near-zero-then-2026 shape is real or just an
artifact of which 5 companies got picked. Writes:
- `data/raw/edgar_marketwide.csv` — year, query, total_filings (market-wide)
- `charts/edgar_marketwide.png` — 5-company sample vs. market-wide, `agentic` query

Also accepts `--synthetic` (see **Synthetic demo mode** below) — the only
collector script that does, since it's the one piece of evidence with no
other offline fallback.

**`build_index.py`** — the combination step. Loads the three collectors'
real output (raises `FileNotFoundError` if any is missing — no automatic
synthetic fallback; pass `--synthetic` to opt into placeholder demo data
instead, see below), resamples everything to monthly and z-scores it, then:
- **Wave 1 sub-index** = z(market relative strength) + z(Wave-1 search interest)
- **Wave 2 sub-index** = z(Wave-2 search interest) + z(EDGAR "ai_broad" intensity)
- **Composite FDI** = `W1_WEIGHT * wave1 + (1 - W1_WEIGHT) * wave2` (default 50/50)

Then runs PELT change-point detection (`ruptures`) on each series' 12-month
momentum to find candidate break dates, and a Chow test at each candidate to
confirm it's a statistically significant break in trend (not just noise).
Writes `output/fdi.csv` and `output/break_results.json`.

**`make_charts.py`** — reads `output/fdi.csv` + `break_results.json` and
renders the three headline charts into `charts/`.

## Quick start

```bash
pip install requests pandas numpy scipy statsmodels ruptures matplotlib pytrends

# 1. collect data -> writes data/raw/*.csv, data/processed/*.csv, charts/*.png
python collect_market_data.py
python collect_trends.py
python collect_edgar.py

# 2. build indices + run structural break tests -> output/fdi.csv, break_results.json
#    (requires all three collectors above to have run first)
python build_index.py

# 3. generate the three headline charts -> charts/*.png
python make_charts.py
```

## Synthetic demo mode

`collect_trends.py`, `collect_edgar.py`, and `collect_edgar_marketwide.py`
all need live internet access (trends.google.com / efts.sec.gov), which a
sandboxed environment may block. For demoing the *method* without that
access, `build_index.py`, `make_charts.py`, and `collect_edgar_marketwide.py`
all accept `--synthetic`:

```bash
python build_index.py --synthetic               # writes output/fdi_synthetic.csv,
                                                  # output/break_results_synthetic.json
python make_charts.py --synthetic                # reads those, writes charts/*_synthetic.png
python collect_edgar_marketwide.py --synthetic   # writes data/raw/edgar_marketwide_synthetic.csv,
                                                  # charts/edgar_marketwide_synthetic.png
```

`collect_market_data.py` and `collect_trends.py` don't need their own
`--synthetic` flag — `build_index.py --synthetic` fabricates stand-in data
for all three collectors' outputs directly, bypassing them entirely.
`collect_edgar_marketwide.py` is the exception: its output
(`edgar_marketwide.csv`/`.png`) is a standalone check that never flows
through `build_index.py`, so it needed its own synthetic path to have any
offline fallback at all — without it, "the single strongest piece of
evidence in the whole project" (per `VERDICT.md`) would have no way to be
demoed without live SEC access.

This is opt-in only — it never triggers automatically, and it never touches
`output/fdi.csv` / `output/break_results.json` / `data/raw/edgar_marketwide.csv`
/ the non-suffixed chart PNGs, so it can't be confused with, or silently
overwrite, a real result. Every synthetic chart is watermarked "SYNTHETIC
DEMO DATA -- NOT A REAL RESULT" and the console output prints the same
warning. **The synthetic result is a demonstration that the pipeline and
break-detection method work end to end — it is not evidence for or against
the two-wave thesis**, since its shape (Wave 1 rising then plateauing, Wave 2
flat then accelerating; market-wide/sample `agentic` counts near-zero then
spiking) is baked in by construction in `synthetic_sources()` and
`synthetic_marketwide_and_sample()`.

## Outputs

- `output/fdi.csv` — monthly sub-indices and composite FDI
- `output/break_results.json` — detected break dates + Chow F/p per series
- six chart PNGs in `charts/` — see below
- (if `--synthetic` was used) matching `output/*_synthetic.*` and
  `charts/*_synthetic.png` files, entirely separate from the real ones above

## Limitations — read before over-citing this

- **Proxies, not ground truth.** Search interest measures attention, not
  adoption. Filing language measures what companies *say*, not what they
  ship or how much revenue it drives. Stock price reflects expectations, not
  realized market share. Net income is a real financial outcome, but only
  four fiscal years are available per company via `yfinance`, too short to
  fully separate a rate-cycle effect from company-specific factors.
- **Short Wave 2 window.** The genuine acceleration signal covers roughly
  2024-2026 — about two years. A single flat year would meaningfully change
  the picture; this cannot yet be distinguished from a temporary spike with
  full confidence.
- **Thin, noisy tail.** The final one to two months of the combined index
  (June-July 2026) reverse sharply in *both* sub-indices simultaneously —
  treated as noise here, not a new trend, but worth re-checking in 6-12
  months.
- **Small, hand-picked, all-public company set — partially mitigated for
  Wave 2.** 5 companies for EDGAR, 7 tickers for market prices, all of them
  public incumbents or already-public 2010s fintechs. The market-wide EDGAR
  check (`charts/edgar_marketwide.png`) confirms the "thin until 2024-2025"
  shape isn't a 5-company artifact, but the underlying gap remains: there is
  still no way, with any data collected here, to see a private AI-native
  challenger even if one existed and was winning right now.
- **`VERDICT.md` Part 3 (banks likely absorb the AI wave) is a prediction,
  explicitly labeled as such.** It should not be cited with the same
  confidence as the parts that describe what already happened.

## Config

All tunable parameters (ticker baskets, keyword groups, composite weight,
resampling frequency, PELT penalty) live in the `CONFIG` block at the top of
`build_index.py`.