"""
ai_assistant.py
================
Groq-powered research assistant for the Fintech Two-Wave Disruption Index.

Every answer is grounded in the *live* computed numbers -- whatever
build_index.py's build_indices() / run_break_analysis() currently produced,
which inside app.py reflects whatever the sidebar sliders are set to right
now -- plus a condensed version of VERDICT.md's own stated limitations. The
model is instructed to only cite numbers present in that context and to
preserve the project's own epistemic distinctions (Wave 1 = measured,
Wave 2 = early/thin evidence, "banks win the AI wave" = a labeled prediction,
not a finding). This is what stops it from inventing statistics or
overclaiming beyond what the pipeline actually found.

Two entry points, both STATELESS -- every call rebuilds the data context
fresh rather than relying on a server-side chat session, so an answer always
reflects whatever the sliders are set to *right now*, even if they changed
since the last question:

    build_data_context(df, breaks, w1_weight, pelt_penalty,
                        momentum_window, used_synthetic) -> str
    generate_summary(context, api_key)                  -> str
    answer_question(question, context, api_key, history) -> str

Needs:
    pip install groq
    a Groq API key -- free, no billing card required -- at
    https://console.groq.com/keys

Originally built against Gemini; switched to Groq because the Google Cloud
project behind the available Gemini key(s) required a funded billing account
before unlocking any quota, even nominally "free tier" (confirmed across two
separate keys/projects, both returning limit: 0). Groq's free tier works
without a card. build_data_context() and the prompt-building logic are
unchanged -- only _get_client()/_generate() below are provider-specific.
"""

from __future__ import annotations

import os

import pandas as pd

from build_index import FINTECH_TICKERS, LEGACY_TICKERS, WAVE1_TREND_TERMS, WAVE2_TREND_TERMS

HERE = os.path.dirname(os.path.abspath(__file__))

# llama-3.3-70b-versatile has this key's highest free-tier rate limit of the
# models tried (12000 tokens/min on-demand, vs. 8000 for openai/gpt-oss-120b
# and openai/gpt-oss-20b, 6000 for llama-3.1-8b-instant -- checked directly
# against /v1/chat/completions' x-ratelimit-limit-tokens response header,
# since Groq doesn't publish per-key limits anywhere else). That budget, not
# raw model quality, is the binding constraint on how much CONTEXT below can
# afford to include -- see build_data_context()'s comment on why README.md
# isn't inlined. Swap models in your Groq console
# (https://console.groq.com/docs/models) if your quota differs, but re-check
# the rate-limit headers before assuming a "smarter" model actually fits.
# Avoid groq/compound or other tool-using models here, since their web
# search / code execution would let answers drift from CONTEXT, which is the
# whole point of rule 1 below.
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_INSTRUCTIONS = """\
You are a research assistant embedded in a Streamlit app for a thesis titled
"Fintech Two-Wave Disruption Index." The thesis asks whether fintech
disruption of traditional banking (Wave 1: payments, neobanks, embedded
finance, ~2010-2021) has already run its course, and whether a second,
AI-native wave (Wave 2: AI-native underwriting/advisory, ~2024-) is only now
beginning.

Every message you receive will include a CONTEXT block with several parts:
current parameter settings; live-computed sub-index values, peaks, and
detected structural breaks with Chow test F-statistics and p-values; the
underlying raw component signals (price, search, filings, profitability) and
what companies/keywords each one is built from; a recent-months table of
every series; and the full, current text of this project's VERDICT.md (the
written verdict). Follow these rules strictly:

1. Only cite numbers, dates, findings, or methodology details that literally
   appear in CONTEXT. Never invent a statistic, company name, date, or
   mechanism that isn't there.
2. If CONTEXT says synthetic/demo data is active, say so explicitly and
   plainly in your answer, and make clear that mode is fabricated placeholder
   data used to demo the pipeline, not evidence for or against the thesis.
3. Keep two things distinct, since CONTEXT now contains both:
   - LIVE numbers (sub-index values, breaks, Chow stats) reflect whatever the
     sliders are set to *right now*, which may differ from VERDICT.md's
     numbers -- VERDICT.md was written at the default 50/50 weight and is a
     static snapshot, not auto-updating. If they disagree, say so rather than
     quietly picking one.
   - VERDICT.md's own predictions (e.g. "banks likely absorb the AI wave")
     are explicitly labeled predictions in that document, not findings --
     never present them with the same confidence as what the live numbers or
     VERDICT.md's evidence sections show already happened.
4. Preserve this project's own epistemic distinctions -- do not flatten them:
   Wave 1 conclusions are backed by real market/profitability data and can be
   stated with real confidence; Wave 2 conclusions rest on thin, early
   evidence and should be described as suggestive, not proven.
5. Be concise and specific. Cite exact numbers (F-statistics, p-values,
   dates, z-scores, company tickers) when relevant -- specific figures are
   what make an answer useful in a live presentation setting.
6. If the question asks something CONTEXT genuinely can't answer, say so
   plainly rather than guessing or reasoning beyond the provided data.
"""


def _fmt(x, decimals=3):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a"
    return f"{x:.{decimals}f}"


def _series_break_lines(breaks: dict, series_key: str, label: str) -> str:
    info = breaks["series"][series_key]
    if not info["break_dates"]:
        return f"  {label}: no statistically confirmed breaks at current settings."
    lines = [f"  {label}: {info['n_breaks']} break(s) detected"]
    for ct in info["chow_tests"]:
        if "F_stat" in ct:
            sig = "significant at 5%" if ct["significant_5pct"] else "NOT significant at 5%"
            lines.append(
                f"    - {ct['break_date']}: Chow F={_fmt(ct['F_stat'])}, "
                f"p={_fmt(ct['p_value'], 5)} ({sig})"
            )
        else:
            lines.append(f"    - {ct.get('break_date')}: {ct.get('note', 'could not test')}")
    return "\n".join(lines)


def _read_project_doc(filename: str) -> str:
    """Reads a project doc fresh off disk on every call, rather than keeping
    a hand-copied summary in this file -- so the assistant can never cite a
    stale version of README.md/VERDICT.md after either one is edited. Falls
    back to a short note instead of crashing the app if the file is missing
    (e.g. a stripped-down deployment) -- that's a degraded-context problem,
    not a fabricated-evidence one, so it doesn't need build_index.py's
    fail-loudly treatment of missing collector output."""
    path = os.path.join(HERE, filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"[{filename} not found at {path} -- not available this session]"


# Raw input columns in IndexResult.df, one row per sub-index component, with
# what each is actually built from (from build_index.py's CONFIG) -- lets the
# assistant answer "what does wave1_trend track?" instead of only reciting
# the combined z-score.
_COMPONENTS = [
    ("market_rel_strength", "Wave 1", "Market relative strength (fintech basket / legacy basket price ratio)",
     f"fintech: {', '.join(FINTECH_TICKERS)} vs. legacy: {', '.join(LEGACY_TICKERS)}"),
    ("wave1_trend", "Wave 1", "Wave 1 search interest (Google Trends)",
     f"terms: {', '.join(WAVE1_TREND_TERMS)}"),
    ("wave1_profitability", "Wave 1", "Relative profitability growth (net income, fintech vs. legacy)",
     "symmetric YoY growth, fintech basket minus legacy basket, ~3 usable annual points (fiscal 2023-2025)"),
    ("wave2_trend", "Wave 2", "Wave 2 search interest (Google Trends)",
     f"terms: {', '.join(WAVE2_TREND_TERMS)}"),
    ("edgar_ai_intensity", "Wave 2", "EDGAR AI-language intensity (SEC filings)",
     "\"artificial intelligence\" (ai_broad query) mention count, summed across the 7-company sample"),
]


def _component_signal_lines(df: pd.DataFrame) -> str:
    lines = []
    for col, wave, label, composition in _COMPONENTS:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        latest_val, latest_date = s.iloc[-1], s.index[-1]
        peak_val, peak_date = s.max(), s.idxmax()
        trough_val, trough_date = s.min(), s.idxmin()
        lines.append(
            f"  [{wave}] {label} ({col})\n"
            f"    composition: {composition}\n"
            f"    latest ({latest_date.date()}): {_fmt(latest_val)} | "
            f"peak: {_fmt(peak_val)} on {peak_date.date()} | "
            f"trough: {_fmt(trough_val)} on {trough_date.date()}"
        )
    return "\n".join(lines)


def _recent_months_table(df: pd.DataFrame, n: int = 12) -> str:
    """Compact month-by-month table of every series' last n rows, so the
    assistant can answer questions about a specific recent month rather than
    only the single latest value and the all-time peak."""
    cols = [c for c in ("market_rel_strength", "wave1_trend", "wave1_profitability",
                        "wave2_trend", "edgar_ai_intensity", "wave1", "wave2", "FDI")
           if c in df.columns]
    recent = df[cols].tail(n)
    header = "Date       | " + " | ".join(f"{c:>14s}" for c in cols)
    rows = [header, "-" * len(header)]
    for date, row in recent.iterrows():
        vals = " | ".join(f"{_fmt(row[c]):>14s}" for c in cols)
        rows.append(f"{date.date()} | {vals}")
    return "\n".join(rows)


def build_data_context(df: pd.DataFrame, breaks: dict, w1_weight: float,
                        pelt_penalty: float, momentum_window: int,
                        used_synthetic: bool) -> str:
    """Assembles the grounding context block from the live-computed
    IndexResult.df and run_break_analysis() output -- the same objects
    app.py already recomputes on every slider change -- plus VERDICT.md read
    fresh off disk, so the assistant can answer written-verdict questions,
    not just live-number lookups. README.md is deliberately NOT inlined here
    despite being read fresh the same way VERDICT.md is: the two together
    would run close to or over this key's 12000 TPM Groq rate limit (see
    GROQ_MODEL's comment) once system instructions, chat history, and the
    question itself are added on top. The methodology facts README.md would
    have added (tickers, keywords, sub-index formulas) are already covered
    compactly by _component_signal_lines() below instead."""
    start, end = df.index.min(), df.index.max()
    latest = df.iloc[-1]
    peak_w1_date = df["wave1"].idxmax()
    peak_w2_date = df["wave2"].idxmax()

    parts = []
    if used_synthetic:
        parts.append(
            "*** SYNTHETIC DEMO DATA ACTIVE *** -- everything below is fabricated "
            "placeholder data (two-wave shape baked in by construction), NOT real "
            "evidence. Any answer must say this explicitly.\n"
        )

    parts.append(f"""\
CURRENT PARAMETERS
  Wave 1 weight in composite FDI: {w1_weight:.2f} (Wave 2 weight: {1 - w1_weight:.2f})
  PELT break-detection penalty: {pelt_penalty}
  Momentum window: {momentum_window} months
  Data range: {start.date()} to {end.date()}

LATEST VALUES ({end.date()})
  Wave 1 sub-index (z-score): {_fmt(latest['wave1'])}
  Wave 2 sub-index (z-score): {_fmt(latest['wave2'])}
  Composite FDI: {_fmt(latest['FDI'])}

PEAKS
  Wave 1 sub-index peaked {_fmt(df['wave1'].max())} on {peak_w1_date.date()}
  Wave 2 sub-index peaked {_fmt(df['wave2'].max())} on {peak_w2_date.date()}

DETECTED STRUCTURAL BREAKS (PELT candidate + Chow test confirmation)
{_series_break_lines(breaks, 'wave1', 'Wave 1 sub-index')}
{_series_break_lines(breaks, 'wave2', 'Wave 2 sub-index')}
{_series_break_lines(breaks, 'FDI', 'Composite FDI')}

UNDERLYING COMPONENT SIGNALS (what each sub-index is actually built from)
{_component_signal_lines(df)}

RECENT MONTHLY VALUES (last 12 months, z-scored except where noted otherwise above)
{_recent_months_table(df)}

--- WRITTEN VERDICT (VERDICT.md, live off disk, current as of this session) ---
STATIC -- written at the default 50/50 weight; may disagree with CURRENT
PARAMETERS/LATEST VALUES above if sliders moved. Its own labeled predictions
(e.g. "banks likely absorb the AI wave") are predictions, not findings.

{_read_project_doc("VERDICT.md")}""")

    return "\n".join(parts)


def _get_client(api_key: str):
    try:
        from groq import Groq
    except ImportError as e:
        raise RuntimeError(
            "groq is not installed. Run: pip install groq"
        ) from e
    return Groq(api_key=api_key)


def _generate(prompt: str, api_key: str) -> str:
    client = _get_client(api_key)
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(str(e)) from e


def generate_summary(context: str, api_key: str) -> str:
    """One executive-summary paragraph reflecting the CURRENT parameter
    settings -- not a reuse of VERDICT.md's static text, which was written
    at the default 50/50 weight."""
    prompt = f"""CONTEXT:
{context}

Write a 150-220 word executive-summary paragraph interpreting the CONTEXT
above, in the voice of a research memo. Reflect the CURRENT parameter
settings honestly -- if breaks are weak, absent, or different from what a
default 50/50 weighting would show, say so rather than reproducing a
generic verdict. Do not pad with disclaimers beyond what's needed; state the
finding, then the one or two caveats that materially affect it."""
    return _generate(prompt, api_key)


def answer_question(question: str, context: str, api_key: str,
                    history: list[dict] | None = None) -> str:
    """Stateless Q&A: rebuilds the full prompt (system instructions + fresh
    context + prior turns + new question) on every call, rather than using a
    persistent chat session -- so an answer always reflects whatever the
    sliders are set to right now, even if they changed since the last
    question in this conversation."""
    history_text = ""
    if history:
        recent = history[-6:]  # keep the prompt small
        turns = [f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in recent]
        history_text = "\nPRIOR CONVERSATION (for context only, may reflect " \
                       "different parameter settings than CONTEXT above):\n" + \
                       "\n".join(turns) + "\n"

    prompt = f"""CONTEXT:
{context}
{history_text}
New question: {question}

Answer:"""
    return _generate(prompt, api_key)
