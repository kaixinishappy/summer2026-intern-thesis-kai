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

> **Status:** `build_index.py` currently falls back to synthetic placeholder
> data — its loaders look for `data/market.csv`, `data/trends.csv`,
> `data/edgar.csv`, which don't exist; the collectors write elsewhere (see
> layout below). It prints `Data source: SYNTHETIC (placeholder)` when this
> happens. The finding above describes the intended result, not yet a
> real-data-confirmed one. The loader paths need to be fixed before the
> output can be trusted.

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

## Quick start

```bash
pip install requests pandas numpy scipy statsmodels ruptures matplotlib pytrends

# 1. collect data -> writes data/raw/*.csv, data/processed/*.csv, charts/*.png
python collect_market_data.py
python collect_trends.py
python collect_edgar.py

# 2. build indices + run structural break tests -> output/fdi.csv, break_results.json
#    NOTE: currently always prints "Data source: SYNTHETIC (placeholder)" --
#    see Status note above.
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
- `charts/two_wave_index.png` — the two sub-indices and composite, breaks annotated
- `charts/momentum_handoff.png` — 12-month momentum showing the Wave 1 → Wave 2 handoff
- `charts/incumbent_response.png` — market pressure vs. AI language in filings
- `charts/indexed_performance.png`, `charts/trends_comparison.png`, `charts/edgar_mentions.png`
  — per-collector diagnostic charts, one from each of the three collect_*.py scripts

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