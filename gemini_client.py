"""
gemini_client.py
================
One place for the low-level Gemini (google-genai) plumbing shared by the two
LLM features in this project -- the research assistant (ai_assistant.py) and
the robustness/red-team agent (robustness_agent.py). Before this module those
two files each carried their own copy of the client factory, the 429 backoff,
and the free-tier daily-vs-per-minute quota logic, kept "in sync manually";
that comment is now obsolete because both import from here.

What lives here:
    GEMINI_MODEL                     -- the single model id both features use
    get_client(api_key)              -- client factory (with a request timeout)
    generate_with_retry(...)         -- one blocking call, with 429 backoff
    generate_stream_with_retry(...)  -- same, but yields streamed text chunks

Why a request timeout: the assistant's calls are user-facing and synchronous;
without a ceiling a wedged connection would hang the browser's fetch forever.

Needs:
    pip install google-genai
    a Gemini API key from https://ai.google.dev (AI Studio "Get API key" flow --
    a genuinely free product; a Google Cloud Console / Vertex AI key is a
    different, billing-gated product -- see ai_assistant.py's header note).
"""

from __future__ import annotations

import time

# gemini-3.6-flash: Google's current general-purpose flash model. Google
# doesn't publish exact free-tier RPM/TPM numbers publicly -- only the AI
# Studio dashboard shows them once a key exists -- so if this model 429s
# persistently or is deprecated, check https://aistudio.google.com/rate-limit
# and swap here (one edit now updates both LLM features). Avoid models that do
# their own server-side tool use (web search, code execution): both features
# depend on answers staying grounded in the context/tools we supply, not the
# open web.
GEMINI_MODEL = "gemini-3.6-flash"

# Per-request wall-clock ceiling (milliseconds), passed to the SDK's HTTP layer
# so a stuck call fails loudly instead of hanging a user-facing fetch forever.
REQUEST_TIMEOUT_MS = 90_000


def get_client(api_key: str):
    """Builds a google-genai client, or raises a clear install hint if the
    package is missing (it's an optional-feeling dependency -- everything
    except the LLM features works without it)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from e
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def _retry_delay_seconds(exc, default: float = 15.0) -> float:
    """Reads the server's own suggested RetryInfo.retryDelay off a 429 response
    rather than guessing a backoff -- Gemini's free tier caps the model on a
    short per-minute window on top of the per-day one _is_daily_quota_exhausted()
    checks for, and the agent's tool loop (or a burst of chat turns) can easily
    exceed that per-minute cap."""
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
    """A per-minute rate limit is worth sleeping through; a per-DAY quota is
    not -- retryDelay on that error isn't a meaningful countdown to reset, so
    sleeping and retrying just burns wall-clock time for a wall that won't come
    down for hours. Detected via the QuotaFailure violation's quotaId, which
    names the exhausted bucket (e.g.
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


def _daily_quota_error(model: str, exc) -> RuntimeError:
    return RuntimeError(
        f"Gemini's free-tier daily request quota for {model} is exhausted for "
        "today (shared across the summary, chat, and robustness agent). "
        "Retrying won't help until it resets -- see "
        "https://ai.google.dev/gemini-api/docs/rate-limits."
    )


def generate_with_retry(client, *, model: str, contents, config, max_retries: int = 5):
    """One blocking generate_content call, retrying only on a per-minute 429
    (sleeping for the server-suggested delay). A per-day quota or any non-429
    error is raised immediately -- retrying those just wastes time."""
    from google.genai import errors
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.ClientError as e:
            if getattr(e, "code", None) != 429:
                raise
            if _is_daily_quota_exhausted(e):
                raise _daily_quota_error(model, e) from e
            if attempt == max_retries:
                raise
            time.sleep(_retry_delay_seconds(e) + 1.0)


def generate_stream_with_retry(client, *, model: str, contents, config, max_retries: int = 5):
    """Streaming counterpart of generate_with_retry: yields response chunks as
    the model produces them. Retry is only attempted before the first chunk has
    been yielded -- once tokens have reached the caller, a mid-stream failure
    can't be retried without duplicating already-emitted text, so it's raised."""
    from google.genai import errors
    for attempt in range(max_retries + 1):
        yielded = False
        try:
            stream = client.models.generate_content_stream(
                model=model, contents=contents, config=config,
            )
            for chunk in stream:
                yielded = True
                yield chunk
            return
        except errors.ClientError as e:
            if yielded or getattr(e, "code", None) != 429:
                raise
            if _is_daily_quota_exhausted(e):
                raise _daily_quota_error(model, e) from e
            if attempt == max_retries:
                raise
            time.sleep(_retry_delay_seconds(e) + 1.0)
