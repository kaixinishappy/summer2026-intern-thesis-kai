# Fintech Two-Wave Disruption Index

Empirically testing whether fintech disruption of traditional banking has run its
course, or whether a **second wave of AI-native financial services** is only now
beginning.

Rather than asking the trivial question ("did fintech disrupt banking?" — yes),
this project tests for **two separate structural breaks**: the maturation of
Wave 1 (payments, neobanks, embedded finance) and the onset of Wave 2 (AI-native
underwriting and advisory).

## The finding in one sentence

Wave 1 momentum plateaus around 2020–2021 while Wave 2 momentum accelerates from
~2023 — a detectable *handoff* rather than one continuous trend — and a blended
"fintech index" misses it entirely because averaging the two waves cancels the
signal.

> **Status:** `build_index.py` now loads real collector output (it prints
> `Data source: REAL`). It previously fell back to synthetic data silently
> because its loaders pointed at `data/market.csv` / `data/trends.csv` /
> `data/edgar.csv`, which never existed — fixed to read the actual paths in
> `data/raw/`. The ticker baskets, trend-term lists, and the EDGAR loader
> (which expects a different, long-format schema) were also out of sync with
> the collectors and have been corrected.

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
- `charts/edgar_mentions.png`

**`build_index.py`** — the combination step. Loads the three collectors'
real output (falls back to synthetic placeholder data with the two-wave shape
baked in only if any real file is missing, or `--synthetic` is passed),
resamples everything to monthly and z-scores it, then:
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
#    prints "Data source: REAL" once all three collectors' CSVs exist
python build_index.py

# 3. generate the three headline charts -> charts/*.png
python make_charts.py
```

No data yet? `python build_index.py --synthetic` runs the full pipeline on
placeholder data with the two-wave shape baked in, so you can see the method work
end to end. **Synthetic output is a demonstration of the method, not evidence** —
every chart and the console output are tagged as synthetic.

## Outputs

- `output/fdi.csv` — monthly sub-indices and composite FDI
- `output/break_results.json` — detected break dates + Chow F/p per series
- six chart PNGs in `charts/` — see below

## Charts, explained

Three per-collector diagnostic charts (one per data source, sanity-checks the
raw signal), plus three headline charts (built from the combined index).
Descriptions below reflect the current real-data run, not a hypothetical.

**`charts/indexed_performance.png`** (from `collect_market_data.py`) — every
ticker's price rebased to 100 at its 2018 start date, one line per company,
colored by category. Currently shows fintech/embedded-finance names (XYZ,
PYPL) spiking to 6-7x their starting price through 2021 while the traditional
banks barely move, then fintech giving almost all of that back by 2022-2023
while JPM/HSBC/BCS grind steadily upward and end up *ahead* of PYPL and XYZ by
2026 — the raw price evidence behind the "Wave 1 plateaued" claim.

**`charts/trends_comparison.png`** (from `collect_trends.py`) — average
yearly Google Trends interest for the Wave 1 term group vs. the Wave 2 term
group. Wave 1 interest is flat-to-declining 2018-2024 then ticks back up;
Wave 2 interest is literally zero every year through 2023 (nobody was
searching "agentic AI banking" before then) and only turns on in 2024-2025,
reaching ~22 (still well below Wave 1's ~34) by 2026 — the "Wave 2 is only
just beginning" claim, visible directly in search behavior.

**`charts/edgar_mentions.png`** (from `collect_edgar.py`) — count of filings
per year matching `"artificial intelligence"` (the `ai_broad` query), grouped
by company category. Nearly every company mentions AI in nearly every annual
filing every year back to 2019 — this series is a saturated baseline (as the
collector script's own docstring predicts), which is why it's mainly useful
as a steady denominator rather than a discriminating signal on its own. (The
`agentic`-phrase-family query, not charted here, is the one expected to be
genuinely near-zero before ~2023; see `data/raw/edgar_mentions.csv`.)

**`charts/two_wave_index.png`** — the two z-scored sub-indices plus the
composite FDI, with detected break dates annotated as vertical lines. In the
current run: Wave 1 peaks around late 2020/2021, declines through 2023-2024,
then partially recovers into 2026; Wave 2 stays near/below zero until
2022 and then rises steadily, overtaking Wave 1 by mid-2025 and pulling well
ahead by 2026. Breaks land at Apr 2021 and Jun 2025 for Wave 1, Feb 2022 and
Aug 2024 for Wave 2 — all significant at the 5% level (Chow p < 0.001).

**`charts/momentum_handoff.png`** — the 12-month change (momentum) in each
sub-index, the same data the break detection actually runs on. Wave 1
momentum is negative for most of 2021-2025 (red-shaded region — literally
losing ground year over year) while Wave 2 momentum is positive and rising
over the same stretch; both spike together at the very end of the series
(2026), which is the composite FDI's most recent and least-confirmed move —
worth treating as provisional rather than a settled trend given how few
months of data support it.

**`charts/incumbent_response.png`** — market relative strength (red, left
axis) against EDGAR AI-language intensity (blue, right axis) on a dual-axis
plot. Note the EDGAR line moves in straight interpolated segments between
year-end points, since it's genuinely annual data resampled to monthly, not a
monthly-native series. Shows fintech market pressure peaking in 2021 while AI
disclosure language actually dips in 2023-2024 before climbing again toward
2025-2026 — i.e. incumbents' AI-language ramp doesn't line up neatly with when
market pressure from fintech was highest, it shows up later.

## Method notes & limitations

- Breaks are detected on *momentum* (12-month difference) so a plateau registers
  as a clean mean shift, which is both statistically tractable and easy to
  interpret ("growth stopped here").
- Search interest measures *attention*, not adoption; filing language measures
  what incumbents *say*, not what they ship. Both are treated as leading
  indicators, not ground truth.
- The Wave 2 window is short (~3 years), so the onset signal cannot yet be
  distinguished from a spike. See `VERDICT.md` for the full treatment.

## Config

All tunable parameters (ticker baskets, keyword groups, composite weight,
resampling frequency, PELT penalty) live in the `CONFIG` block at the top of
`build_index.py`.