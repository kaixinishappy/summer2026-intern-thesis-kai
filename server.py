"""
server.py
=========
FastAPI backend for the Fintech Two-Wave Disruption Index dashboard.

Replaces app.py's Streamlit app: same live parameter recompute
(build_index.py) and same Gemini research assistant (ai_assistant.py) --
just exposed as a small JSON API consumed by a plain HTML/JS/Plotly
frontend (static/) instead of rendered server-side by Streamlit. Charts
are drawn in the browser from real numbers, not shipped as PNGs.

Run:
    pip install -r requirements.txt
    uvicorn server:app --reload
    open http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

# Anchored to this file's directory, not the current working directory, so
# `uvicorn server:app` finds .env regardless of where it's launched from.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ai_assistant
import robustness_agent
from build_index import (
    DATA_DIR,
    EDGAR_CSV,
    FINTECH_TICKERS,
    FUNDAMENTALS_CSV,
    LEGACY_TICKERS,
    MARKET_CSV,
    MOMENTUM_WINDOW,
    PELT_PENALTY,
    W1_WEIGHT,
    WAVE1_TREND_TERMS,
    WAVE1_TRENDS_CSV,
    WAVE2_TREND_TERMS,
    WAVE2_TRENDS_CSV,
    build_indices,
    run_break_analysis,
    zscore,
)
from collect_market_marketwide import relative_strength

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")

INDEXED_PERFORMANCE_CSV = os.path.join(RAW_DIR, "indexed_performance.csv")
TRENDS_YEARLY_CSV = os.path.join(PROCESSED_DIR, "trends_yearly.csv")
MARKET_MARKETWIDE_CSV = os.path.join(RAW_DIR, "market_marketwide.csv")
EDGAR_MARKETWIDE_CSV = os.path.join(RAW_DIR, "edgar_marketwide.csv")
EDGAR_STANCE_CSV = os.path.join(RAW_DIR, "edgar_stance.csv")

# Fixed ticker order (matches build_index.py's baskets) -- the frontend
# assigns chart colors by this order, never by rank, so a ticker keeps its
# color across charts and reruns.
TICKER_ORDER = list(LEGACY_TICKERS) + list(FINTECH_TICKERS)

app = FastAPI(title="Fintech Two-Wave Disruption Index API")

REAL_DATA_AVAILABLE = all(
    os.path.exists(p) for p in
    (MARKET_CSV, FUNDAMENTALS_CSV, WAVE1_TRENDS_CSV, WAVE2_TRENDS_CSV, EDGAR_CSV)
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _resolve_api_key(client_key: str | None) -> str | None:
    """Same precedence as app.py's sidebar: an explicit per-request key (the
    dashboard's equivalent of the old sidebar text input, kept in the
    browser's memory only) wins over the server's own .env/environment."""
    return client_key or os.environ.get("GEMINI_API_KEY")


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of records, NaN -> null."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _series_to_records(s: pd.Series, date_name: str, value_name: str) -> list[dict]:
    df = s.rename(value_name).reset_index()
    df.columns = [date_name, value_name]
    return _records(df)


def _require_file(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{os.path.basename(path)} not found -- run the collector script first.")


# --------------------------------------------------------------------------- #
# static frontend
# --------------------------------------------------------------------------- #

STATIC_DIR = os.path.join(HERE, "static")
app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")


@app.get("/")
def index_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #

@app.get("/api/status")
def status():
    return {
        "real_data_available": REAL_DATA_AVAILABLE,
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "defaults": {
            "w1_weight": W1_WEIGHT,
            "pelt_penalty": PELT_PENALTY,
            "momentum_window": MOMENTUM_WINDOW,
        },
        "tickers": {
            "legacy": LEGACY_TICKERS,
            "fintech": FINTECH_TICKERS,
            "order": TICKER_ORDER,
        },
        "trend_terms": {"wave1": WAVE1_TREND_TERMS, "wave2": WAVE2_TREND_TERMS},
    }


# --------------------------------------------------------------------------- #
# index construction + structural breaks (the "live recompute" endpoint --
# mirrors app.py's sidebar sliders exactly)
# --------------------------------------------------------------------------- #

@app.get("/api/index")
def get_index(
    w1_weight: float = Query(W1_WEIGHT, ge=0.0, le=1.0),
    pelt_penalty: float = Query(PELT_PENALTY, ge=0.5, le=10.0),
    momentum_window: int = Query(MOMENTUM_WINDOW, ge=3, le=24),
    synthetic: bool = Query(False),
):
    forced_synthetic = synthetic or not REAL_DATA_AVAILABLE
    try:
        res = build_indices(weight_w1=w1_weight, use_synthetic=forced_synthetic)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    breaks = run_break_analysis(res, momentum_window=momentum_window, pelt_penalty=pelt_penalty)

    df = res.df.reset_index().rename(columns={res.df.index.name or "index": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    return {
        "used_synthetic": res.used_synthetic,
        "forced_synthetic": forced_synthetic and not synthetic,
        "params": {"w1_weight": w1_weight, "pelt_penalty": pelt_penalty, "momentum_window": momentum_window},
        "records": _records(df),
        "breaks": breaks,
    }


# --------------------------------------------------------------------------- #
# data collection tab -- the four raw sources, real data only (no synthetic
# per-ticker/per-term breakdown exists; build_index.py's synthetic mode only
# fabricates the four already-aggregated series, see its synthetic_sources())
# --------------------------------------------------------------------------- #

@app.get("/api/data-collection")
def data_collection():
    if not REAL_DATA_AVAILABLE:
        raise HTTPException(status_code=404, detail="Real collector output not found.")

    _require_file(INDEXED_PERFORMANCE_CSV)
    prices = pd.read_csv(INDEXED_PERFORMANCE_CSV, parse_dates=["Date"])
    monthly = (
        prices.groupby("ticker", sort=False)
        .apply(lambda g: g.set_index("Date")[["indexed"]].resample("ME").last())
        .reset_index()
    )
    meta = prices[["ticker", "name", "category"]].drop_duplicates("ticker").set_index("ticker")
    monthly["name"] = monthly["ticker"].map(meta["name"])
    monthly["category"] = monthly["ticker"].map(meta["category"])
    monthly["Date"] = monthly["Date"].dt.strftime("%Y-%m-%d")

    _require_file(TRENDS_YEARLY_CSV)
    trends = pd.read_csv(TRENDS_YEARLY_CSV)

    _require_file(EDGAR_CSV)
    edgar = pd.read_csv(EDGAR_CSV)
    edgar_yearly = edgar.groupby(["year", "query"], as_index=False)["mentions"].sum()
    edgar_2026_agentic = (
        edgar[(edgar["year"] == 2026) & (edgar["query"] == "agentic") & (edgar["mentions"] > 0)]
        [["ticker", "name", "category", "mentions"]]
        .sort_values("mentions", ascending=False)
    )

    _require_file(FUNDAMENTALS_CSV)
    fundamentals = pd.read_csv(FUNDAMENTALS_CSV).sort_values(["category", "ticker", "fiscal_year"])

    return {
        "ticker_order": TICKER_ORDER,
        "indexed_performance": _records(monthly.rename(columns={"Date": "date", "indexed": "value"})),
        "trends_yearly": _records(trends),
        "edgar_yearly": _records(edgar_yearly),
        "edgar_2026_agentic": _records(edgar_2026_agentic),
        "fundamentals": _records(fundamentals),
        "revenue_share": _revenue_share(fundamentals),
    }


def _revenue_share(fundamentals: pd.DataFrame) -> list[dict]:
    """Fintech's share of the (fintech + legacy) revenue pool, per fiscal year --
    the market-share proxy the thesis question literally asks for ("taken
    significant market share"), which stock price only stands in for. Computed
    only for years where BOTH baskets report revenue, so a missing early year on
    one side can't distort the ratio. Thin by construction (yfinance exposes ~4
    fiscal years); shown as a recent-snapshot proxy, not a long history."""
    if "revenue" not in fundamentals.columns:
        return []
    fin = fundamentals.dropna(subset=["revenue"])
    rows = []
    for year, g in fin.groupby("fiscal_year"):
        fintech_rev = g[g["ticker"].isin(FINTECH_TICKERS)]["revenue"].sum()
        legacy_rev = g[g["ticker"].isin(LEGACY_TICKERS)]["revenue"].sum()
        has_fintech = g["ticker"].isin(FINTECH_TICKERS).any()
        has_legacy = g["ticker"].isin(LEGACY_TICKERS).any()
        if not (has_fintech and has_legacy) or (fintech_rev + legacy_rev) == 0:
            continue
        rows.append({
            "fiscal_year": int(year),
            "fintech_revenue": float(fintech_rev),
            "legacy_revenue": float(legacy_rev),
            "fintech_share_pct": round(100 * fintech_rev / (fintech_rev + legacy_rev), 2),
        })
    return rows


# --------------------------------------------------------------------------- #
# EDGAR agentic-language STANCE -- classify_filings.py's read of what each
# company's agentic passages actually SAY (deploying / exploring / risk), not
# just how many there are. Separate route from /api/data-collection on purpose:
# the count table only needs the collectors, but stance needs the (API-key,
# LLM) classify stage to have run, so a missing edgar_stance.csv degrades this
# panel alone instead of 404-ing the whole Data Collection tab.
# --------------------------------------------------------------------------- #

# Stances ordered strongest-adoption -> weakest, so the frontend can render a
# stacked bar in a stable, meaningful left-to-right order regardless of counts.
STANCE_ORDER = ["deploying", "exploring", "risk", "unclear"]


@app.get("/api/edgar-stance")
def edgar_stance():
    """Per-company stance mix + the underlying classified passages. Returns
    available=False (not an error) when classify_filings.py hasn't been run,
    so the frontend can show a 'not yet classified' hint rather than a failure."""
    if not os.path.exists(EDGAR_STANCE_CSV):
        return {"available": False,
                "detail": "edgar_stance.csv not found -- run: python classify_filings.py"}

    df = pd.read_csv(EDGAR_STANCE_CSV)
    if df.empty:
        return {"available": False, "detail": "edgar_stance.csv is empty."}

    # Per-company stance counts + dominant label, in the market-basket ticker
    # order so a company keeps its row position across the dashboard.
    summary = []
    order = {t: i for i, t in enumerate(TICKER_ORDER)}
    for ticker, grp in df.groupby("ticker", sort=False):
        counts = grp["stance"].value_counts()
        row = {
            "ticker": ticker,
            "name": grp["name"].iloc[0],
            "category": grp["category"].iloc[0],
            "total": int(len(grp)),
            "dominant": grp["stance"].mode().iloc[0],
        }
        for s in STANCE_ORDER:
            row[s] = int(counts.get(s, 0))
        summary.append(row)
    summary.sort(key=lambda r: order.get(r["ticker"], len(order)))

    passage_cols = ["ticker", "name", "category", "fiscal_year", "form",
                    "stance", "subject", "quote", "rationale", "passage"]
    passages = df[[c for c in passage_cols if c in df.columns]]

    return {
        "available": True,
        "stance_order": STANCE_ORDER,
        "summary": summary,
        "passages": _records(passages),
    }


# --------------------------------------------------------------------------- #
# robustness / generalization checks tab -- market-wide EDGAR check + sector
# ETF check, mirroring collect_edgar_marketwide.py / collect_market_marketwide.py
# --------------------------------------------------------------------------- #

@app.get("/api/robustness-checks")
def robustness_checks():
    if not REAL_DATA_AVAILABLE:
        raise HTTPException(status_code=404, detail="Real collector output not found.")

    _require_file(MARKET_MARKETWIDE_CSV)
    _require_file(MARKET_CSV)
    etf = pd.read_csv(MARKET_MARKETWIDE_CSV, parse_dates=["Date"])
    prices = pd.read_csv(MARKET_CSV, parse_dates=["Date"])

    etf_monthly = (
        etf.groupby("ticker", sort=False)
        .apply(lambda g: g.set_index("Date")[["indexed"]].resample("ME").last())
        .reset_index()
    )
    etf_meta = etf[["ticker", "name"]].drop_duplicates("ticker").set_index("ticker")
    etf_monthly["name"] = etf_monthly["ticker"].map(etf_meta["name"])
    etf_monthly["Date"] = etf_monthly["Date"].dt.strftime("%Y-%m-%d")

    sample_ratio = relative_strength(prices, FINTECH_TICKERS, LEGACY_TICKERS)
    etf_ratio = relative_strength(etf, ["FINX"], ["KBWB"])

    # Macro-confound control: fintech basket vs. growth benchmarks (QQQ/ARKK),
    # to separate "fintech specifically lost" from "all growth stocks fell in
    # 2022". Combined into one frame so relative_strength() can pivot fintech
    # tickers (from prices.csv) against a benchmark (from market_marketwide.csv).
    combined = pd.concat([prices[["Date", "ticker", "close"]],
                          etf[["Date", "ticker", "close"]]], ignore_index=True)
    macro_control = {}
    for bench in ("QQQ", "ARKK"):
        if bench in etf["ticker"].values:
            rs = relative_strength(combined, FINTECH_TICKERS, [bench])
            if rs is not None:
                macro_control[bench] = _series_to_records(rs, "date", "value")

    _require_file(EDGAR_MARKETWIDE_CSV)
    marketwide = pd.read_csv(EDGAR_MARKETWIDE_CSV)
    mw_agentic = marketwide[marketwide["query"] == "agentic"][["year", "total_filings"]].sort_values("year")

    _require_file(EDGAR_CSV)
    edgar = pd.read_csv(EDGAR_CSV)
    sample_agentic = (
        edgar[edgar["query"] == "agentic"]
        .groupby("year", as_index=False)["mentions"].sum()
        .sort_values("year")
    )

    return {
        "market_marketwide": {
            "etf_indexed": _records(etf_monthly.rename(columns={"Date": "date", "indexed": "value"})),
            "sample_ratio": _series_to_records(sample_ratio, "date", "value"),
            "etf_ratio": _series_to_records(etf_ratio, "date", "value"),
        },
        "macro_control": {
            "sample_ratio_vs_legacy": _series_to_records(sample_ratio, "date", "value"),
            "vs_benchmark": macro_control,
        },
        "edgar_marketwide": {
            "marketwide_agentic": _records(mw_agentic),
            "sample_agentic": _records(sample_agentic),
        },
    }


# --------------------------------------------------------------------------- #
# converging-evidence tab -- the synthesis view. Every independent raw signal,
# z-scored onto one comparable scale, so a non-technical reader can *see* that
# the Wave 1 signals all peak and roll over together (~2021) while the Wave 2
# signals all inflect up together (~2024). The persuasion isn't one statistic;
# it's five unrelated datasets agreeing on the same two dates.
# --------------------------------------------------------------------------- #

# key -> (human label, which wave, what a peak MEANS here)
CONVERGENCE_SIGNALS = [
    ("market_rel_strength", "Fintech vs. bank stock strength", "wave1"),
    ("wave1_trend", "Wave 1 search interest", "wave1"),
    ("wave1_profitability", "Fintech profitability gap", "wave1"),
    ("wave2_trend", "Wave 2 (AI finance) search interest", "wave2"),
    ("edgar_ai_intensity", "AI language in SEC filings", "wave2"),
]


@app.get("/api/convergence")
def convergence(synthetic: bool = Query(False)):
    forced_synthetic = synthetic or not REAL_DATA_AVAILABLE
    try:
        res = build_indices(use_synthetic=forced_synthetic)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    df = res.df
    out_df = pd.DataFrame(index=df.index)
    signals = []
    for key, label, wave in CONVERGENCE_SIGNALS:
        if key not in df.columns:
            continue
        # Smooth (6-month centred mean) before comparing/plotting: this is a
        # big-picture synthesis view, so a single noisy month shouldn't set a
        # signal's "peak" (raw argmax put Wave 1 search interest's peak on a 2026
        # spike, off-message and misleading). The smoothed trend is what the eye
        # reads off the overlay chart anyway.
        z = zscore(df[key]).rolling(6, center=True, min_periods=2).mean()
        out_df[key] = z
        peak_date = z.idxmax()
        trough_date = z.idxmin()
        signals.append({
            "key": key, "label": label, "wave": wave,
            "peak_date": peak_date.strftime("%Y-%m-%d") if pd.notna(peak_date) else None,
            "trough_date": trough_date.strftime("%Y-%m-%d") if pd.notna(trough_date) else None,
        })

    records = out_df.reset_index().rename(columns={out_df.index.name or "index": "date"})
    records["date"] = pd.to_datetime(records["date"]).dt.strftime("%Y-%m-%d")
    return {
        "used_synthetic": res.used_synthetic,
        "forced_synthetic": forced_synthetic and not synthetic,
        "signals": signals,
        "records": _records(records),
    }


# --------------------------------------------------------------------------- #
# written verdict tab -- read fresh off disk every call, same as
# ai_assistant.py's _read_project_doc(), so an edit to either file shows up
# without restarting the server
# --------------------------------------------------------------------------- #

@app.get("/api/verdict")
def verdict():
    return {
        "verdict_md": ai_assistant._read_project_doc("VERDICT.md"),
    }


# --------------------------------------------------------------------------- #
# AI research assistant (Gemini) -- grounded in the exact df/breaks the
# caller supplies, exactly like app.py's slider-driven recompute
# --------------------------------------------------------------------------- #

class AIContextParams(BaseModel):
    w1_weight: float = W1_WEIGHT
    pelt_penalty: float = PELT_PENALTY
    momentum_window: int = MOMENTUM_WINDOW
    synthetic: bool = False
    api_key: str | None = None


class AIChatRequest(AIContextParams):
    question: str
    history: list[dict] = []


def _build_context(p: AIContextParams) -> tuple[str, bool]:
    """Returns (grounding context, used_synthetic). used_synthetic is surfaced
    so the chat tool loop recomputes on the same real-vs-synthetic data the
    context describes."""
    forced_synthetic = p.synthetic or not REAL_DATA_AVAILABLE
    res = build_indices(weight_w1=p.w1_weight, use_synthetic=forced_synthetic)
    breaks = run_break_analysis(res, momentum_window=p.momentum_window, pelt_penalty=p.pelt_penalty)
    context = ai_assistant.build_data_context(
        res.df, breaks, p.w1_weight, p.pelt_penalty, p.momentum_window, res.used_synthetic
    )
    return context, res.used_synthetic


# Streamed responses use Server-Sent Events so the browser can render tokens as
# they arrive. Pre-flight work (API key, context build) happens before the
# StreamingResponse so those failures return a normal HTTP error; anything that
# goes wrong once streaming has started is delivered as an SSE "error" event
# (see ai_assistant's stream_* generators).
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(events) -> str:
    for event, data in events:
        yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
    yield "event: done\ndata: {}\n\n"


@app.post("/api/ai/summary")
def ai_summary(p: AIContextParams):
    api_key = _resolve_api_key(p.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="No Gemini API key configured.")
    context, _ = _build_context(p)
    return StreamingResponse(
        _sse(ai_assistant.stream_summary(context, api_key)),
        media_type="text/event-stream", headers=_SSE_HEADERS,
    )


@app.post("/api/ai/chat")
def ai_chat(req: AIChatRequest):
    api_key = _resolve_api_key(req.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="No Gemini API key configured.")
    context, used_synthetic = _build_context(req)
    return StreamingResponse(
        _sse(ai_assistant.stream_chat(
            req.question, context, api_key,
            history=req.history, use_synthetic=used_synthetic,
        )),
        media_type="text/event-stream", headers=_SSE_HEADERS,
    )


# --------------------------------------------------------------------------- #
# Robustness agent -- the tool-using agent from robustness_agent.py, exposed so
# the Robustness tab can run it live and show its check-by-check trace + final
# verdict. Unlike the stability score (a deterministic grid sweep), this is the
# qualitative, exploratory version: the model chooses which parameter settings
# to check. Synchronous (the run is a handful of LLM calls); the frontend shows
# a spinner. Capped at a few steps so one run can't drain the free-tier quota.
# --------------------------------------------------------------------------- #

class RobustnessAgentRequest(BaseModel):
    synthetic: bool = False
    max_steps: int = robustness_agent.MAX_STEPS_DEFAULT
    api_key: str | None = None


@app.post("/api/robustness-agent")
def run_robustness_agent(req: RobustnessAgentRequest):
    api_key = _resolve_api_key(req.api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail="No Gemini API key configured.")
    # Force synthetic when real data is missing, exactly like _build_context, so
    # the agent checks the same data the rest of the dashboard is showing.
    use_synthetic = req.synthetic or not REAL_DATA_AVAILABLE
    # Bound max_steps to the agent's own default so a hand-crafted request can't
    # ask for an unbounded (quota-draining) run.
    max_steps = max(1, min(int(req.max_steps), robustness_agent.MAX_STEPS_DEFAULT))
    try:
        result = robustness_agent.run_agent(api_key, use_synthetic=use_synthetic, max_steps=max_steps)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "used_synthetic": result.used_synthetic,
        "steps_used": result.steps_used,
        "max_steps": result.max_steps,
        "trace": result.trace,
        "verdict": result.verdict,
    }

