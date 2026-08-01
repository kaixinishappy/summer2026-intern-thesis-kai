"""
classify_filings.py
===================
Part 3 refinement for the FinTech Two-Wave Disruption Index.

collect_edgar.py answers "how many filings mention agentic-AI language?" -- a
raw count. That count can't tell apart three very different things a filing
might be doing with the same words:

  * DEPLOYING  -- the company says it is already using / has shipped agentic AI
                  in its own products or operations.
  * EXPLORING  -- the company is investing in, piloting, or planning agentic AI,
                  but hasn't shipped it.
  * RISK       -- the company names agentic AI as a *threat* or uncertainty: a
                  risk factor, a competitive danger, a source of disintermediation.

The distinction is the whole of Findings Part 3. "Banks are moving first on AI"
(self + deploying/exploring) and "banks are naming AI as a threat" (risk) look
identical to a keyword tally, yet mean opposite things for the thesis. Reading
JPMorgan's 2026 10-K makes the point immediately: all three of its "agentic"
mentions sit in the risk-factors section -- disintermediation, cyber exposure,
system failure -- not a single deployment claim. The raw count scores that as
"JPM discloses agentic AI," which reads as leadership; the text says the
opposite.

This module reads the actual filing passages and classifies each one along two
axes -- stance (deploying / exploring / risk) and subject (self / competitor /
general) -- using the same Gemini setup as ai_assistant.py. It is the one thing
the deterministic pipeline structurally cannot do: a regex can count the phrase,
but only reading the sentence tells you whether the company is building it or
fearing it.

Two stages, deliberately split so a failure or quota limit in one doesn't cost
the other, and so each can be re-run alone:

  Stage A -- EXTRACT (no API key; needs efts.sec.gov + www.sec.gov)
      find_agentic_filings() -> download each filing -> extract_passages()
      Writes data/raw/edgar_passages.csv (one row per passage). Cached: the
      classify stage reads this, so you only pay the SEC download once.

  Stage B -- CLASSIFY (needs GEMINI_API_KEY; no network to SEC)
      Reads edgar_passages.csv, batches passages per company (one LLM call
      each -- Gemini's free tier is ~20 requests/day, so per-passage calls
      would blow the budget), writes data/raw/edgar_stance.csv (passages +
      their labels) and prints a per-company stance summary.

Run both:
    python classify_filings.py                # extract (if needed) then classify
Run one:
    python classify_filings.py --extract-only # Stage A only, no API key
    python classify_filings.py --classify-only # Stage B only, from cached passages

Grounding discipline mirrors ai_assistant.py: the model is told to classify
ONLY from the passage text in front of it, to quote the span it relied on, and
to return "unclear" rather than guess when the passage is ambiguous -- so a
label is always traceable to a sentence a human can re-read.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time

import pandas as pd
import requests

# Reuse collect_edgar.py's SEC config verbatim so this module queries exactly
# the same universe the count-based signal did -- same companies, same CIK
# resolution, same agentic query, same User-Agent. If those change there,
# they change here too, and the two Part-3 signals stay comparable.
from collect_edgar import (
    COMPANIES,
    HEADERS,
    RETRYABLE_STATUS,
    SEARCH_URL,
    build_ticker_to_cik_map,
)

RAW_DIR = "data/raw"
PASSAGES_CSV = os.path.join(RAW_DIR, "edgar_passages.csv")
STANCE_CSV = os.path.join(RAW_DIR, "edgar_stance.csv")

# Only the agentic phrase family -- ai_broad ("artificial intelligence") is the
# saturated baseline and isn't what Part 3 turns on. We classify where the
# Wave-2-specific language actually appears.
AGENTIC_QUERY = '"AI agent" OR "AI agents" OR "agentic AI" OR "agentic" OR "AI-powered agent"'

# Regex form of the same phrase family, for locating the matches inside the
# downloaded document. Kept in sync with AGENTIC_QUERY above by hand -- EDGAR's
# query language and Python regex don't share a syntax.
AGENTIC_PATTERN = re.compile(
    r"\b(agentic(?:\s+AI)?|AI\s+agents?|AI-powered\s+agents?)\b", re.IGNORECASE
)

START_YEAR = 2024   # agentic language is near-zero before this (see Findings
END_YEAR = 2026     # Part 2); no point downloading pre-2024 filings to classify.

# Characters of context to keep on each side of a matched phrase. A risk-factor
# vs. deployment read needs the surrounding sentence, not just the phrase --
# ~320 each side reliably captures the clause without pulling in unrelated
# neighbouring paragraphs.
CONTEXT_CHARS = 320

# Cap passages kept per filing. A filing that mentions agentic AI a dozen times
# is unusual here (JPM's 2026 10-K has three); the cap bounds both the CSV and
# the eventual prompt size against a pathological filing without losing signal.
MAX_PASSAGES_PER_FILING = 15

GEMINI_MODEL = "gemini-3.6-flash"  # matches ai_assistant.py; see its note on rate limits

STANCE_VALUES = ("deploying", "exploring", "risk", "unclear")
SUBJECT_VALUES = ("self", "competitor", "general", "unclear")

SYSTEM_INSTRUCTIONS = """\
You classify passages from public-company annual filings (10-K / 20-F) that
mention agentic-AI or AI-agent language, for a research project on whether banks
and fintechs are ADOPTING agentic AI or merely DISCLOSING IT AS A RISK.

For each passage decide two things, using ONLY the words in that passage:

STANCE -- what is the company doing with agentic AI here?
  "deploying"  : states it is already using, has launched, or currently operates
                 agentic AI / AI agents in its own products, services, or operations.
  "exploring"  : is investing in, developing, piloting, testing, or planning
                 agentic AI, but does not claim it is live yet.
  "risk"       : frames agentic AI as a threat, uncertainty, or danger -- a risk
                 factor, competitive/disintermediation threat, security/regulatory
                 concern, or something that "could" harm it. Forward-looking "could"
                 / "may adversely affect" language is risk, not deployment.
  "unclear"    : the passage names the phrase but gives too little context to tell.

SUBJECT -- who is the agentic AI attributed to?
  "self"       : the filer's own agentic AI (its products, its operations, its plans).
  "competitor" : a rival, disruptor, or new entrant's agentic AI.
  "general"    : the industry / technology at large, no specific actor.
  "unclear"    : cannot tell.

Rules:
1. Classify strictly from the passage text. Do not use outside knowledge of what
   the company actually does.
2. A risk-factor framing is "risk" EVEN IF the company clearly has the technology
   -- what matters is how THIS passage frames it.
3. Prefer "unclear" over guessing when the passage is genuinely ambiguous.
4. "quote" must be a short verbatim span (<= 25 words) copied from the passage
   that most justifies your stance label. Do not paraphrase it.
5. Return STRICT JSON only, no prose, no markdown fences.
"""


# --------------------------------------------------------------------------- #
# Stage A -- extract passages from the real filings
# --------------------------------------------------------------------------- #

def find_agentic_filings(cik: str, forms: str, start_year: int, end_year: int,
                         max_retries: int = 4, timeout: int = 30) -> list[dict]:
    """Full-text-search one company for the agentic query and return one record
    per matching filing: accession number, primary document filename, form, and
    file date. This is the same efts.sec.gov endpoint collect_edgar.py counts
    hits from -- here we keep each hit's `adsh`/`_id` so we can fetch the actual
    document next, instead of only reading `hits.total`."""
    params = {
        "q": AGENTIC_QUERY,
        "forms": forms,
        "startdt": f"{start_year}-01-01",
        "enddt": f"{end_year}-12-31",
        "ciks": cik,
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=timeout)
        except requests.exceptions.RequestException as e:
            wait = 3 * (2 ** attempt)
            print(f"    Network error ({e.__class__.__name__}) for {cik}, retry in {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code in RETRYABLE_STATUS:
            base = 15 if resp.status_code == 429 else 3
            wait = base * (2 ** attempt)
            print(f"    HTTP {resp.status_code} for {cik}, retry in {wait}s "
                  f"(attempt {attempt + 1}/{max_retries})...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        filings = []
        for h in hits:
            # _id is "<accession-with-dashes>:<primary-document-filename>".
            adsh_doc = h.get("_id", "")
            if ":" not in adsh_doc:
                continue
            adsh, filename = adsh_doc.split(":", 1)
            src = h.get("_source", {})
            file_date = (src.get("file_date") or "")
            filings.append({
                "adsh": adsh,
                "filename": filename,
                "form": src.get("form", forms),
                "file_date": file_date,
                # Fiscal year the filing covers, best-effort: EDGAR's period_ending
                # is the fiscal year-end; fall back to the file_date's year.
                "fiscal_year": (src.get("period_ending") or file_date)[:4],
            })
        return filings
    print(f"    GAVE UP on {cik} after {max_retries} retries -> no filings recorded")
    return []


def download_filing_text(cik: str, adsh: str, filename: str,
                         max_retries: int = 3, timeout: int = 60) -> str | None:
    """Download one filing's primary document and return it as cleaned plain
    text (tags stripped, entities unescaped, whitespace collapsed). Returns None
    on repeated failure rather than raising, so one unreachable document doesn't
    abort the whole extraction run."""
    # Archives path wants the CIK with leading zeros stripped and the accession
    # number with its dashes removed.
    cik_nz = str(int(cik))
    adsh_nodash = adsh.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_nz}/{adsh_nodash}/{filename}"
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.exceptions.RequestException as e:
            wait = 3 * (2 ** attempt)
            print(f"    Network error downloading {url} ({e.__class__.__name__}), "
                  f"retry in {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code in RETRYABLE_STATUS:
            wait = 3 * (2 ** attempt)
            print(f"    HTTP {resp.status_code} downloading {filename}, retry in {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", resp.text)   # strip HTML/XBRL tags
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()     # collapse whitespace
        return text
    print(f"    GAVE UP downloading {filename} -> skipping this filing")
    return None


def extract_passages(text: str, context_chars: int = CONTEXT_CHARS,
                     max_passages: int = MAX_PASSAGES_PER_FILING) -> list[str]:
    """Return the windows of `text` around each agentic-phrase match. Overlapping
    windows (two matches within one window of each other) are merged into a
    single passage so the same sentence isn't classified twice; passages are
    capped at `max_passages`."""
    spans: list[tuple[int, int]] = []
    for m in AGENTIC_PATTERN.finditer(text):
        start = max(0, m.start() - context_chars)
        end = min(len(text), m.end() + context_chars)
        if spans and start <= spans[-1][1]:
            # Overlaps the previous window -> extend it rather than add a new one.
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    passages = [text[s:e].strip() for s, e in spans[:max_passages]]
    return passages


def extract_all_passages(companies: dict, ticker_to_cik: dict) -> pd.DataFrame:
    """Stage A driver: for every company, find its agentic filings, download
    each, and extract the passages. One row per passage. Companies whose
    filings mention nothing simply contribute no rows -- that absence is itself
    Part-3 signal (e.g. neobanks with no agentic language at all)."""
    rows = []
    for ticker, info in companies.items():
        cik = ticker_to_cik.get(ticker)
        if cik is None:
            print(f"  WARNING: could not resolve CIK for {ticker}, skipping")
            continue
        print(f"Finding agentic filings for {ticker} ({info['name']})...")
        filings = find_agentic_filings(cik, info["forms"], START_YEAR, END_YEAR)
        print(f"    {len(filings)} matching filing(s)")
        for f in filings:
            time.sleep(0.3)  # stay under SEC's 10 req/sec across both endpoints
            text = download_filing_text(cik, f["adsh"], f["filename"])
            if text is None:
                continue
            passages = extract_passages(text)
            for i, passage in enumerate(passages):
                rows.append({
                    "ticker": ticker,
                    "name": info["name"],
                    "category": info["category"],
                    "fiscal_year": f["fiscal_year"],
                    "form": f["form"],
                    "file_date": f["file_date"],
                    "adsh": f["adsh"],
                    "passage_idx": i,
                    "passage": passage,
                })
            print(f"    {f['adsh']} ({f['file_date']}): {len(passages)} passage(s)")
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Stage B -- classify passages with Gemini
# --------------------------------------------------------------------------- #

def _get_client(api_key: str):
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError("google-genai is not installed. Run: pip install google-genai") from e
    return genai.Client(api_key=api_key)


def _generate(prompt: str, api_key: str) -> str:
    """Single Gemini call, same interface ai_assistant.py uses so the two stay
    in lockstep on SDK/model."""
    client = _get_client(api_key)
    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        system_instruction=SYSTEM_INSTRUCTIONS,
        input=prompt,
    )
    return interaction.output_text


def _extract_json(raw: str):
    """Parse the model's reply into JSON, tolerating a stray ```json fence or
    leading prose. Raises ValueError if nothing parseable is found, so a
    malformed reply fails loudly rather than silently dropping a company's
    passages."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to the outermost [...] or {...} block.
        for open_c, close_c in (("[", "]"), ("{", "}")):
            i, j = raw.find(open_c), raw.rfind(close_c)
            if i != -1 and j != -1 and j > i:
                try:
                    return json.loads(raw[i:j + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Could not parse JSON from model reply: {raw[:200]!r}")


def _coerce_label(value, allowed: tuple[str, ...]) -> str:
    v = str(value or "").strip().lower()
    return v if v in allowed else "unclear"


def classify_company_passages(name: str, passages: list[str], api_key: str) -> list[dict]:
    """Classify all of one company's passages in a SINGLE call (returns a JSON
    array, one object per passage, in order). Batching per company keeps the run
    inside Gemini's ~20-requests/day free tier -- one call per company, not one
    per passage."""
    numbered = "\n\n".join(f"[Passage {i}]\n{p}" for i, p in enumerate(passages))
    prompt = f"""Company filing under review: {name}

Classify each of the following {len(passages)} passages. Return a JSON array of
exactly {len(passages)} objects, in the same order, each shaped:
  {{"passage_idx": <int>, "stance": "deploying|exploring|risk|unclear",
    "subject": "self|competitor|general|unclear",
    "quote": "<verbatim span <=25 words>", "rationale": "<one short sentence>"}}

PASSAGES:
{numbered}
"""
    parsed = _extract_json(_generate(prompt, api_key))
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array for {name}, got {type(parsed).__name__}")

    # Map by passage_idx when the model supplies it; else fall back to position.
    by_idx = {}
    for pos, obj in enumerate(parsed):
        if not isinstance(obj, dict):
            continue
        idx = obj.get("passage_idx", pos)
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = pos
        by_idx[idx] = obj

    results = []
    for i in range(len(passages)):
        obj = by_idx.get(i, {})
        results.append({
            "stance": _coerce_label(obj.get("stance"), STANCE_VALUES),
            "subject": _coerce_label(obj.get("subject"), SUBJECT_VALUES),
            "quote": str(obj.get("quote", "")).strip(),
            "rationale": str(obj.get("rationale", "")).strip(),
        })
    return results


def classify_all(passages_df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    """Stage B driver: classify every passage, grouped by company so each
    company costs one API call. Returns the input frame with stance/subject/
    quote/rationale columns appended."""
    out_rows = []
    for name, grp in passages_df.groupby("name", sort=False):
        grp = grp.sort_values("passage_idx")
        passages = grp["passage"].tolist()
        print(f"Classifying {len(passages)} passage(s) for {name}...")
        labels = classify_company_passages(name, passages, api_key)
        for (_, row), label in zip(grp.iterrows(), labels):
            out_rows.append({**row.to_dict(), **label})
        time.sleep(0.5)
    return pd.DataFrame(out_rows)


def print_summary(stance_df: pd.DataFrame) -> None:
    """Per-company stance mix -- the Part-3 read the raw count can't give:
    who is deploying vs. who is only disclosing agentic AI as a risk."""
    print("\n=== Stance summary (agentic-AI passages, by company) ===")
    print("Company            | deploy | explore |  risk | unclear | dominant")
    print("-" * 72)
    for name, grp in stance_df.groupby("name", sort=False):
        counts = grp["stance"].value_counts()
        d = int(counts.get("deploying", 0))
        e = int(counts.get("exploring", 0))
        r = int(counts.get("risk", 0))
        u = int(counts.get("unclear", 0))
        dominant = grp["stance"].mode().iloc[0] if not grp.empty else "n/a"
        print(f"{name:18s} | {d:6d} | {e:7d} | {r:5d} | {u:7d} | {dominant}")
    print("\nRead: 'risk'-dominant incumbents are naming agentic AI as a THREAT,")
    print("not announcing deployment -- a distinction the raw mention count in")
    print("collect_edgar.py cannot make. See edgar_stance.csv for the quotes.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def run_extract() -> pd.DataFrame:
    os.makedirs(RAW_DIR, exist_ok=True)
    print("=== Stage A: resolving tickers to CIKs ===")
    ticker_to_cik = build_ticker_to_cik_map()
    print(f"Loaded {len(ticker_to_cik)} ticker->CIK mappings\n")
    print(f"=== Extracting agentic passages, {START_YEAR}-{END_YEAR} ===")
    df = extract_all_passages(COMPANIES, ticker_to_cik)
    df.to_csv(PASSAGES_CSV, index=False)
    print(f"\nSaved {len(df)} passage(s) to {PASSAGES_CSV}")
    return df


def run_classify(passages_df: pd.DataFrame, api_key: str) -> pd.DataFrame:
    if passages_df.empty:
        print("No passages to classify. Run extraction first (--extract-only).")
        return passages_df
    print(f"\n=== Stage B: classifying {len(passages_df)} passage(s) with {GEMINI_MODEL} ===")
    stance_df = classify_all(passages_df, api_key)
    stance_df.to_csv(STANCE_CSV, index=False)
    print(f"Saved {len(stance_df)} classified passage(s) to {STANCE_CSV}")
    print_summary(stance_df)
    return stance_df


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extract-only", action="store_true",
                        help="Stage A only: download filings + extract passages (no API key needed).")
    parser.add_argument("--classify-only", action="store_true",
                        help="Stage B only: classify cached passages from edgar_passages.csv.")
    args = parser.parse_args()

    if args.extract_only and args.classify_only:
        parser.error("--extract-only and --classify-only are mutually exclusive.")

    if args.classify_only:
        if not os.path.exists(PASSAGES_CSV):
            parser.error(f"{PASSAGES_CSV} not found -- run extraction first (--extract-only).")
        passages_df = pd.read_csv(PASSAGES_CSV)
    else:
        passages_df = run_extract()

    if args.extract_only:
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        # Load .env the same way server.py does, so a local key is found.
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
            api_key = os.environ.get("GEMINI_API_KEY")
        except ImportError:
            pass
    if not api_key:
        print("\nNo GEMINI_API_KEY set -- passages extracted but not classified.")
        print("Set it (or put it in .env) and re-run: python classify_filings.py --classify-only")
        return

    run_classify(passages_df, api_key)


if __name__ == "__main__":
    main()
