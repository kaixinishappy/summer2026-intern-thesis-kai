# Fintech Two-Wave Disruption Index

Empirically testing whether fintech disruption of traditional banking has run its
course, or whether a **second wave of AI-native financial services** is only now
beginning.

Rather than asking the trivial question ("did fintech disrupt banking?" — yes),
this project tests for **two separate structural breaks**: the maturation of
Wave 1 (payments, neobanks, embedded finance) and the onset of Wave 2 (AI-native
underwriting and advisory).

## How it works

Four independent data sources are collected, normalised to a monthly frequency,
and combined into a **Fintech Disruption Index (FDI)** with two sub-indices:

| Source | Script | Signal | Wave |
|--------|--------|--------|------|
| Market prices | `collect_market_data.py` | fintech-vs-legacy relative strength | 1 |
| Net income (fundamentals) | `collect_market_data.py` | fintech-vs-legacy profitability growth | 1 |
| Google Trends | `collect_trends.py` | search interest per keyword group | 1 & 2 |
| SEC EDGAR filings | `collect_edgar.py` | AI-language intensity per filing | 2 |

- **Wave 1 sub-index** = market relative strength + Wave-1 search interest +
  relative profitability growth
- **Wave 2 sub-index** = Wave-2 search interest + EDGAR AI intensity
- **Composite FDI** = weighted blend (weight configurable)

Structural breaks are detected on each sub-index's **12-month momentum** using
PELT (`ruptures`), then confirmed with a classical **Chow test** for a break in
the linear trend. Each sub-index is re-standardised to unit variance after
averaging its inputs, so PELT's penalty means the same thing regardless of how
many raw signals feed a given wave (Wave 1 now averages three, Wave 2 still
averages two).

Two standalone checks, mirroring each other, ask whether the headline
7-ticker/7-company findings generalize beyond that hand-picked sample:
`collect_edgar_marketwide.py` reruns the EDGAR "agentic" query with no company
filter across every SEC 10-K filer, and `collect_market_marketwide.py` compares
a fintech-sector ETF (FINX) against a bank-sector ETF (KBWB) instead of the 7
tickers. Neither feeds into the composite FDI — they're validation charts, not
additional index inputs.

## Repository layout

```
.
├── collect_market_data.py # data collection: prices, fundamentals, indexed performance
├── collect_market_marketwide.py # check: 7-ticker sample vs. FINX/KBWB sector ETFs
├── collect_trends.py      # data collection: Google Trends, Wave 1 & 2 keyword groups
├── collect_edgar.py       # data collection: SEC EDGAR filing mentions
├── collect_edgar_marketwide.py # check: 7-company sample vs. every SEC 10-K filer
├── build_index.py         # builds sub-indices + composite, runs break tests
├── make_charts.py         # the three headline charts (reads output/, writes charts/)
├── app.py                 # Streamlit app: live sliders, recomputes in real time
├── ai_assistant.py        # Groq research assistant: live summary + Q&A, used by app.py
├── data/
│   ├── raw/                   # prices.csv, fundamentals.csv, indexed_performance.csv,
│   │                          # market_marketwide.csv, wave1_trends.csv, wave2_trends.csv,
│   │                          # edgar_mentions.csv, edgar_marketwide.csv
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
- `data/raw/fundamentals.csv` — annual net income per company (feeds
  `build_index.py`'s Wave 1 profitability signal, below)
- `data/raw/indexed_performance.csv` — the rebased-to-100 series
- `charts/indexed_performance.png`

**`collect_market_marketwide.py`** — extends the 7-ticker price comparison
with a market-wide baseline: FINX (Global X FinTech ETF) vs. KBWB (Invesco
KBW Bank ETF), instead of the 7 hand-picked names, to check whether the
"fintech rose then rolled over vs. banks" shape is real or just an artifact
of which 7 companies got picked — same spirit as `collect_edgar_marketwide.py`
below, for the price signal instead of the EDGAR signal. Not fed into
`build_index.py`'s composite; a standalone generalization check. Writes:
- `data/raw/market_marketwide.csv` — ETF daily close, rebased-to-100
- `charts/market_marketwide.png` — ETF indexed prices + 7-ticker-sample vs.
  ETF relative-strength overlay

**`collect_trends.py`** — pulls Google Trends search-interest (via `pytrends`)
for two term groups: Wave 1 ("neobank", "digital bank app", "mobile banking")
and Wave 2 ("AI agent finance", "agentic AI banking", "autonomous wealth
management"), weekly since 2018. Aggregates to yearly averages and writes:
- `data/raw/wave1_trends.csv`, `data/raw/wave2_trends.csv` — weekly, per term
- `data/processed/trends_yearly.csv` — yearly average, long format
- `charts/trends_comparison.png`

**`collect_edgar.py`** — queries SEC EDGAR's full-text search API for how
often each company's annual filing (10-K, or 20-F for HSBC, Barclays, and
Nubank — all three are foreign private issuers) matches two query sets per
year since 2019: `"agentic"` (the "AI agent" / "agentic AI" phrase
family — near-zero until it isn't) and `"ai_broad"` (`"artificial
intelligence"` — the saturated baseline). Regulatory disclosure carries legal
weight, unlike a press release, so this is the strongest evidence layer in the
project. Covers all 7 tickers from the market-price basket (BCS and NU were
originally left out of this collector despite being valid SEC filers with
real CIKs — added to close that gap). Writes:
- `data/raw/edgar_mentions.csv` — long format, one row per company/year/query

No chart of its own — see `collect_edgar_marketwide.py` below, which reads
this CSV and charts the `agentic` series against the entire market.

**`collect_edgar_marketwide.py`** — extends `collect_edgar.py`'s `agentic`
query with no company filter, across every 10-K filer in EDGAR, to check
whether the 7-company sample's near-zero-then-2026 shape is real or just an
artifact of which 7 companies got picked. Writes:
- `data/raw/edgar_marketwide.csv` — year, query, total_filings (market-wide)
- `charts/edgar_marketwide.png` — 7-company sample vs. market-wide, `agentic` query

Also accepts `--synthetic` (see **Synthetic demo mode** below), like
`collect_market_marketwide.py` above — both are market-wide/generalization
checks with no other offline fallback, unlike the primary collectors, which
`build_index.py --synthetic` fabricates stand-in data for directly.

**`build_index.py`** — the combination step. Loads the four collectors'
real output (raises `FileNotFoundError` if any is missing — no automatic
synthetic fallback; pass `--synthetic` to opt into placeholder demo data
instead, see below), resamples everything to monthly and z-scores it, then:
- **Wave 1 sub-index** = z(market relative strength) + z(Wave-1 search interest)
  + z(fintech-vs-legacy relative profitability growth), re-standardised to
  unit variance after averaging
- **Wave 2 sub-index** = z(Wave-2 search interest) + z(EDGAR "ai_broad" intensity),
  re-standardised the same way
- **Composite FDI** = `W1_WEIGHT * wave1 + (1 - W1_WEIGHT) * wave2` (default 50/50)

The profitability signal is annual (~3 usable YoY growth points per basket,
since `yfinance` only exposes ~4 fiscal years) and much thinner than the
monthly price/search signals — it's held flat at its nearest real value
outside 2023-2025 rather than shrinking the whole index's date range down to
that window (see `load_profitability()`'s docstring for the exact mechanism).

Then runs PELT change-point detection (`ruptures`) on each series' 12-month
momentum to find candidate break dates, and a Chow test at each candidate to
confirm it's a statistically significant break in trend (not just noise).
Writes `output/fdi.csv` and `output/break_results.json`.

**`make_charts.py`** — reads `output/fdi.csv` + `break_results.json` and
renders the three headline charts into `charts/`.

## Quick start

```bash
pip install requests pandas numpy scipy statsmodels ruptures matplotlib pytrends yfinance streamlit groq python-dotenv

# 1. collect data -> writes data/raw/*.csv, data/processed/*.csv, charts/*.png
#    (collect_market_data.py's fundamentals.csv feeds build_index.py's Wave 1
#    profitability signal directly -- no separate collection step needed)
python collect_market_data.py
python collect_trends.py
python collect_edgar.py

# 1b. optional: market-wide/sample generalization checks, standalone (not
#     required by step 2 below)
python collect_market_marketwide.py
python collect_edgar_marketwide.py

# 2. build indices + run structural break tests -> output/fdi.csv, break_results.json
#    (requires the three primary collectors above to have run first)
python build_index.py

# 3. generate the three headline charts -> charts/*.png
python make_charts.py
```

## Interactive app

```bash
streamlit run app.py
```

`app.py` is a live version of steps 2-3 above: sliders for the composite
weight (`W1_WEIGHT`), PELT break-detection penalty, and momentum window
recompute the sub-indices, break dates, and Chow tests on every change —
Streamlit reruns the script top-to-bottom on each interaction, so there's no
separate "rebuild" step. It imports `build_indices()` and
`run_break_analysis()` straight from `build_index.py` (which now accepts
`momentum_window`/`pelt_penalty` overrides for this purpose, defaulting to
the same `CONFIG` constants the CLI uses) and reuses `make_charts.py`'s
color palette and break-annotation helper, so the live charts can't drift
from the static PNGs' numbers or styling. If `data/raw/*.csv` is missing, a
sidebar toggle switches to the same synthetic demo data as `--synthetic`
elsewhere in this project (clearly labeled — moving sliders changes how the
data is combined and tested, never which data is loaded).

### AI Research Assistant (Groq)

Below the charts, an "AI Research Assistant" section (`ai_assistant.py`) adds
two Groq-powered features, both grounded in the exact `df`/`breaks` objects
`app.py` just recomputed — never a static copy of `VERDICT.md`:

- **Live summary** — regenerates a short executive-summary paragraph that
  reflects whatever the sliders are *currently* set to, so you can compare it
  against `VERDICT.md`'s written verdict at the default 50/50 weight.
- **Ask a question** — a chat interface for questions about the current run
  (break dates, F-statistics, what a limitation means, etc.).

Every call rebuilds its context fresh from the live numbers and is instructed
to only cite figures present in that context — it can't invent a statistic or
silently reuse a stale answer from before you moved a slider. It also refuses
to blur the project's own epistemic distinctions: Wave 1 findings get stated
with real confidence, Wave 2 findings are flagged as thin/early evidence, and
"banks absorb the AI wave" is treated as the labeled prediction it is, not a
finding.

Needs a Groq API key — free, no billing card required, at
<https://console.groq.com/keys>. Three ways to supply it, in order of
precedence:
1. **`.env` file (recommended for local dev)** — copy `.env.example` to
   `.env` and paste your key in as `GROQ_API_KEY=...`. `.env` is gitignored
   and loaded automatically by `app.py` on startup via `python-dotenv`; it
   never gets committed.
2. **Environment variable** — `export GROQ_API_KEY=...` before launching.
3. **Sidebar input** — paste it into the app at runtime if you'd rather not
   use a file; kept in Streamlit's session memory only, never written to
   disk.

(This originally targeted Gemini; switched to Groq after the available
Gemini key(s) required a funded Google Cloud billing account before
unlocking any quota, confirmed across two separate projects. `ai_assistant.py`
uses the official `groq` Python SDK, an OpenAI-compatible chat-completions
API.)

If no key is present through any of these, the app still runs normally —
this section just shows the key prompt instead of the summary/chat tabs.

## Synthetic demo mode

`collect_trends.py`, `collect_edgar.py`, `collect_edgar_marketwide.py`, and
`collect_market_marketwide.py` all need live internet access
(trends.google.com / efts.sec.gov / Yahoo Finance), which a sandboxed
environment may block. For demoing the *method* without that access,
`build_index.py`, `make_charts.py`, `collect_edgar_marketwide.py`, and
`collect_market_marketwide.py` all accept `--synthetic`:

```bash
python build_index.py --synthetic               # writes output/fdi_synthetic.csv,
                                                  # output/break_results_synthetic.json
python make_charts.py --synthetic                # reads those, writes charts/*_synthetic.png
python collect_edgar_marketwide.py --synthetic   # writes data/raw/edgar_marketwide_synthetic.csv,
                                                  # charts/edgar_marketwide_synthetic.png
python collect_market_marketwide.py --synthetic  # writes data/raw/market_marketwide_synthetic.csv,
                                                  # charts/market_marketwide_synthetic.png
```

`collect_market_data.py` and `collect_trends.py` don't need their own
`--synthetic` flag — `build_index.py --synthetic` fabricates stand-in data
for all four collectors' outputs directly, bypassing them entirely.
`collect_edgar_marketwide.py` and `collect_market_marketwide.py` are the
exception: both are standalone checks that never flow through
`build_index.py`, so they each needed their own synthetic path to have any
offline fallback at all — without it, "the single strongest piece of
evidence in the whole project" (per `VERDICT.md`) would have no way to be
demoed without live SEC/Yahoo Finance access.

This is opt-in only — it never triggers automatically, and it never touches
`output/fdi.csv` / `output/break_results.json` / `data/raw/edgar_marketwide.csv`
/ `data/raw/market_marketwide.csv` / the non-suffixed chart PNGs, so it can't
be confused with, or silently overwrite, a real result. Every synthetic chart
is watermarked "SYNTHETIC DEMO DATA -- NOT A REAL RESULT" and the console
output prints the same warning. **The synthetic result is a demonstration
that the pipeline and break-detection method work end to end — it is not
evidence for or against the two-wave thesis**, since its shape (Wave 1 rising
then plateauing, Wave 2 flat then accelerating; market-wide/sample `agentic`
counts near-zero then spiking; fintech-vs-bank ETF rising then rolling over)
is baked in by construction in `synthetic_sources()`,
`synthetic_marketwide_and_sample()`, and `synthetic_etf_and_sample()`.

## Outputs

- `output/fdi.csv` — monthly sub-indices and composite FDI
- `output/break_results.json` — detected break dates + Chow F/p per series
- eight chart PNGs in `charts/` — see below
- (if `--synthetic` was used) matching `output/*_synthetic.*` and
  `charts/*_synthetic.png` files, entirely separate from the real ones above

## Limitations

- **Proxies, not ground truth.** Search interest measures attention, not
  adoption. Filing language measures what companies *say*, not what they
  ship or how much revenue it drives. Stock price reflects expectations, not
  realized market share. Net income is a real financial outcome and now feeds
  Wave 1 directly (`load_profitability()` in `build_index.py`), but only four
  fiscal years are available per company via `yfinance` — about 3 usable YoY
  growth points per basket, too short to fully separate a rate-cycle effect
  from company-specific factors, and much thinner than the monthly price and
  search signals it's averaged with.
- **Short Wave 2 window.** The genuine acceleration signal covers roughly
  2024-2026 — about two years. A single flat year would meaningfully change
  the picture; this cannot yet be distinguished from a temporary spike with
  full confidence.
- **Thin, noisy tail.** The final one to two months of the combined index
  (June-July 2026) reverse sharply in *both* sub-indices simultaneously —
  treated as noise here, not a new trend, but worth re-checking in 6-12
  months.
- **Small, hand-picked, all-public company set — partially mitigated for both
  waves.** 7 companies for EDGAR (matching the full 7-ticker market-price
  basket), all of them public incumbents or already-public 2010s fintechs.
  The market-wide EDGAR check (`charts/edgar_marketwide.png`) confirms the
  "thin until 2024-2025" shape isn't a 7-company artifact, and the FINX/KBWB
  sector-ETF check (`charts/market_marketwide.png`) confirms the "fintech
  rose then rolled over vs. banks" price shape isn't either — but the
  underlying gap remains: there is still no way, with any data collected
  here, to see a private AI-native challenger even if one existed and was
  winning right now.
- **`VERDICT.md` Part 3 (banks likely absorb the AI wave) is a prediction,
  explicitly labeled as such.** It should not be cited with the same
  confidence as the parts that describe what already happened.

## Config

All tunable parameters (ticker baskets, keyword groups, composite weight,
resampling frequency, PELT penalty) live in the `CONFIG` block at the top of
`build_index.py`.
