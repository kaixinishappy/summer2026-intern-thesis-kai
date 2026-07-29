"""
robustness_agent.py
====================
Gemini-powered robustness/red-team agent for the Fintech Two-Wave Disruption
Index's structural-break findings.

Unlike ai_assistant.py (a single-shot, stateless "here's the live context,
answer the question" call), this is a genuine multi-step tool-using agent: it
is given one tool -- probe(w1_weight, pelt_penalty, momentum_window), a thin
wrapper around build_index.py's own build_indices()/run_break_analysis() --
and decides for itself, turn by turn, which parameter combinations to test to
see whether this project's headline structural breaks survive across the
range of defensible parameter choices, or only appear at the one setting the
paper happens to report.

This checks robustness of the *statistical method* to parameter choice. It is
not new evidence for or against the two-wave thesis, and it cannot wander
outside the same parameter bounds app.py's sliders already expose (w1_weight
0-1, pelt_penalty 0.5-10, momentum_window 3-24 months) -- see PARAM_BOUNDS
below.

Two entry points:

    run_agent(api_key, use_synthetic=False, max_steps=MAX_STEPS_DEFAULT) -> AgentResult
    main() -- CLI: python robustness_agent.py [--synthetic]

Needs the same GEMINI_API_KEY / google-genai setup as ai_assistant.py.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field

from build_index import (
    MOMENTUM_WINDOW as DEFAULT_MOMENTUM_WINDOW,
    OUT_DIR,
    PELT_PENALTY as DEFAULT_PELT_PENALTY,
    W1_WEIGHT as DEFAULT_W1_WEIGHT,
    build_indices,
    run_break_analysis,
)

# Same GEMINI_MODEL as ai_assistant.py, kept in sync manually since the two
# files pick their model independently (see ai_assistant.py's comment on
# where to check current rate limits if this needs to change).
GEMINI_MODEL = "gemini-3.6-flash"

# Mirrors app.py's sidebar slider ranges exactly, so a probe the agent runs
# is always a setting a human could actually have chosen live in the app --
# never a value nobody would defend.
PARAM_BOUNDS = {
    "w1_weight": (0.0, 1.0),
    "pelt_penalty": (0.5, 10.0),
    "momentum_window": (3, 24),
}

# Gemini's free tier caps gemini-3.6-flash at ~20 requests/DAY per project
# (GenerateRequestsPerDayPerProjectPerModel-FreeTier -- confirmed empirically
# via a 429's QuotaFailure detail; not documented with an exact number
# anywhere public), shared with ai_assistant.py's summary/chat calls in the
# same app. Kept small so one run doesn't spend most of the day's budget --
# see _generate_with_retry()'s daily-quota fast-fail below for what happens
# if it's already exhausted when this runs.
MAX_STEPS_DEFAULT = 6

SYSTEM_INSTRUCTIONS = """\
You are a robustness/red-team analyst for a thesis titled "Fintech Two-Wave
Disruption Index." The thesis detects turning points in a Wave 1
(payments/neobanks/embedded finance) sub-index, a Wave 2 (AI-native finance)
sub-index, and a composite FDI, using PELT change-point detection on
12-month momentum. Each turning point comes with a direction (slowdown /
acceleration) and a stability score. Three parameters govern this: w1_weight
(composite blend), pelt_penalty (higher = fewer, more conservative turning
points), and momentum_window (months).

Your job: determine whether the turning points the project reports are robust
(they keep showing up across a reasonable range of these three parameters) or
fragile (they only appear at one specific setting). This complements the
project's own built-in stability score -- you are the qualitative, exploratory
version of the same check.

You have one tool, `probe`, which actually recomputes the index and turning
points at whatever parameters you choose and returns the real turning-point
dates, directions, and stability scores for wave1, wave2, and FDI. Valid ranges:
  w1_weight: 0.0-1.0 (note: only affects the FDI composite, not wave1/wave2
    individually -- don't expect it to move sub-index breaks)
  pelt_penalty: 0.5-10.0
  momentum_window: 3-24 (months)

Procedure:
1. First call probe with the project's own default parameters (given in the
   task message below) to establish the baseline breaks -- treat whatever
   break dates that call returns as "the headline breaks" you are testing the
   robustness of. Do not assume specific dates in advance.
2. Then choose further probes yourself -- vary one or more parameters away
   from the defaults, in directions you think are most likely to make a
   reported break appear or disappear -- to see whether the same turning-point
   dates (roughly) and their directions survive.
3. You do not need to grid-search exhaustively. Stop once you have enough
   evidence to characterize each headline break as robust, fragile, or
   parameter-dependent (e.g. "only survives when momentum_window >= 9"), or
   when you are told your step budget is exhausted.
4. When you stop calling the tool, write a final verdict as plain text (no
   further tool calls). For each headline break: state whether it is robust,
   fragile, or parameter-dependent, and cite the specific probe results
   (parameters + turning-point dates/directions/stability) that support that
   call. Only cite numbers that
   actually came back from a probe call -- never invent or estimate a result
   you didn't get from the tool. Be concise and specific; this will be read
   by someone deciding how much to trust the thesis's headline finding.
"""

PROBE_FUNCTION_DECLARATION = {
    "name": "probe",
    "description": (
        "Recompute the Wave 1 / Wave 2 / FDI sub-indices and detect turning "
        "points (PELT change-point detection) at the given parameters. Returns "
        "the actual turning-point dates found at this exact setting, each with a "
        "direction (slowdown / acceleration) and a stability score (the share of "
        "a parameter grid that also finds it)."
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


@dataclass
class AgentResult:
    trace: list[dict] = field(default_factory=list)
    verdict: str = ""
    used_synthetic: bool = False
    steps_used: int = 0
    max_steps: int = MAX_STEPS_DEFAULT


def _clamp(name: str, value: float):
    lo, hi = PARAM_BOUNDS[name]
    return max(lo, min(hi, value))


def probe(w1_weight: float, pelt_penalty: float, momentum_window: int,
          use_synthetic: bool = False) -> dict:
    """The agent's one tool. Reuses build_index.py's own functions directly
    -- no duplicated statistics -- and clamps every argument into the same
    bounds app.py's sliders enforce, so a probe can never land outside a
    setting a human could actually have chosen."""
    w1_weight = _clamp("w1_weight", float(w1_weight))
    pelt_penalty = _clamp("pelt_penalty", float(pelt_penalty))
    momentum_window = int(_clamp("momentum_window", int(momentum_window)))

    res = build_indices(weight_w1=w1_weight, use_synthetic=use_synthetic)
    breaks = run_break_analysis(res, momentum_window=momentum_window, pelt_penalty=pelt_penalty)

    out = {
        "params": {
            "w1_weight": w1_weight,
            "pelt_penalty": pelt_penalty,
            "momentum_window": momentum_window,
        },
        "series": {},
    }
    for col in ("wave1", "wave2", "FDI"):
        info = breaks["series"][col]
        out["series"][col] = {
            "break_dates": info["break_dates"],
            "turning_points": [
                {
                    "break_date": tp.get("break_date"),
                    "direction": tp.get("direction"),
                    "stability_pct": tp.get("stability_pct"),
                }
                for tp in info["turning_points"]
            ],
        }
    return out


def _get_client(api_key: str):
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from e
    return genai.Client(api_key=api_key)


def _retry_delay_seconds(exc, default: float = 15.0) -> float:
    """Reads the server's own suggested RetryInfo.retryDelay off a 429
    response rather than guessing a backoff -- Gemini's free tier also caps
    gemini-3.6-flash on a short per-minute window on top of the per-day one
    _is_daily_quota_exhausted() below checks for (see ai_assistant.py's
    comment on checking AI Studio for current limits), and this agent's tool
    loop can easily make more calls than that per-minute cap in one run."""
    try:
        details = exc.details.get("error", {}).get("details", [])
        for d in details:
            if str(d.get("@type", "")).endswith("RetryInfo"):
                delay = str(d.get("retryDelay", ""))
                if delay.endswith("s"):
                    return float(delay[:-1])
    except Exception:
        pass
    return default


def _is_daily_quota_exhausted(exc) -> bool:
    """A per-minute rate limit is worth sleeping through (see
    _retry_delay_seconds above); a per-DAY quota is not -- retryDelay on that
    error is not a meaningful countdown to reset, so blindly sleeping and
    retrying just burns wall-clock time for a wall that won't come down for
    hours. Detected via the QuotaFailure violation's quotaId, which names the
    quota bucket that got exhausted (e.g.
    'GenerateRequestsPerDayPerProjectPerModel-FreeTier' vs. a per-minute one)."""
    try:
        details = exc.details.get("error", {}).get("details", [])
        for d in details:
            if str(d.get("@type", "")).endswith("QuotaFailure"):
                for v in d.get("violations", []):
                    if "PerDay" in str(v.get("quotaId", "")):
                        return True
    except Exception:
        pass
    return False


def _generate_with_retry(client, *, model: str, contents, config, max_retries: int = 5):
    from google.genai import errors
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.ClientError as e:
            if getattr(e, "code", None) != 429:
                raise
            if _is_daily_quota_exhausted(e):
                raise RuntimeError(
                    f"Gemini's free-tier daily request quota for {model} is "
                    "exhausted for today (shared with the AI research "
                    "assistant above). Retrying won't help until it resets -- "
                    "see https://ai.google.dev/gemini-api/docs/rate-limits."
                ) from e
            if attempt == max_retries:
                raise
            time.sleep(_retry_delay_seconds(e) + 1.0)


def run_agent(api_key: str, use_synthetic: bool = False,
              max_steps: int = MAX_STEPS_DEFAULT) -> AgentResult:
    """Drives the manual tool-calling loop: send messages -> if the model
    asked for a probe, run it and feed the result back -> repeat, until the
    model answers with plain text (its verdict) or max_steps is hit.

    Driven manually rather than via the SDK's automatic-function-calling
    helper so callers get a hard step cap (bounded demo latency/cost) and a
    clean structured trace to render in app.py -- letting a viewer see the
    loop happen is the point of this feature, not just its conclusion.
    """
    from google.genai import types

    client = _get_client(api_key)
    tool = types.Tool(function_declarations=[
        types.FunctionDeclaration(**PROBE_FUNCTION_DECLARATION)
    ])
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        tools=[tool],
    )

    task_message = f"""\
Project defaults to test robustness against:
  w1_weight = {DEFAULT_W1_WEIGHT}
  pelt_penalty = {DEFAULT_PELT_PENALTY}
  momentum_window = {DEFAULT_MOMENTUM_WINDOW}

You have a budget of at most {max_steps} probe calls. Begin.{
        ' Note: this run uses synthetic placeholder data (two-wave shape '
        'baked in by construction), so treat any breaks found as a test of '
        'the pipeline/method, not real evidence.' if use_synthetic else ''
    }"""

    contents = [types.Content(role="user", parts=[types.Part(text=task_message)])]
    trace: list[dict] = []
    verdict = ""
    steps_used = 0

    for step in range(max_steps):
        response = _generate_with_retry(
            client, model=GEMINI_MODEL, contents=contents, config=config,
        )
        candidate = response.candidates[0]
        contents.append(candidate.content)

        function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
        if not function_calls:
            verdict = (response.text or "").strip()
            break

        response_parts = []
        for fc in function_calls:
            steps_used += 1
            try:
                result = probe(use_synthetic=use_synthetic, **fc.args)
                trace.append({"params": result["params"], "result": result["series"]})
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response={"result": result})
                )
            except Exception as e:
                trace.append({"params": fc.args, "error": str(e)})
                response_parts.append(
                    types.Part.from_function_response(name=fc.name, response={"error": str(e)})
                )
            if steps_used >= max_steps:
                break
        contents.append(types.Content(role="user", parts=response_parts))
    else:
        # Loop exhausted max_steps without the model volunteering a final
        # answer -- ask it directly, no more tool calls offered.
        contents.append(types.Content(role="user", parts=[types.Part(
            text="Your probe budget is exhausted. Give your final verdict now, "
                 "as plain text, based only on the probes already run above."
        )]))
        response = _generate_with_retry(
            client, model=GEMINI_MODEL, contents=contents,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTIONS),
        )
        verdict = (response.text or "").strip()

    if not verdict:
        # Model stopped calling tools but returned no text either (e.g. hit a
        # blank turn) -- surface that plainly rather than showing an empty box.
        verdict = "[Agent stopped without producing a final verdict text.]"

    return AgentResult(trace=trace, verdict=verdict, used_synthetic=use_synthetic,
                       steps_used=steps_used, max_steps=max_steps)


def _print_trace(result: AgentResult) -> None:
    print("=" * 66)
    if result.used_synthetic:
        print("  *** SYNTHETIC PLACEHOLDER DATA -- NOT A REAL RESULT ***")
    print(f"  Robustness agent -- {result.steps_used}/{result.max_steps} probes used")
    print("-" * 66)
    for i, entry in enumerate(result.trace, 1):
        p = entry["params"]
        print(f"  Probe {i}: w1_weight={p.get('w1_weight')}, "
              f"pelt_penalty={p.get('pelt_penalty')}, "
              f"momentum_window={p.get('momentum_window')}")
        if "error" in entry:
            print(f"    error: {entry['error']}")
            continue
        for col in ("wave1", "wave2", "FDI"):
            info = entry["result"][col]
            dates = info["break_dates"] or ["none"]
            print(f"    {col:6s}: {dates}")
    print("-" * 66)
    print("  VERDICT")
    print("-" * 66)
    print(result.verdict)
    print("=" * 66)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true",
                    help="probe synthetic placeholder data instead of real collector output")
    ap.add_argument("--max-steps", type=int, default=MAX_STEPS_DEFAULT)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
            api_key = os.environ.get("GEMINI_API_KEY")
        except ImportError:
            pass
    if not api_key:
        raise SystemExit(
            "GEMINI_API_KEY not set. Put it in a .env file or export it -- "
            "see README.md's AI Research Assistant section for how to get one."
        )

    result = run_agent(api_key, use_synthetic=args.synthetic, max_steps=args.max_steps)
    _print_trace(result)

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = "_synthetic" if args.synthetic else ""
    report_path = os.path.join(OUT_DIR, f"robustness_report{suffix}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Robustness agent report{' (SYNTHETIC DEMO DATA)' if args.synthetic else ''}\n\n")
        f.write(f"{result.steps_used}/{result.max_steps} probes used.\n\n")
        f.write("## Probes\n\n")
        for i, entry in enumerate(result.trace, 1):
            f.write(f"**Probe {i}**: `{json.dumps(entry['params'])}`\n\n")
            if "error" in entry:
                f.write(f"- error: {entry['error']}\n\n")
                continue
            for col in ("wave1", "wave2", "FDI"):
                info = entry["result"][col]
                f.write(f"- {col}: breaks={info['break_dates'] or 'none'}\n")
            f.write("\n")
        f.write("## Verdict\n\n")
        f.write(result.verdict + "\n")
    print(f"  Saved: {report_path}")


if __name__ == "__main__":
    main()
