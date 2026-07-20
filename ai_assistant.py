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

import pandas as pd

# Free tier, fast, good quality; swap for another model in your Groq console
# (https://console.groq.com/docs/models) if this one is deprecated or your
# quota needs differ.
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_INSTRUCTIONS = """\
You are a research assistant embedded in a Streamlit app for a thesis titled
"Fintech Two-Wave Disruption Index." The thesis asks whether fintech
disruption of traditional banking (Wave 1: payments, neobanks, embedded
finance, ~2010-2021) has already run its course, and whether a second,
AI-native wave (Wave 2: AI-native underwriting/advisory, ~2024-) is only now
beginning.

Every message you receive will include a CONTEXT block containing the
live-computed numbers for the CURRENT session -- current parameter settings,
sub-index values, detected structural breaks with Chow test F-statistics and
p-values, and known limitations. Follow these rules strictly:

1. Only cite numbers, dates, and findings that literally appear in CONTEXT.
   Never invent a statistic, company name, or date that isn't there.
2. If CONTEXT says synthetic/demo data is active, say so explicitly and
   plainly in your answer, and make clear that mode is fabricated placeholder
   data used to demo the pipeline, not evidence for or against the thesis.
3. Preserve this project's own epistemic distinctions -- do not flatten them:
   - Wave 1 conclusions are backed by real market/profitability data and can
     be stated with real confidence.
   - Wave 2 conclusions rest on thin, early evidence (search interest, SEC
     filing language) and should be described as suggestive, not proven.
   - Any claim that "incumbent banks will win the AI wave" is an explicitly
     labeled PREDICTION in this project, not a finding -- never present it
     with the same confidence as the Wave 1 results.
4. Be concise and specific. Cite exact numbers (F-statistics, p-values,
   dates, z-scores) when relevant -- specific figures are what make an answer
   useful in a live presentation setting.
5. If the question asks something CONTEXT genuinely can't answer, say so
   plainly rather than guessing or reasoning beyond the provided data.
"""

# Condensed from VERDICT.md's "Limitations" section -- kept short and stable
# so it fits in every context call without re-reading the file each time.
LIMITATIONS_SUMMARY = """\
- Proxies, not ground truth: search interest measures attention, not
  adoption; filing language measures what companies say, not what they ship;
  only ~4 fiscal years of net income are available per company.
- Short Wave 2 window: the acceleration signal covers roughly 2024-2026,
  about two years -- a single flat year would meaningfully change the
  picture.
- Small, hand-picked, public-only company set: 5 companies for EDGAR filings,
  7 tickers for market prices. A market-wide EDGAR check (not in this app's
  live data) confirms the "thin until 2024-2025" shape isn't a 5-company
  artifact, but there is still no way to see a private AI-native challenger
  even if one exists and is winning right now.
- "Banks likely absorb the AI wave" is an explicit prediction in this
  project's written verdict, not a finding -- it should not be cited with the
  same confidence as what already happened in Wave 1.
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


def build_data_context(df: pd.DataFrame, breaks: dict, w1_weight: float,
                        pelt_penalty: float, momentum_window: int,
                        used_synthetic: bool) -> str:
    """Assembles the grounding context block from the live-computed
    IndexResult.df and run_break_analysis() output -- the same objects
    app.py already recomputes on every slider change."""
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

KNOWN LIMITATIONS OF THIS PROJECT
{LIMITATIONS_SUMMARY}""")

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
