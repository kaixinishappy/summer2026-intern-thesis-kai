"""
ai_assistant.py
================
Gemini-powered research assistant for the Fintech Two-Wave Disruption Index.

Every answer is grounded in the *live* computed numbers -- whatever
build_index.py's build_indices() / run_break_analysis() currently produced,
which inside app.py reflects whatever the sidebar sliders are set to right
now -- plus VERDICT.md's verdict/bottom-line text and the detailed Part
1/2/3 evidence tables, which live in README.md's Findings section. The
model is instructed to only cite numbers present in that context and to
preserve the project's own epistemic distinctions (Wave 1 = measured,
Wave 2 = early/thin evidence, "banks win the AI wave" = a labeled prediction,
not a finding). This is what stops it from inventing statistics or
overclaiming beyond what the pipeline actually found.

All entry points are STATELESS -- every call rebuilds the data context fresh
rather than relying on a server-side chat session, so an answer always reflects
whatever the sliders are set to *right now*, even if they changed since the
last question:

    build_data_context(df, breaks, w1_weight, pelt_penalty,
                        momentum_window, used_synthetic) -> str
    stream_summary(context, api_key)                     -> yields (event, data)
    stream_chat(question, context, api_key, history,     -> yields (event, data)
                use_synthetic)
    generate_summary(context, api_key)                   -> str   (non-stream)
    answer_question(question, context, api_key, history) -> str   (non-stream)

The two stream_* generators yield (event, data) tuples the server turns into
Server-Sent Events, so answers type out live in the browser instead of landing
in one blob. stream_chat additionally gives the model a `recompute` tool (the
same build_indices()/run_break_analysis() wrapper the robustness agent uses),
so it can answer what-if questions -- "what if Wave 2 were weighted 70%?" --
by actually recomputing the index at those parameters rather than being stuck
with the single snapshot the sliders happen to be at.

The low-level Gemini plumbing (client, model id, 429 backoff, timeout) lives in
gemini_client.py, shared with robustness_agent.py; only the prompts, context
assembly, and tool wiring are here.

Needs:
    pip install google-genai
    a Gemini API key -- free, no billing card required -- from
    https://ai.google.dev (the "Get API key" / AI Studio flow specifically;
    a key issued through Google Cloud Console / Vertex AI instead is a
    different product and does require billing).

Originally built against Gemini, briefly switched to Groq after an earlier
Gemini key returned quota limit: 0 without a funded Google Cloud billing
account, then switched back once it became clear that failure was specific to
Cloud Console/Vertex AI-issued keys -- an ai.google.dev AI Studio key is a
separate, genuinely free product. Groq remains a fine alternative if this key
ever hits the same wall; the context/prompt-building logic here is
provider-agnostic -- only gemini_client.py is Gemini-specific.
"""

from __future__ import annotations

import os

import pandas as pd

from build_index import FINTECH_TICKERS, LEGACY_TICKERS, WAVE1_TREND_TERMS, WAVE2_TREND_TERMS
from gemini_client import (
    GEMINI_MODEL,
    generate_stream_with_retry,
    generate_with_retry,
    get_client,
)

HERE = os.path.dirname(os.path.abspath(__file__))

# Sampling temperature for the assistant. Low but not zero: these are
# analytical/interpretive answers where we want steady, grounded phrasing, not
# creative variance -- but a hard 0 tends to make the prose stilted and
# repetitive across turns.
TEMPERATURE = 0.3

# How many recompute (what-if) tool calls one chat answer may make before the
# tool is withdrawn and the model must answer from what it has. Bounds the
# free-tier daily quota (shared with the summary and the robustness agent, see
# gemini_client.GEMINI_MODEL) and keeps one question from fanning out into a
# grid search -- that's the robustness agent's job, not the chat assistant's.
MAX_RECOMPUTE_CALLS = 4
# Hard ceiling on model<->tool round trips, so a misbehaving model that keeps
# emitting tool calls can never loop forever.
MAX_CHAT_TURNS = 8

SYSTEM_INSTRUCTIONS = """\
You are a research assistant embedded in a web dashboard (a FastAPI backend
with a plain HTML/JS frontend) for a thesis titled
"Fintech Two-Wave Disruption Index." The thesis asks whether fintech
disruption of traditional banking (Wave 1: payments, neobanks, embedded
finance, ~2010-2021) has already run its course, and whether a second,
AI-native wave (Wave 2: AI-native underwriting/advisory, ~2024-) is only now
beginning.

Every message you receive will include a CONTEXT block with several parts:
current parameter settings; live-computed sub-index values, peaks, and
detected turning points, each labelled with its direction (slowdown /
acceleration) and a stability score (the share of parameter settings that also
find that turning point -- high means robust, low means it depends on the exact
settings); the underlying raw component signals (price, search, filings,
profitability) and what companies/keywords each one is built from; a
recent-months table of every series; the full, current text of this project's
VERDICT.md (the written verdict and bottom line); and README.md's Findings
section (the detailed Part 1/2/3 evidence -- price/profitability tables,
turning-point stability, EDGAR filing counts, and the market-wide/sector-ETF
generalization checks). Follow these rules strictly:

1. Only cite numbers, dates, findings, or methodology details that literally
   appear in CONTEXT. Never invent a statistic, company name, date, or
   mechanism that isn't there.
2. If CONTEXT says synthetic/demo data is active, say so explicitly and
   plainly in your answer, and make clear that mode is fabricated placeholder
   data used to demo the pipeline, not evidence for or against the thesis.
3. Keep two things distinct, since CONTEXT now contains both:
   - LIVE numbers (sub-index values, turning points, stability scores) reflect
     whatever the sliders are set to *right now*, which may differ from the numbers in
     VERDICT.md and README.md's Findings section -- both were written at the
     default 50/50 weight and are static snapshots, not auto-updating. If
     they disagree, say so rather than quietly picking one.
   - VERDICT.md's own predictions (e.g. "banks likely absorb the AI wave")
     are explicitly labeled predictions in that document, not findings --
     never present them with the same confidence as what the live numbers or
     README.md's Findings section show already happened.
4. Preserve this project's own epistemic distinctions -- do not flatten them:
   Wave 1 conclusions are backed by real market/profitability data and can be
   stated with real confidence; Wave 2 conclusions rest on thin, early
   evidence and should be described as suggestive, not proven.
5. Be concise and specific. Cite exact numbers (turning-point dates and their
   stability scores, z-scores, company tickers) when relevant -- specific
   figures are what make an answer useful in a live presentation setting.
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
        return f"  {label}: no turning point detected at current settings."
    lines = [f"  {label}: {info['n_breaks']} turning point(s) detected"]
    for tp in info["turning_points"]:
        strength = ("robust" if tp["stability_pct"] >= 70
                    else "moderate" if tp["stability_pct"] >= 40
                    else "fragile")
        lines.append(
            f"    - {tp['break_date']}: {tp['direction']} "
            f"(stable across {tp['stability_pct']}% of parameter settings, "
            f"{tp['n_settings_matched']}/{tp['n_settings']} -- {strength})"
        )
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


def _read_findings_section() -> str:
    """Extracts just the '## Findings' section (the Part 1/2/3 evidence
    tables that used to live in VERDICT.md, moved to README.md) rather than
    inlining the whole README -- the rest of it (install steps, repo layout,
    quick-start commands) isn't relevant to grounding and would only add
    tokens for no benefit."""
    text = _read_project_doc("README.md")
    if text.startswith("["):  # missing-file placeholder from _read_project_doc
        return text
    marker = "\n## Findings"
    start = text.find(marker)
    if start == -1:
        return "[Findings section not found in README.md]"
    body = text[start + 1:]  # drop leading newline so the heading starts the string
    lines = body.split("\n")
    end_idx = next((i for i, line in enumerate(lines[1:], start=1)
                     if line.startswith("## ")), len(lines))
    return "\n".join(lines[:end_idx]).strip()


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


def _static_reference() -> str:
    """The parameter-independent half of the context: VERDICT.md and README.md's
    Findings section, read fresh off disk. Identical for every call within a
    session regardless of slider position, so build_data_context() puts it
    FIRST -- Gemini's implicit prefix caching keys on the longest shared prefix
    across requests, and keeping this large, stable block ahead of the live
    numbers (which change on every slider move and every turn) is what lets that
    caching actually hit and cut repeat cost/latency."""
    return f"""\
--- WRITTEN VERDICT (VERDICT.md, live off disk, current as of this session) ---
STATIC -- written at the default 50/50 weight; may disagree with the LIVE
NUMBERS below if the sliders moved. Its own labeled predictions (e.g. "banks
likely absorb the AI wave") are predictions, not findings.

{_read_project_doc("VERDICT.md")}

--- DETAILED FINDINGS (README.md's Findings section, live off disk, current as of this session) ---
STATIC, same default-50/50-weight snapshot as VERDICT.md above -- the price,
profitability, structural-break, and EDGAR evidence tables behind the verdict
(Parts 1-3)."""


def _live_numbers(df: pd.DataFrame, breaks: dict, w1_weight: float,
                  pelt_penalty: float, momentum_window: int,
                  used_synthetic: bool) -> str:
    """The parameter-dependent half of the context: everything computed from
    the live IndexResult.df / run_break_analysis() output at the current slider
    settings. Changes on every slider move, so it comes AFTER _static_reference()
    (see that function's note on implicit caching)."""
    start, end = df.index.min(), df.index.max()
    latest = df.iloc[-1]
    peak_w1_date = df["wave1"].idxmax()
    peak_w2_date = df["wave2"].idxmax()

    notice = ""
    if used_synthetic:
        notice = (
            "*** SYNTHETIC DEMO DATA ACTIVE *** -- everything below is fabricated "
            "placeholder data (two-wave shape baked in by construction), NOT real "
            "evidence. Any answer must say this explicitly.\n\n"
        )

    return f"""\
{notice}CURRENT PARAMETERS
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

DETECTED TURNING POINTS (PELT change-point + parameter-stability score)
{_series_break_lines(breaks, 'wave1', 'Wave 1 sub-index')}
{_series_break_lines(breaks, 'wave2', 'Wave 2 sub-index')}
{_series_break_lines(breaks, 'FDI', 'Composite FDI')}

UNDERLYING COMPONENT SIGNALS (what each sub-index is actually built from)
{_component_signal_lines(df)}

RECENT MONTHLY VALUES (last 12 months, z-scored except where noted otherwise above)
{_recent_months_table(df)}"""


def build_data_context(df: pd.DataFrame, breaks: dict, w1_weight: float,
                       pelt_penalty: float, momentum_window: int,
                       used_synthetic: bool) -> str:
    """Assembles the grounding context: the static reference material (VERDICT.md
    + README.md's Findings, read fresh off disk) followed by the live-computed
    numbers at the current slider settings. Static-first ordering is deliberate;
    see _static_reference(). Only the Findings section of README.md is extracted
    rather than the whole file -- the rest (install steps, repo layout,
    quick-start commands) isn't relevant to grounding and would only add tokens;
    see _read_findings_section(). The remaining methodology facts (tickers,
    keywords, sub-index formulas) are covered compactly by _live_numbers()'s
    component-signal lines instead."""
    return (
        "REFERENCE MATERIAL (static this session):\n"
        f"{_static_reference()}\n\n"
        "============================================================\n"
        "LIVE NUMBERS (reflect the CURRENT slider settings right now):\n\n"
        f"{_live_numbers(df, breaks, w1_weight, pelt_penalty, momentum_window, used_synthetic)}"
    )


# What-if tool for the chat assistant: the same index recompute the robustness
# agent uses, exposed so a question like "what if Wave 2 were weighted 70%?" is
# answered by actually recomputing rather than guessing. Named "recompute"
# (vs the agent's "check") only so the trace reads naturally in the chat UI; it
# dispatches to the identical function.
RECOMPUTE_FUNCTION_DECLARATION = {
    "name": "recompute",
    "description": (
        "Recompute the Wave 1 / Wave 2 / FDI sub-indices and re-detect turning "
        "points at a DIFFERENT set of parameters than the ones in LIVE NUMBERS -- "
        "use this to answer any what-if question about changing the Wave 1 "
        "weight, PELT penalty, or momentum window, instead of guessing what would "
        "change. Returns the actual turning-point dates, directions, and "
        "stability scores at those parameters; only cite numbers it returns."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "w1_weight": {
                "type": "number",
                "description": "Composite FDI blend weight for Wave 1, 0.0-1.0.",
            },
            "pelt_penalty": {
                "type": "number",
                "description": "PELT break-detection penalty, 0.5-10.0 (higher = fewer breaks).",
            },
            "momentum_window": {
                "type": "integer",
                "description": "Momentum window in months, 3-24.",
            },
        },
        "required": ["w1_weight", "pelt_penalty", "momentum_window"],
    },
}


def _summary_prompt(context: str) -> str:
    return f"""CONTEXT:
{context}

Write a 150-220 word executive-summary paragraph interpreting the CONTEXT
above, in the voice of a research memo. Reflect the CURRENT parameter
settings honestly -- if breaks are weak, absent, or different from what a
default 50/50 weighting would show, say so rather than reproducing a
generic verdict. Do not pad with disclaimers beyond what's needed; state the
finding, then the one or two caveats that materially affect it."""


def _chat_prompt(question: str, context: str, history: list[dict] | None) -> str:
    history_text = ""
    if history:
        recent = history[-6:]  # keep the prompt small
        turns = [f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                 for m in recent]
        history_text = "\nPRIOR CONVERSATION (for context only, may reflect " \
                       "different parameter settings than CONTEXT above):\n" + \
                       "\n".join(turns) + "\n"

    return f"""CONTEXT:
{context}
{history_text}
If the question asks what would happen at DIFFERENT parameters than the LIVE
NUMBERS above (a different Wave 1 weight, PELT penalty, or momentum window),
call the `recompute` tool with those parameters and base your answer on what it
returns -- do not guess. For anything answerable from CONTEXT as-is, just
answer directly.

New question: {question}

Answer:"""


def _config(with_tools: bool):
    """Builds the GenerateContentConfig, optionally with the recompute tool.
    Imported lazily so importing this module never requires google-genai (only
    actually calling the model does)."""
    from google.genai import types
    tools = None
    if with_tools:
        tools = [types.Tool(function_declarations=[
            types.FunctionDeclaration(**RECOMPUTE_FUNCTION_DECLARATION)
        ])]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=TEMPERATURE,
        tools=tools,
    )


# --------------------------------------------------------------------------- #
# Streaming entry points -- yield (event, data) tuples the server relays as
# Server-Sent Events. Events: ("token", {"text": ...}) for answer text as it
# arrives, ("tool", {...}) for a recompute call the model made, and
# ("error", {"message": ...}) if generation fails after the stream has already
# started (pre-flight errors -- no key, bad context -- are raised before the
# stream opens so the server can return a normal HTTP error instead).
# --------------------------------------------------------------------------- #

def stream_summary(context: str, api_key: str):
    """Executive summary, streamed token by token."""
    client = get_client(api_key)
    try:
        for chunk in generate_stream_with_retry(
            client, model=GEMINI_MODEL, contents=_summary_prompt(context),
            config=_config(with_tools=False),
        ):
            if getattr(chunk, "text", None):
                yield ("token", {"text": chunk.text})
    except Exception as e:
        yield ("error", {"message": str(e)})


def stream_chat(question: str, context: str, api_key: str,
                history: list[dict] | None = None, use_synthetic: bool = False):
    """Streamed Q&A with the recompute what-if tool. Runs a model<->tool loop:
    each turn is streamed, its answer text relayed as it arrives; if the model
    instead asks to recompute, the call is run and fed back and the loop
    continues. The tool is withdrawn after MAX_RECOMPUTE_CALLS so one question
    can't fan out into a grid search or drain the daily quota."""
    from google.genai import types
    from robustness_agent import check as recompute_index

    client = get_client(api_key)
    contents = [types.Content(role="user", parts=[
        types.Part(text=_chat_prompt(question, context, history))
    ])]
    recompute_calls = 0

    try:
        for _ in range(MAX_CHAT_TURNS):
            tools_left = recompute_calls < MAX_RECOMPUTE_CALLS
            acc_text = ""
            fn_parts = []
            calls = []
            for chunk in generate_stream_with_retry(
                client, model=GEMINI_MODEL, contents=contents,
                config=_config(with_tools=tools_left),
            ):
                cand = chunk.candidates[0] if chunk.candidates else None
                if not cand or not cand.content or not cand.content.parts:
                    continue
                for part in cand.content.parts:
                    if getattr(part, "function_call", None):
                        fn_parts.append(part)
                        calls.append(part.function_call)
                    elif getattr(part, "text", None):
                        acc_text += part.text
                        yield ("token", {"text": part.text})

            # Thread this model turn back into the conversation so any tool
            # responses below attach to the right call.
            model_parts = ([types.Part(text=acc_text)] if acc_text else []) + fn_parts
            if model_parts:
                contents.append(types.Content(role="model", parts=model_parts))

            if not calls:
                return  # model answered with text -- already streamed above

            response_parts = []
            for fc in calls:
                recompute_calls += 1
                try:
                    result = recompute_index(use_synthetic=use_synthetic, **fc.args)
                    yield ("tool", {"params": result["params"], "result": result["series"]})
                    response_parts.append(types.Part.from_function_response(
                        name=fc.name, response={"result": result}))
                except Exception as e:
                    yield ("tool", {"params": dict(fc.args), "error": str(e)})
                    response_parts.append(types.Part.from_function_response(
                        name=fc.name, response={"error": str(e)}))
            contents.append(types.Content(role="user", parts=response_parts))
    except Exception as e:
        yield ("error", {"message": str(e)})


# --------------------------------------------------------------------------- #
# Non-streaming entry points -- kept for the CLI / tests and any caller that
# just wants the finished string. Same prompts as the streaming versions.
# --------------------------------------------------------------------------- #

def generate_summary(context: str, api_key: str) -> str:
    """One executive-summary paragraph reflecting the CURRENT parameter
    settings -- not a reuse of VERDICT.md's static text, which was written at
    the default 50/50 weight."""
    client = get_client(api_key)
    response = generate_with_retry(
        client, model=GEMINI_MODEL, contents=_summary_prompt(context),
        config=_config(with_tools=False),
    )
    return (response.text or "").strip()


def answer_question(question: str, context: str, api_key: str,
                    history: list[dict] | None = None) -> str:
    """Non-streaming, no-tool Q&A: rebuilds the full prompt fresh on every call
    (stateless), so an answer always reflects whatever the sliders are set to
    right now. For the tool-enabled, streamed version the UI uses, see
    stream_chat()."""
    client = get_client(api_key)
    response = generate_with_retry(
        client, model=GEMINI_MODEL, contents=_chat_prompt(question, context, history),
        config=_config(with_tools=False),
    )
    return (response.text or "").strip()
