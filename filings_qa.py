"""
filings_qa.py
=============
"Ask the filings" -- a grounded question-answering feature over the actual SEC
filing passages this project already extracted
([`data/raw/edgar_passages.csv`](data/raw/edgar_passages.csv), and the
richer [`data/raw/edgar_stance.csv`](data/raw/edgar_stance.csv) when the
classify stage has run).

Unlike ai_assistant.py -- which grounds Gemini in the *computed numbers* (index
values, turning points, verdict text) -- this grounds it in *primary-source
text*: the passages from the companies' own 10-K / 20-F filings. Every answer is
built ONLY from retrieved passages and cites each claim back to a verbatim quote
with company and fiscal year, so a listener can re-check the sentence against
the filing. The model is told, in the system instruction, to answer strictly
from the supplied SOURCES and to say the filings don't cover something rather
than fill the gap from open-web knowledge.

Retrieval is deliberately simple lexical scoring (token overlap + a
company-name/ticker boost), not embeddings: the corpus is a few dozen short
passages, so a vector index would be machinery without benefit, and lexical
scoring keeps the whole feature dependency-free apart from the Gemini call
itself. If the corpus ever grows large enough to need semantic retrieval, only
retrieve() changes.

Entry point:
    answer(question, api_key, k=DEFAULT_K) -> dict
        {answer, sources: [...], cited_indices: [...], retrieved_count}

The low-level Gemini plumbing (client, model id, 429 backoff, timeout) is shared
with the rest of the project via gemini_client.py.
"""

from __future__ import annotations

import csv
import os
import re

from gemini_client import GEMINI_MODEL, generate_with_retry, get_client

HERE = os.path.dirname(os.path.abspath(__file__))
STANCE_CSV = os.path.join(HERE, "data", "raw", "edgar_stance.csv")
PASSAGES_CSV = os.path.join(HERE, "data", "raw", "edgar_passages.csv")

# How many passages to put in front of the model. The corpus is small, so this
# is less "retrieval cutoff" than "don't dump the whole corpus when a focused
# question only needs a few" -- it keeps the prompt tight and the citations
# legible.
DEFAULT_K = 6

# Interpretive but tightly grounded -- steady phrasing, no creative drift away
# from the source text.
TEMPERATURE = 0.2

# Same low-signal words ai_assistant-style prompts ignore; dropped before
# lexical scoring so a shared "the/and/of" never outweighs a real term match.
_STOPWORDS = frozenset("""
a an the and or but of to in on for with as at by from is are was were be been
being it its this that these those what which who whom how why when where do does
did done has have had will would can could should may might about into over under
""".split())

SYSTEM_INSTRUCTIONS = """\
You answer questions about how a set of financial companies discuss AI and
"agentic AI" in their own SEC filings (10-K / 20-F annual reports). You are
given a question and a numbered list of SOURCES, each a verbatim passage from a
named company's filing for a given fiscal year.

Rules, applied strictly:
1. Answer ONLY from the SOURCES provided. Never use outside or prior knowledge
   about these companies, their products, or AI in general.
2. Cite every claim with the bracketed source number(s) it comes from, like
   [1] or [2][4]. A sentence with no citation is not allowed.
3. If the SOURCES do not contain the answer, say plainly that the filings in
   scope do not cover it. Do not guess, extrapolate, or fill the gap.
4. Preserve who is speaking and about whom: a company naming agentic AI as a
   *risk / competitive threat* is saying something opposite to a company
   describing *deploying* it in its own products. Do not flatten that.
5. Be concise and specific -- name the company and fiscal year, and prefer the
   filing's own wording. This is for a live presentation, so lead with the
   direct answer, then the supporting detail.
"""


# --------------------------------------------------------------------------- #
# corpus
# --------------------------------------------------------------------------- #

def load_passages(stance_path: str = STANCE_CSV,
                  passages_path: str = PASSAGES_CSV) -> list[dict]:
    """Loads the filing passages, preferring edgar_stance.csv (it carries the
    LLM's stance label + the verbatim quote it relied on, which make richer
    citations) and falling back to edgar_passages.csv (extract-only, no API key
    needed). Returns [] if neither exists, so the caller can report 'no filings
    indexed yet' rather than crash."""
    path = stance_path if os.path.exists(stance_path) else passages_path
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            passage = (row.get("passage") or "").strip()
            if not passage:
                continue
            rows.append({
                "id": i,
                "ticker": (row.get("ticker") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "category": (row.get("category") or "").strip(),
                "fiscal_year": (row.get("fiscal_year") or "").strip(),
                "form": (row.get("form") or "").strip(),
                "passage": passage,
                # Only present in edgar_stance.csv; "" when falling back.
                "stance": (row.get("stance") or "").strip(),
                "quote": (row.get("quote") or "").strip(),
            })
    return rows


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


def retrieve(question: str, passages: list[dict], k: int = DEFAULT_K) -> list[dict]:
    """Lexical top-k: score each passage by how many distinct question terms it
    contains, with a boost when the question names the passage's company (ticker
    or a word from its name). Ties and zero-overlap questions fall back to
    corpus order, so a vague question ("what do the filings say about AI?") still
    returns a representative spread rather than nothing."""
    q_terms = set(_tokens(question))
    # Company handles the boost keys on: ticker + each name word.
    scored = []
    for p in passages:
        p_terms = set(_tokens(p["passage"]))
        overlap = len(q_terms & p_terms)
        handles = {p["ticker"].lower(), *_tokens(p["name"])}
        company_hit = 2 if (q_terms & handles) else 0
        scored.append((overlap + company_hit, p))
    # Stable sort by score desc; passages with no signal keep their file order.
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in scored[:k]]


# --------------------------------------------------------------------------- #
# prompt + answer
# --------------------------------------------------------------------------- #

def _format_sources(retrieved: list[dict]) -> str:
    blocks = []
    for n, p in enumerate(retrieved, start=1):
        header = f"[{n}] {p['name']} ({p['ticker']}) -- FY{p['fiscal_year']} {p['form']}".rstrip()
        if p["stance"]:
            header += f" -- classified stance: {p['stance']}"
        blocks.append(f"{header}\n{p['passage']}")
    return "\n\n".join(blocks)


def _prompt(question: str, retrieved: list[dict]) -> str:
    return f"""SOURCES:
{_format_sources(retrieved)}

QUESTION: {question}

Answer using only the SOURCES above, citing each claim with its [number]. If the
SOURCES do not cover the question, say so plainly.

Answer:"""


def _cited_indices(answer: str, n_sources: int) -> list[int]:
    """1-based source numbers the answer actually cited, in first-appearance
    order -- lets the UI surface the quotes the answer leaned on, not the whole
    retrieved set."""
    seen = []
    for m in re.findall(r"\[(\d+)\]", answer):
        i = int(m)
        if 1 <= i <= n_sources and i not in seen:
            seen.append(i)
    return seen


def _config():
    from google.genai import types
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=TEMPERATURE,
    )


def answer(question: str, api_key: str, k: int = DEFAULT_K) -> dict:
    """Retrieve the most relevant filing passages, then answer strictly from
    them with inline [n] citations. Returns the answer plus the sources (so the
    UI can render the verbatim passage/quote behind each citation) and which
    source numbers the answer actually cited.

    Raises ValueError if there are no passages to answer from -- a degraded-setup
    state (classify/extract stage not run) the caller should surface, not a
    fabricated answer."""
    question = (question or "").strip()
    if not question:
        raise ValueError("Empty question.")
    passages = load_passages()
    if not passages:
        raise ValueError(
            "No filing passages found -- run classify_filings.py (or its "
            "--extract-only stage) to populate data/raw/edgar_passages.csv first."
        )
    retrieved = retrieve(question, passages, k=k)

    client = get_client(api_key)
    response = generate_with_retry(
        client, model=GEMINI_MODEL, contents=_prompt(question, retrieved),
        config=_config(),
    )
    text = (response.text or "").strip()

    sources = [{
        "n": n,
        "ticker": p["ticker"],
        "name": p["name"],
        "category": p["category"],
        "fiscal_year": p["fiscal_year"],
        "form": p["form"],
        "stance": p["stance"],
        # The stance stage's short verbatim quote makes a tighter citation; fall
        # back to the fuller passage when only the extract stage has run.
        "quote": p["quote"] or p["passage"],
    } for n, p in enumerate(retrieved, start=1)]

    return {
        "answer": text,
        "sources": sources,
        "cited_indices": _cited_indices(text, len(sources)),
        "retrieved_count": len(retrieved),
        "corpus_size": len(passages),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="Question to ask the filings.")
    parser.add_argument("-k", type=int, default=DEFAULT_K, help="Passages to retrieve.")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY (see ai_assistant.py's header note).")
    result = answer(args.question, api_key, k=args.k)
    print(result["answer"])
    print()
    print(f"-- grounded in {result['retrieved_count']} of {result['corpus_size']} passages; "
          f"cited {result['cited_indices']}")
    for s in result["sources"]:
        mark = "*" if s["n"] in result["cited_indices"] else " "
        print(f" {mark}[{s['n']}] {s['name']} ({s['ticker']}) FY{s['fiscal_year']} {s['form']}")


if __name__ == "__main__":
    main()
