# Fintech Two-Wave Disruption Index

Empirically testing whether fintech disruption of traditional banking has run its
course, or whether a **second wave of AI-native financial services** is only now
beginning.

Rather than asking the trivial question ("did fintech disrupt banking?" — yes),
this project tests for **two separate structural breaks**: the maturation of
Wave 1 (payments, neobanks, embedded finance) and the onset of Wave 2 (AI-native
underwriting and advisory).

## The finding in one sentence

Wave 1 peaks in 2020 and rolls over by April 2021, then grinds lower for three
straight years before an abrupt (and still-thin) rebound from mid-2025, while
Wave 2 stays flat-to-negative until a genuine acceleration begins in August
2024 and roughly triples in strength by mid-2026 — two separately-dated,
statistically significant breaks (Chow p < 0.001) rather than one continuous
trend.

> **Nuance:** the blended composite FDI does *not* cancel this signal the way
> the original hypothesis expected. Because Wave 1 and Wave 2 happen to both
> inflect upward within the same few months of 2025, the FDI's detected break
> dates are identical to Wave 1's alone — so right now the composite is
> dominated by Wave 1's swings rather than cleanly averaging away two distinct
> stories. Also note the final one to two months of data (Jun-Jul 2026) reverse
> sharply in *both* sub-indices; treat that tail as noisy/unconfirmed, not a
> new trend — see `charts/two_wave_index.png` and `output/fdi.csv`.

> **Status:** `build_index.py` requires all three collectors' real output to
> be present and fails loudly (`FileNotFoundError`) if any is missing — there
> is no *automatic* synthetic-data fallback. (An earlier version silently
> substituted fabricated placeholder data whenever a real CSV was missing,
> because its loader paths were wrong; that auto-fallback is gone now that the
> paths are fixed.) A synthetic **demo mode** still exists, but only runs when
> explicitly requested with `--synthetic`, and it always writes to separate
> `*_synthetic.*` files/charts so it can never be confused with, or overwrite,
> a real result — see **Synthetic demo mode** below.

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

Both `collect_trends.py` and `collect_edgar.py` need live internet access
(trends.google.com / efts.sec.gov), which a sandboxed environment may block.
For demoing the *method* without that access, `build_index.py` and
`make_charts.py` both accept `--synthetic`:

```bash
python build_index.py --synthetic    # writes output/fdi_synthetic.csv,
                                      # output/break_results_synthetic.json
python make_charts.py --synthetic    # reads those, writes charts/*_synthetic.png
```

This is opt-in only — it never triggers automatically, and it never touches
`output/fdi.csv` / `output/break_results.json` / the non-suffixed chart PNGs,
so it can't be confused with, or silently overwrite, a real result. Every
synthetic chart is watermarked "SYNTHETIC DEMO DATA -- NOT A REAL RESULT" and
the console output prints the same warning. **The synthetic result is a
demonstration that the pipeline and break-detection method work end to end —
it is not evidence for or against the two-wave thesis**, since its shape
(Wave 1 rising then plateauing, Wave 2 flat then accelerating) is baked in by
construction in `synthetic_sources()`.

## Outputs

- `output/fdi.csv` — monthly sub-indices and composite FDI
- `output/break_results.json` — detected break dates + Chow F/p per series
- six chart PNGs in `charts/` — see below
- (if `--synthetic` was used) matching `output/*_synthetic.*` and
  `charts/*_synthetic.png` files, entirely separate from the real ones above

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