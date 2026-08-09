# Fintech Disruption of Traditional Banking

This thesis examines whether the first wave of fintech disruption—digital
payments, neobanks, and embedded finance—has matured, or whether a second wave
of AI-native financial services is beginning.

It does not treat a single metric as proof. It combines market performance,
profitability, search interest, and regulatory disclosures, then tests whether
the resulting turning points survive alternative modelling choices.

## How it works

Four signals from three source systems (Yahoo Finance, Google Trends, and SEC
EDGAR) are normalised to a monthly frequency and combined into a **Fintech
Disruption Index (FDI)** with two sub-indices:

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


Turning points are detected on each sub-index's 12-month momentum with PELT
(`ruptures`). Each is assigned a stability score: the share of a penalty ×
momentum-window grid that also identifies it. This distinguishes robust regime
changes from breaks that only occur under one exact parameter setting.

Two standalone checks test generalisability without entering the composite FDI:
`collect_market_marketwide.py` compares FINX with KBWB rather than the selected
seven tickers, and `collect_edgar_marketwide.py` repeats the agentic-AI query
across all SEC 10-K filers.

## Tech stack

- **Language and analysis:** Python, pandas, NumPy, SciPy, statsmodels, and
  `ruptures` (PELT change-point detection).
- **Data sources and collection:** Yahoo Finance via `yfinance`, Google Trends
  via `pytrends`, and SEC EDGAR full-text search via `requests`.
- **Visualisation:** Matplotlib for generated charts; Plotly with plain
  HTML/CSS/JavaScript for the interactive dashboard.
- **Web application:** FastAPI and Uvicorn.
- **AI features:** Google Gemini via `google-genai`, with environment loading
  through `python-dotenv`.
- **Automation:** GitHub Actions creates a monthly refresh pull request.

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
├── classify_filings.py    # reads the agentic passages, LLM-classifies each as
│                          #   deploying / exploring / risk (sharpens Part 3)
├── build_index.py         # builds sub-indices + composite, runs break tests
├── make_charts.py         # the three headline charts (reads output/, writes charts/)
├── server.py              # FastAPI server for the interactive dashboard
├── static/                # HTML, CSS, and JavaScript dashboard frontend
│   ├── index.html         # dashboard page
│   └── assets/
│       ├── css/style.css  # styling
│       └── js/            # API client, charts, and UI behaviour
├── ai_assistant.py        # Gemini research assistant: live summary + Q&A
├── robustness_agent.py    # tool-using Gemini agent: red-teams the headline
│                          #   breaks by choosing its own parameter checks
├── filings_qa.py          # "Ask the filings": grounded Q&A over the real SEC
│                          #   filing passages, every claim cited to a quote
├── gemini_client.py       # shared Gemini client, retry, and timeout handling
├── predictions.py         # scores the standing prediction (PREDICTIONS.md)
│                          #   against fresh pipeline output, one row per refresh
├── PREDICTIONS.md         # the frozen, falsifiable forecast + its scorecard
├── data/
│   ├── raw/                   # prices.csv, fundamentals.csv, indexed_performance.csv,
│   │                          # market_marketwide.csv, wave1_trends.csv, wave2_trends.csv,
│   │                          # edgar_mentions.csv, edgar_marketwide.csv,
│   │                          # edgar_passages.csv, edgar_stance.csv
│   └── processed/             # trends_yearly.csv
├── charts/                # generated collector, validation, and headline charts
├── output/                # fdi.csv, break_results.json, robustness reports
├── VERDICT.md             # written verdict
└── README.md
```

## Quick start

Install all project dependencies:

```bash
pip install -r requirements.txt
```

Then run the data and analysis pipeline:

```bash
# 1. Collect primary data. Creates data/raw/, data/processed/, and source charts.
python collect_market_data.py
python collect_trends.py
python collect_edgar.py

# 2. Optional generalisation checks; these do not enter the composite FDI.
python collect_market_marketwide.py
python collect_edgar_marketwide.py

# 3. Optional: extract and classify filing passages.
#    The classification stage requires GEMINI_API_KEY.
python classify_filings.py

# 4. Build the FDI and detect structural breaks.
python build_index.py

# 5. Generate headline charts from output/fdi.csv and break_results.json.
python make_charts.py
```

To launch the dashboard, run the following after step 4:

```bash
# Optional: enables Gemini summary/chat, filing Q&A, and the robustness agent.
export GEMINI_API_KEY="your-ai-studio-key"

# Open http://127.0.0.1:8000 after this starts.
uvicorn server:app --reload
```

## Key results

The following results are from the committed real-data analysis at the default
50/50 composite weighting:

- **Wave 1 slowdown:** PELT identifies a slowdown in April 2021. It appears in
  15 of 20 penalty × momentum-window settings (**75% stability**).
- **Wave 2 acceleration:** PELT identifies an acceleration in June 2025. It
  appears in 19 of 20 settings (**95% stability**), but the short observation
  window means this is early evidence, not proof of a lasting disruption.
- **Composite FDI:** The June 2025 acceleration is stable across 15 of 20
  settings (**75%**). The April 2021 composite slowdown is only 35% stable, so
  the sub-indices should be interpreted alongside the composite.
- **Revenue-share proxy:** The fintech basket's share of the combined sampled
  fintech-and-bank revenue pool was broadly flat, moving from about **19.4% in
  2022** to **20.3% in 2025**. This is a sample-level proxy, not total industry
  market share.
- **Filing posture:** In the analysed passages, PayPal and Block describe AI
  agent deployment, while the large banks mainly frame agentic AI in terms of
  governance and risk. The inference that banks will absorb the AI wave is a
  **prediction**, not an empirical finding.

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
- **The stance split (deploying / exploring / risk) is an LLM judgment, not a
  measured quantity.** `classify_filings.py` labels each passage with Gemini
  and records the verbatim quote behind every label, so a reader can re-check
  it against the filing — but it is one model's reading of 19 passages, not a
  reproducible statistic, and could differ on a re-run or with a different
  model. It is meant to add a qualitative axis the keyword count can't, not to
  carry the same weight as the count itself. The `unclear` labels (2 of 19,
  both Barclays) mark passages the model itself declined to call.
