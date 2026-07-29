# Fintech Two-Wave Disruption Index

Empirically testing whether fintech disruption of traditional banking has run its
course, or whether a **second wave of AI-native financial services** is only now
beginning.

Rather than asking the trivial question ("did fintech disrupt banking?" — yes),
this project looks for **two separate turning points**: the maturation of
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

Turning points are detected on each sub-index's **12-month momentum** using
PELT (`ruptures`). Instead of attaching a p-value to each one, every turning
point is scored for **stability**: the share of a parameter grid (penalty ×
momentum window) that also finds it. A turning point that survives most settings
is a real regime change; one that only appears at a single exact setting is
fragile. Each sub-index is re-standardised to unit variance after averaging its
inputs, so PELT's penalty means the same thing regardless of how many raw signals
feed a given wave (Wave 1 now averages three, Wave 2 still averages two).

> **Why not a Chow test?** An earlier version ran a classical Chow test at each
> PELT-detected break and reported an F-stat / p-value. That was dropped: the
> break date is *estimated* from the same data the Chow test then evaluates
> (textbook pre-test bias, so the p-values overstated significance), and the
> 12-month momentum transform induces serial correlation that violates the test's
> iid assumption. The stability sweep needs no distributional assumption and is
> easier to defend to a non-technical audience — "this turning point holds no
> matter how we set the knobs" beats "F = 17.3."

Three standalone checks ask whether the headline findings survive beyond the
hand-picked sample and the specific method:
`collect_edgar_marketwide.py` reruns the EDGAR "agentic" query with no company
filter across every SEC 10-K filer; `collect_market_marketwide.py` compares a
fintech-sector ETF (FINX) against a bank-sector ETF (KBWB) instead of the 7
tickers, **and** benchmarks the fintech basket against growth ETFs (QQQ, ARKK) to
separate a fintech-specific decline from the 2022 growth-stock selloff. None feed
into the composite FDI — they're validation charts, not additional index inputs.

## Repository layout

```
.
├── .github/workflows/monthly-refresh.yml # scheduled monthly data refresh -> PR
├── requirements.txt       # pip dependencies (README Quick start mirrors this)
├── collect_market_data.py # data collection: prices, fundamentals, indexed performance
├── collect_market_marketwide.py # check: 7-ticker sample vs. FINX/KBWB sector ETFs
├── collect_trends.py      # data collection: Google Trends, Wave 1 & 2 keyword groups
├── collect_edgar.py       # data collection: SEC EDGAR filing mentions
├── collect_edgar_marketwide.py # check: 7-company sample vs. every SEC 10-K filer
├── build_index.py         # builds sub-indices + composite, runs break tests
├── make_charts.py         # the three headline charts (reads output/, writes charts/)
├── app.py                 # Streamlit app: live sliders, recomputes in real time
├── ai_assistant.py        # Gemini research assistant: live summary + Q&A, used by app.py
├── robustness_agent.py    # Gemini tool-calling agent: sweeps parameters to stress-test the breaks
├── data/
│   ├── raw/                   # prices.csv, fundamentals.csv, indexed_performance.csv,
│   │                          # market_marketwide.csv, wave1_trends.csv, wave2_trends.csv,
│   │                          # edgar_mentions.csv, edgar_marketwide.csv
│   └── processed/             # trends_yearly.csv
├── charts/                # per-collector charts + the three headline charts (*.png)
├── output/                # fdi.csv, break_results.json, robustness_report.md (from build_index.py / robustness_agent.py)
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

**`collect_market_marketwide.py`** — checks the price story against a
market-wide baseline: FINX (fintech-sector ETF) vs. KBWB (bank-sector ETF),
instead of the 7 hand-picked tickers. Standalone generalization check, not
fed into the composite. Writes:
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
project. Covers all 7 tickers from the market-price basket, including BCS
and NU (both 20-F filers). Writes:
- `data/raw/edgar_mentions.csv` — long format, one row per company/year/query

No chart of its own — see `collect_edgar_marketwide.py` below, which reads
this CSV and charts the `agentic` series against the entire market.

**`collect_edgar_marketwide.py`** — extends `collect_edgar.py`'s `agentic`
query with no company filter, across every 10-K filer in EDGAR, to check
whether the 7-company sample's near-zero-then-2026 shape is real or just an
artifact of which 7 companies got picked. Writes:
- `data/raw/edgar_marketwide.csv` — year, query, total_filings (market-wide)
- `charts/edgar_marketwide.png` — 7-company sample vs. market-wide, `agentic` query

Also accepts `--synthetic` (see **Synthetic demo mode** below).

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
momentum to find turning points, labels each one's direction (slowdown /
acceleration), and scores it for stability by re-running detection across a grid
of penalties and momentum windows (what fraction of settings find the same
turning point). Writes `output/fdi.csv` and `output/break_results.json`.

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

## Automation

`.github/workflows/monthly-refresh.yml` re-runs the full pipeline above —
all collectors, `build_index.py`, `make_charts.py` — once a month (matching
the index's monthly resolution) and opens a pull request with whatever
changed in `data/`, `output/`, and `charts/`, rather than pushing straight to
`main`. Can also be run on demand from the Actions tab (`workflow_dispatch`).

Each collector step runs independently, so one flaky source doesn't block
the rest of the refresh; the workflow then verifies `build_index.py`'s
required inputs exist before building, and fails loudly if one is missing.
The most likely failure is `collect_trends.py` — Google frequently
rate-limits/blocks pytrends requests from the datacenter IP ranges
GitHub-hosted runners use, even when the same script works fine locally.

One-time setup before this can open PRs: **Settings → Actions → General →
Workflow permissions → enable "Allow GitHub Actions to create and approve
pull requests."**

## Interactive dashboard

```bash
pip install -r requirements.txt
uvicorn server:app --reload
# open http://127.0.0.1:8000
```

The dashboard is a small **FastAPI backend** (`server.py`) serving a plain
**HTML/JS/Plotly frontend** (`static/`). Every chart is drawn in the browser
from real numbers returned as JSON — nothing is shipped as a PNG. It is
organised as the project's stages, left to right:

1. **Data Collection** — the four raw sources, plus the revenue-share
   market-share proxy.
2. **Index Construction** — Wave 1 / Wave 2 sub-indices and the composite FDI,
   recomputed live from sidebar sliders (`W1_WEIGHT`, PELT penalty, momentum
   window).
3. **Turning Points** — PELT-detected turning points, each with a direction
   (slowdown / acceleration) and a stability score.
4. **Robustness Checks** — the sector-ETF and market-wide EDGAR generalization
   checks, the growth-benchmark macro-confound control, and the Gemini
   robustness agent.
5. **Converging Evidence** — every signal on one z-scored, smoothed scale, so
   the reader can see the independent sources agree on the two turning points.
6. **Verdict & AI Assistant** — `VERDICT.md` + README findings, plus the Gemini
   summary and Q&A.

The endpoints import `build_indices()` and `run_break_analysis()` straight from
`build_index.py` (which accepts `momentum_window`/`pelt_penalty` overrides,
defaulting to the same `CONFIG` constants the CLI uses), so the live numbers
can never drift from the pipeline. If `data/raw/*.csv` is missing, a sidebar
toggle switches to the same synthetic demo data as `--synthetic` elsewhere
(clearly labeled — moving sliders changes how the data is combined and tested,
never which data is loaded).

### AI Research Assistant (Gemini)

Below the charts, an "AI Research Assistant" section (`ai_assistant.py`) adds
two Gemini-powered features, both grounded in the exact `df`/`breaks` objects
the server just recomputed — never a static copy of `VERDICT.md`:

- **Live summary** — regenerates a short executive-summary paragraph that
  reflects whatever the sliders are *currently* set to, so you can compare it
  against `VERDICT.md`'s written verdict at the default 50/50 weight.
- **Ask a question** — a chat interface for questions about the current run
  (turning-point dates, stability scores, what a limitation means, etc.).

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
product. Three ways to supply an AI Studio key, in order of precedence:
1. **`.env` file (recommended for local dev)** — put `GEMINI_API_KEY=...` in
   this project's gitignored `.env` file, loaded automatically by `server.py`
   via `python-dotenv`.
2. **Environment variable** — `export GEMINI_API_KEY=...` before launching.
3. **Sidebar input** — paste it into the dashboard at runtime instead; kept in
   the browser's memory only and sent per-request, never written to disk.

If no key is present through any of these, the app still runs normally —
this section just shows the key prompt instead of the summary/chat tabs.

### Robustness agent (Gemini)

Below the AI Research Assistant, a "Robustness agent" section
(`robustness_agent.py`) adds a genuinely different kind of AI feature: not
another grounded-summary call, but a multi-step **tool-calling agent** that
stress-tests this project's own headline structural breaks against the
choice of parameters that produced them.

It is given exactly one tool, `probe(w1_weight, pelt_penalty,
momentum_window)` — a thin wrapper around `build_index.py`'s own
`build_indices()`/`run_break_analysis()`, no separate statistics — and is
told to: probe the project's own default parameters first (establishing
what "the headline breaks" are, rather than having break dates hardcoded
into its prompt), then decide for itself which further parameter
combinations to test, within the same bounds `app.py`'s sliders already
enforce (`w1_weight` 0–1, `pelt_penalty` 0.5–10, `momentum_window` 3–24
months). It stops once it has enough evidence and writes a verdict: which
breaks are **robust** (survive most reasonable settings), **fragile** (only
appear at the exact reported parameters), or **parameter-dependent**
(survive some directions but not others) — citing only the turning-point
dates, directions, and stability scores each probe actually returned, never an
invented number. (This is the qualitative, LLM-driven companion to the
deterministic stability score `build_index.py` already computes.)

Click "Run robustness agent" to see the loop happen live: an expander shows
every probe it chose to run and what it found, followed by its written
verdict below. This checks robustness of the **statistical method** to
parameter choice — it is a validity check, not new evidence for or against
the two-wave thesis, and its own parameter choices can never wander outside
the sliders' existing ranges.

Uses the same Gemini API key as the assistant above (see setup steps
above) — no separate key needed. One real constraint worth knowing: Gemini's
free tier caps `gemini-3.6-flash` at roughly **20 requests per day per
project** (confirmed empirically via a 429 response's quota detail, not
documented with an exact number anywhere public), shared across this agent
and the assistant above. Each agent run costs one request per probe plus a
final verdict call, so the in-app probe budget slider defaults to a modest
6 and caps at 8 to leave room for the rest of the day's usage. If the day's
quota is already spent, the app fails fast with a clear message rather than
retrying against a wall that won't come down for hours — see
`robustness_agent.py`'s `_generate_with_retry()` for how it tells a
transient per-minute rate limit (worth a short retry) apart from a
per-day quota exhaustion (not worth retrying at all).

Also runnable standalone: `python robustness_agent.py [--synthetic]`
prints the full probe trace and verdict to the console and writes
`output/robustness_report.md` (or `_synthetic.md`).

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
for all four collectors' outputs directly. `collect_edgar_marketwide.py` and
`collect_market_marketwide.py` are standalone checks that never flow through
`build_index.py`, so each needed its own synthetic path for an offline
fallback.

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
- `output/break_results.json` — detected turning points + direction + stability score per series
- seven chart PNGs in `charts/` — see below
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

2022 was a losing year for these three disruptors, while both banks' profits grew substantially. Quantified as fintech-basket-average YoY growth minus legacy-basket-average YoY growth (a symmetric formula, since several fintech tickers cross from loss to profit and a plain percent change would explode): the fintech basket closed that gap sharply in fiscal 2023-2024 (+0.97, +1.03 on a roughly [-2, 2] scale), then gave it back in fiscal 2025 (-0.06, back to roughly even growth). `yfinance` only exposes ~4 fiscal years per company, so this is 3 annual points, not a monthly series: thin by the same standard applied to the EDGAR and search signals.

**Market-share proxy** (`data/raw/fundamentals.csv` revenue column, Data Collection tab): the thesis question is literally about *market share*, which stock price only proxies (a stock can fall while the business keeps growing). Fintech's share of the combined (fintech + legacy) **revenue** pool went **19.4% (2022) → 19.5% → 20.3% → 20.3% (2025)** — essentially flat. Even as the fintechs returned to profit, they stopped taking ground: consistent with "Wave 1 has matured", and a more direct read on the thesis than price. Thin by construction (yfinance exposes ~4 fiscal years), so it's a recent snapshot, not a long history.

**Generalization check** (`collect_market_marketwide.py`, `data/raw/market_marketwide.csv`, `charts/market_marketwide.png`) asks Part 2's EDGAR question of the price signal: is "fintech rose then rolled over" a fact about the 7 picked tickers, or the sector? FINX (fintech-sector ETF) relative to KBWB (bank-sector ETF) peaked at **233** (rebased to 100 at 2018) in **September 2020**, then fell to **56** by July 2026, below its 2018 start. The 7-ticker sample peaked at **519** the same month and sits at **73** by July 2026, also below start. Different amplitude, same shape, same turning point, found independently: the "fintech's win didn't hold" story isn't an artifact of which 7 companies got picked.

**Macro-confound control** (`collect_market_marketwide.py`, QQQ/ARKK, Robustness tab): the obvious objection to "fintech rolled over ~2021" is that *every* unprofitable growth stock sold off in 2022's rate-hike cycle. The FINX/KBWB check above rules out "just the 7 tickers"; this rules out "just the growth selloff." Benchmarked against **QQQ** (Nasdaq-100 growth), the fintech basket peaked at **205** (Dec 2020) and fell to **63** by July 2026 — it underperformed even the broad growth market by ~37% over the period, so the decline is fintech-specific, not the whole growth tide going out. The one honest nuance: against **ARKK** (the most speculative disruptive-growth basket) fintech held up (ending ~142), i.e. it beat the *riskiest* growth bucket while losing to the mainstream one.

**What this can't confirm:** whether banks won by copying features or acquiring challengers is plausible but untested here; there's no product-feature or M&A data in this project. Treat that mechanism as outside knowledge, not a finding.

**Turning-point confirmation** (`output/break_results.json`, `charts/two_wave_index.png`): the Wave 1 sub-index (three inputs: price, search, profitability) has a turning point at **April 2021** — a **slowdown**, momentum rolling from rising to declining — that is **robust**, reappearing under **75% (15/20)** of penalty × momentum-window settings. A second at **June 2025** (an **acceleration**, partial rebound) is nearly as stable at **70% (14/20)**. Momentum (`charts/momentum_handoff.png`) is negative for most of 2021-2025: literally losing ground year over year during what this project calls Wave 1's "disruption." The composite FDI shows the same June 2025 acceleration robustly (**75%**), but its April 2021 slowdown is **fragile** (only **35%, 7/20**) — an honest caveat: blending the waves *weakens* the 2021 signal that is strong in Wave 1 alone, which is exactly why the project keeps the sub-indices separate rather than reading the composite. (This replaces an earlier Chow test whose p-values were biased by estimating the break date from the same data — see the "Why not a Chow test?" note above.)

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
