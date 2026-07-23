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
├── ai_assistant.py        # Gemini research assistant: live summary + Q&A, used by app.py
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
pip install requests pandas numpy scipy statsmodels ruptures matplotlib pytrends yfinance streamlit google-genai python-dotenv

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

### AI Research Assistant (Gemini)

Below the charts, an "AI Research Assistant" section (`ai_assistant.py`) adds
two Gemini-powered features, both grounded in the exact `df`/`breaks` objects
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

Needs a Gemini API key — free, no billing card required, from the **"Get API
key" flow at <https://ai.google.dev>** (AI Studio) specifically. A key issued
through Google Cloud Console / Vertex AI instead is a different, billed
product — using one of those is what caused this project's earlier attempt at
Gemini to require a funded billing account (see below). Three ways to supply
an AI Studio key, in order of precedence:
1. **`.env` file (recommended for local dev)** — copy `.env.example` to
   `.env` and paste your key in as `GEMINI_API_KEY=...`. `.env` is gitignored
   and loaded automatically by `app.py` on startup via `python-dotenv`; it
   never gets committed.
2. **Environment variable** — `export GEMINI_API_KEY=...` before launching.
3. **Sidebar input** — paste it into the app at runtime if you'd rather not
   use a file; kept in Streamlit's session memory only, never written to
   disk.

(This originally targeted Gemini, switched to Groq after an earlier Gemini
key returned quota limit: 0 without a funded Google Cloud billing account,
then switched back once it became clear that failure was specific to Cloud
Console/Vertex AI-issued keys rather than Gemini itself. `ai_assistant.py`
uses the official `google-genai` Python SDK — the current package; the older
`google-generativeai` package it might be confused with was fully
deprecated in November 2025.)

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
evidence in the whole project" (per the Findings section above) would have
no way to be demoed without live SEC/Yahoo Finance access.

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

## Findings

The full evidence behind [VERDICT.md](VERDICT.md)'s verdict, split into the same
three parts.

### Part 1: Wave 1 fintech has largely lost

**Price evidence** (`charts/indexed_performance.png`, `data/raw/prices.csv`), rebasing each company's stock to 100 at its start date:

| Ticker | Category | Peak (indexed) | Peak date | Value at 2026-07-02 |
|---|---|---|---|---|
| XYZ (Block) | embedded finance | **779** | 2021-08-05 | 218 |
| PYPL (PayPal) | embedded finance | 418 | 2021-07-23 | **62** (below 2018 start) |
| SOFI | neobank | 264 | 2025-11-12 | 150 |
| NU (Nubank) | neobank | 182 | 2026-01-28 | 132 |
| JPM | traditional bank | n/a | steady climb | **389** |
| BCS (Barclays) | traditional bank | n/a | steady climb | 335 |
| HSBC | traditional bank | n/a | steady climb | 299 |

The disruptors had a real, dramatic run in 2020-2021: Block up nearly 8x, PayPal over 4x. It didn't hold. PayPal is the only company here to end up below its own starting price five years later. Traditional banks, which barely participated in the 2021 boom, have compounded steadily since 2023-2024 and are now either the best performer (JPM) or fully caught up (BCS, HSBC).

**Profitability evidence** (`data/raw/fundamentals.csv`, now wired into the Wave 1 sub-index as `wave1_profitability`; see `build_index.py`'s `load_profitability()`):

| Ticker | 2022 net income | 2023 net income |
|---|---|---|
| SOFI | **-$320M** | -$301M |
| XYZ (Block) | **-$541M** | +$10M |
| NU (Nubank) | **-$365M** | +$1,031M |
| JPM | +$37.7B | +$49.6B |
| HSBC | +$15.6B | +$23.5B |

2022 was a losing year for these three disruptors, while both banks' profits grew substantially. Quantified as fintech-basket-average YoY growth minus legacy-basket-average YoY growth (a symmetric formula, since several fintech tickers cross from loss to profit and a plain percent change would explode): the fintech basket closed that gap sharply in fiscal 2023-2024 (+0.97, +1.03 on a roughly [-2, 2] scale), then gave it back in fiscal 2025 (-0.06, back to roughly even growth). `yfinance` only exposes ~4 fiscal years per company, so this is 3 annual points, not a monthly series: thin by the same standard applied to the EDGAR and search signals, and why the Wave 1 Chow F-statistics below shifted when this was added.

**Generalization check** (`collect_market_marketwide.py`, `data/raw/market_marketwide.csv`, `charts/market_marketwide.png`) asks Part 2's EDGAR question of the price signal: is "fintech rose then rolled over" a fact about the 7 picked tickers, or the sector? FINX (fintech-sector ETF) relative to KBWB (bank-sector ETF) peaked at **233** (rebased to 100 at 2018) in **September 2020**, then fell to **56** by July 2026, below its 2018 start. The 7-ticker sample peaked at **519** the same month and sits at **73** by July 2026, also below start. Different amplitude, same shape, same turning point, found independently: the "fintech's win didn't hold" story isn't an artifact of which 7 companies got picked.

**What this can't confirm:** whether banks won by copying features or acquiring challengers is plausible but untested here; there's no product-feature or M&A data in this project. Treat that mechanism as outside knowledge, not a finding.

**Structural break confirmation** (`output/break_results.json`, `charts/two_wave_index.png`): the Wave 1 sub-index (now three inputs: price, search, profitability) shows a significant break at **April 2021** (Chow F=17.259, p<0.001), rolling from rising to declining, and a second at **June 2025** (F=4.09, p=0.021), a partial rebound, still significant at 5% but visibly weaker than the price-only version, since profitability is flat through most of 2021 and only moves in 2023-2025. Momentum (`charts/momentum_handoff.png`) is negative for most of 2021-2025: literally losing ground year over year during what this project calls Wave 1's "disruption." Composite FDI now shows both breaks too (F=7.517, p=0.001 at April 2021; F=22.971, p<0.001 at June 2025), where previously only June 2025 cleared threshold: adding profitability strengthened the case for April 2021 as a real break, not just a price artifact.

### Part 2: Wave 2 (AI-native finance) is not yet measurable

This project can't price "is AI-native finance winning" the way it can Wave 1: the companies that would represent that wave are mostly private or too newly public for real stock history. Forcing a market-price answer would mean reading a signal into a handful of thin, noisy tickers that isn't really there. The honest move here is to say so, and treat the thinness of every measurable proxy as evidence the wave is early, not absent.

**SEC filings**, the sharpest signal, thin by design not accident (`data/raw/edgar_mentions.csv`, charted against the market-wide check in `charts/edgar_marketwide.png`). Filings were searched for `"artificial intelligence"` (`ai_broad`, the saturated baseline) and the "AI agent"/"agentic AI" phrase family (`agentic`, Wave-2-specific). By year, summed across all 7 companies:

| Year | `agentic` mentions | `ai_broad` mentions |
|---|---|---|
| 2019-2025 | **0 every year** | 1 → 3 → 4 → 5 → 5 → 7 → 7 |
| 2026 | **5 total** (JPM, HSBC, Barclays, PayPal, Block: one filing each) | 7 |

Seven straight years of zero, then five filings in the latest cycle across seven companies: a real, dated first appearance in a legally binding disclosure, not marketing copy, but still thin enough not to over-read. `ai_broad`, for comparison, is already saturated by 2019, confirming it's a baseline, not a discriminator.

**Checked against the entire market**, not just these 7 (`collect_edgar_marketwide.py`, `data/raw/edgar_marketwide.csv`, `charts/edgar_marketwide.png`): same `agentic` query, form type, and years, but no company filter, across every 10-K filer:

| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Market-wide `agentic` filings | 5 | 1 | 0 | 1 | 3 | 6 | **111** | **388** |

This is the single strongest evidence in the project that the thinness is early, not an artifact of a 7-company sample. Market-wide, `agentic` language sits in the low single digits, against tens of thousands of filers, for six straight years, then jumps roughly 18x in 2025 and grows further in 2026: same shape as the 7-company sample, different scale, found independently. It directly answers the obvious objection: no, this isn't just an artifact of which 7 companies got picked.

(Two points needed manual re-verification: the unscoped query is flakier than per-company ones, returning a spurious `0` for `ai_broad` 2026 on first pull, 3640 on retry, consistent with 2025's 3324, and `agentic` 2024 failed its automatic retries and was re-queried by hand to 6. Recorded in `collect_edgar_marketwide.py`'s comments; worth knowing if you re-run this and see a suspicious zero.)

**Search attention:** Wave 2 terms ("AI agent finance", "agentic AI banking", "autonomous wealth management") register literally zero interest every year from 2018 through 2023. Interest turns on in 2024-2025 and reaches ~22 by 2026: real, but from a standing start over two years, still below Wave 1's level.

**No market proxy exists.** Unlike Wave 1, there's no "AI-native fintech" stock basket here, because the relevant companies aren't public. That's not a gap to fix with more tickers; it's the state of the world this verdict describes.

### Part 3: The likely winner is the banks, again, plausible but not proven

The dramatic version of the Wave 2 thesis assumes banks are too encumbered by legacy infrastructure to use AI, leaving room for an AI-native challenger to repeat the Wave 1 playbook. That's not well supported here, and one data point leans the other way: **all five companies whose 2026 filings mention `agentic` language are already-established incumbents: JPM, HSBC, Barclays, PayPal, Block.** None are new AI-native entrants, because none exist in the sample. Neither neobank, SoFi or Nubank, shows `agentic` language even in 2026; the signal sits entirely with traditional banks and older, already-public embedded-finance players, the opposite of what an "AI-native upstart" thesis would predict.

This is **consistent with** incumbents moving first, not **proof of** it. The dataset is public companies only, which structurally excludes any private AI-native challenger moving as fast or faster out of view. Absence of a counter-example in a sample that couldn't contain one either way is weak evidence. What actually tips the prediction toward "banks win again" is mostly outside this codebase: balance-sheet scale, existing compute/data budgets, and the fact that (per Part 1) banks currently have the profits to fund an AI build-out while several Wave 1 challengers were posting losses as recently as 2022-2023.

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
- **Findings Part 3 above (banks likely absorb the AI wave) is a prediction,
  explicitly labeled as such.** It should not be cited with the same
  confidence as the parts that describe what already happened.

## Config

All tunable parameters (ticker baskets, keyword groups, composite weight,
resampling frequency, PELT penalty) live in the `CONFIG` block at the top of
`build_index.py`.
