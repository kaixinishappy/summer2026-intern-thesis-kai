"""
predictions.py
==============
Turns this project's headline *forecast* into a falsifiable, self-scoring
prediction.

VERDICT.md ends with a prediction, not a finding -- "banks can absorb the AI
wave the way they absorbed the first ... an AI-native challenger may never get
the room to disrupt them at scale." As prose, nothing ever checks whether it
turns out right. This module freezes that claim as an explicit prediction with
named *confirming* and *breaking* signals, reads the current state of each
signal off the pipeline's OWN output (no new data collection --
`output/break_results.json` from build_index.py and `data/raw/edgar_stance.csv`
from classify_filings.py), decides which way the observable evidence is leaning
today, and appends one dated row to PREDICTIONS.md.

The monthly refresh workflow runs this right after build_index.py, so the
scorecard grows one row per refresh: the forecast is audited against fresh data
over time instead of sitting frozen in prose. Re-running within the same month
updates that month's row in place (idempotent) rather than duplicating it.

Deliberately kept to the Python standard library (json + csv, no pandas): it
only *reads* numbers the pipeline already computed, so it stays a light,
independently runnable step that can't fail for a dependency reason the rest of
the pipeline wouldn't have failed on first.

Entry points:
    evaluate() -> dict            # current reading of every tracked signal + lean
    update_scorecard() -> dict    # idempotent per-month upsert into PREDICTIONS.md
    read_scorecard_rows() -> list # parsed history rows (for the dashboard API)
    main()                        # CLI: python predictions.py [--print-only]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BREAK_RESULTS = os.path.join(HERE, "output", "break_results.json")
EDGAR_STANCE = os.path.join(HERE, "data", "raw", "edgar_stance.csv")
SCORECARD_PATH = os.path.join(HERE, "PREDICTIONS.md")

# When the prediction was fixed. Everything the scorecard tracks is evidence
# accumulated AFTER this date against the claim written on it.
FROZEN_DATE = "2026-08-03"

PREDICTION_TITLE = "Banks absorb the AI wave"
PREDICTION_TEXT = (
    "The AI-native second wave does not disrupt incumbent banks at scale the way "
    "Wave 1 threatened to: the banks' governance-first posture is a deliberate "
    "strategy to absorb AI on their own terms, and if it holds, an AI-native "
    "challenger never gets the room to disrupt them at scale."
)

# A Wave 2 acceleration turning point this stable (share of the parameter grid
# that also finds it, from break_results.json) counts as the second wave clearly
# gaining ATTENTION. Note this alone does not break the prediction -- the whole
# claim is that banks absorb an ignition they can see coming; it's reported as
# context, and only the posture signals below decide the lean.
IGNITION_ROBUST_PCT = 80.0

# The stance CSV's category values that are NOT the incumbent banks. Everything
# here is treated as a "fintech" filer for the deployment-split signal.
BANK_CATEGORY = "traditional_bank"

# Markers in PREDICTIONS.md between which update_scorecard() owns the rows. The
# table header/separator live ABOVE the START marker so they're never rewritten.
ROW_START = "<!-- SCORECARD:ROWS:START -->"
ROW_END = "<!-- SCORECARD:ROWS:END -->"


# --------------------------------------------------------------------------- #
# reading the pipeline's own output
# --------------------------------------------------------------------------- #

def _wave2_ignition_pct(break_results_path: str = BREAK_RESULTS) -> float | None:
    """Highest stability of any Wave 2 *acceleration* turning point in
    break_results.json -- how robustly the pipeline currently sees the second
    wave accelerating. None if the file or a Wave 2 acceleration break is
    absent (nothing detected yet is a real, reportable state, not an error)."""
    try:
        with open(break_results_path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    tps = data.get("series", {}).get("wave2", {}).get("turning_points", [])
    accel = [tp["stability_pct"] for tp in tps if tp.get("direction") == "acceleration"]
    return max(accel) if accel else None


def _stance_posture(stance_path: str = EDGAR_STANCE) -> dict | None:
    """Reads classify_filings.py's per-passage stance labels and reduces them to
    the two posture facts the prediction rests on:

      * banks_governing -- do the incumbent banks still frame agentic AI mostly
        as a *risk to govern* (stance 'risk') rather than a product they're
        scrambling to *deploy*? This is the load-bearing observable: the
        prediction's mechanism is banks absorbing AI on their own terms.
      * fintech_leads_deploying -- are the fintechs the ones actually *deploying*
        AI (to win customers), out ahead of the banks on deployment? The
        predicted split is "fintechs experiment, banks govern."

    Returns None if the stance file hasn't been produced yet (classify stage
    needs an API key), so the caller can report 'not yet classified' rather than
    inventing a posture."""
    if not os.path.exists(stance_path):
        return None
    bank_risk = bank_deploy = fin_deploy = 0
    n_rows = 0
    with open(stance_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            category = (row.get("category") or "").strip()
            stance = (row.get("stance") or "").strip().lower()
            is_bank = category == BANK_CATEGORY
            if is_bank and stance == "risk":
                bank_risk += 1
            elif is_bank and stance == "deploying":
                bank_deploy += 1
            elif not is_bank and stance == "deploying":
                fin_deploy += 1
    if n_rows == 0:
        return None
    return {
        "bank_risk": bank_risk,
        "bank_deploy": bank_deploy,
        "fintech_deploy": fin_deploy,
        # Banks are "governing" while risk-framing outweighs their own
        # deployment. Ties (0/0) count as not-governing so an empty/degenerate
        # read never silently confirms the prediction.
        "banks_governing": bank_risk > bank_deploy,
        # Fintechs "lead" while they out-deploy the banks (and actually deploy
        # at all -- 0 vs 0 is not a lead).
        "fintech_leads_deploying": fin_deploy > bank_deploy and fin_deploy > 0,
    }


# --------------------------------------------------------------------------- #
# turning the signals into a lean
# --------------------------------------------------------------------------- #

# The two observable confirming conditions. The prediction HOLDS while both are
# true (banks govern, fintechs experiment -- exactly the predicted split); it
# moves to WATCH as they erode. The genuine *breaker* -- a private, AI-native
# challenger scaling -- is outside this public-company sample's view, and the
# scorecard says so rather than pretending an observable proxy settles it.
LEAN_HOLDING = ("holding", "✅ Holding")
LEAN_WATCH = ("watch", "⚠️ Watch")
LEAN_CONTRARY = ("contrary", "❌ Contrary")
LEAN_INSUFFICIENT = ("insufficient", "· Not yet classified")

BLIND_SPOT = (
    "The genuine breaker -- a private, AI-native challenger disrupting at scale "
    "-- is invisible to this public-company sample; the scorecard tracks only "
    "the observable mechanism (bank governance posture + the deploy split)."
)


def _lean(posture: dict | None) -> tuple[str, str, str]:
    """(key, label, rationale). Requires the stance posture; ignition is context
    only, not part of the flip."""
    if posture is None:
        return (*LEAN_INSUFFICIENT,
                "edgar_stance.csv not found -- run classify_filings.py to score the posture signals.")

    confirming = int(posture["banks_governing"]) + int(posture["fintech_leads_deploying"])
    gov = ("banks still frame agentic AI mostly as a risk to govern"
           if posture["banks_governing"]
           else "banks have shifted from governing agentic AI to deploying it")
    split = ("fintechs lead on actually deploying it"
             if posture["fintech_leads_deploying"]
             else "fintechs no longer lead the banks on deployment")
    rationale = f"{gov}; {split}."

    if confirming == 2:
        return (*LEAN_HOLDING, rationale)
    if confirming == 1:
        return (*LEAN_WATCH, rationale)
    return (*LEAN_CONTRARY, rationale)


def evaluate(break_results_path: str = BREAK_RESULTS,
             stance_path: str = EDGAR_STANCE) -> dict:
    """Reads the current state of every tracked signal and returns the lean.
    Pure read -- never recomputes the index or re-collects data."""
    ignition = _wave2_ignition_pct(break_results_path)
    posture = _stance_posture(stance_path)
    lean_key, lean_label, rationale = _lean(posture)

    ignition_note = None
    if ignition is not None:
        ignition_note = "robust" if ignition >= IGNITION_ROBUST_PCT else "modest"

    return {
        "frozen_date": FROZEN_DATE,
        "title": PREDICTION_TITLE,
        "prediction": PREDICTION_TEXT,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "month": date.today().strftime("%Y-%m"),
        "lean": lean_key,
        "lean_label": lean_label,
        "rationale": rationale,
        "blind_spot": BLIND_SPOT,
        "signals": {
            "bank_posture": posture,
            "wave2_ignition_pct": ignition,
            "wave2_ignition_note": ignition_note,
        },
    }


# --------------------------------------------------------------------------- #
# rendering a scorecard row + upserting it into PREDICTIONS.md
# --------------------------------------------------------------------------- #

def _cell_bank_posture(posture: dict | None) -> str:
    if posture is None:
        return "not classified"
    verb = "governance-first" if posture["banks_governing"] else "deploying"
    return f"{verb} ({posture['bank_risk']} risk / {posture['bank_deploy']} deploy)"


def _cell_fintech_lead(posture: dict | None) -> str:
    if posture is None:
        return "not classified"
    yn = "yes" if posture["fintech_leads_deploying"] else "no"
    return f"{yn} ({posture['fintech_deploy']} vs {posture['bank_deploy']})"


def _cell_ignition(ignition: float | None, note: str | None) -> str:
    if ignition is None:
        return "none detected"
    return f"{ignition:.0f}% ({note})"


def render_row(reading: dict) -> str:
    """One markdown table row for the scorecard, keyed on the refresh month."""
    s = reading["signals"]
    return (
        f"| {reading['month']} "
        f"| {_cell_bank_posture(s['bank_posture'])} "
        f"| {_cell_fintech_lead(s['bank_posture'])} "
        f"| {_cell_ignition(s['wave2_ignition_pct'], s['wave2_ignition_note'])} "
        f"| {reading['lean_label']} |"
    )


def _row_month(row: str) -> str | None:
    """First cell of a scorecard row (the YYYY-MM key), or None if not a row."""
    parts = [c.strip() for c in row.strip().strip("|").split("|")]
    return parts[0] if parts and parts[0] else None


def read_scorecard_rows(scorecard_path: str = SCORECARD_PATH) -> list[dict]:
    """Parses the committed scorecard history (the rows between the markers) into
    a list of {month, bank_posture, fintech_lead, ignition, lean} dicts, newest
    last -- so the dashboard can show the forecast's track record over time."""
    try:
        with open(scorecard_path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    block = _extract_block(text)
    if block is None:
        return []
    cols = ["month", "bank_posture", "fintech_lead", "ignition", "lean"]
    rows = []
    for line in block.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(cols) or not cells[0]:
            continue
        rows.append(dict(zip(cols, cells)))
    return rows


def _extract_block(text: str) -> str | None:
    start = text.find(ROW_START)
    end = text.find(ROW_END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start + len(ROW_START):end]


def update_scorecard(reading: dict | None = None,
                     scorecard_path: str = SCORECARD_PATH) -> dict:
    """Upserts this refresh's row into PREDICTIONS.md's scorecard, keyed on the
    month, so a re-run in the same month replaces its row instead of appending a
    duplicate. Returns {'action': 'created'|'updated', 'row': ...}. Raises if
    PREDICTIONS.md or its row markers are missing -- that's a setup error the
    workflow should fail loudly on, not silently paper over."""
    if reading is None:
        reading = evaluate()
    row = render_row(reading)

    with open(scorecard_path, encoding="utf-8") as f:
        text = f.read()
    if ROW_START not in text or ROW_END not in text:
        raise RuntimeError(
            f"{os.path.basename(scorecard_path)} is missing the "
            f"{ROW_START} / {ROW_END} markers -- can't place the scorecard row."
        )

    block = _extract_block(text)
    existing = [ln for ln in block.splitlines() if ln.strip().startswith("|")]
    by_month = {}
    order = []
    for ln in existing:
        m = _row_month(ln)
        if m is None:
            continue
        if m not in by_month:
            order.append(m)
        by_month[m] = ln

    month = reading["month"]
    action = "updated" if month in by_month else "created"
    if month not in by_month:
        order.append(month)
    by_month[month] = row

    new_block = "\n" + "\n".join(by_month[m] for m in sorted(order)) + "\n"
    new_text = text[:text.find(ROW_START) + len(ROW_START)] + new_block + text[text.find(ROW_END):]
    with open(scorecard_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return {"action": action, "row": row}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _print_reading(reading: dict) -> None:
    print(f"Prediction (frozen {reading['frozen_date']}): {reading['title']}")
    print(f"  {reading['prediction']}")
    print()
    print(f"  As of {reading['as_of']} -- lean: {reading['lean_label']}")
    print(f"  Why: {reading['rationale']}")
    s = reading["signals"]
    print(f"  Bank posture:      {_cell_bank_posture(s['bank_posture'])}")
    print(f"  Fintech deploy lead: {_cell_fintech_lead(s['bank_posture'])}")
    print(f"  Wave 2 ignition:   {_cell_ignition(s['wave2_ignition_pct'], s['wave2_ignition_note'])}")
    print(f"  Blind spot: {reading['blind_spot']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-only", action="store_true",
                        help="Print the current reading without writing PREDICTIONS.md.")
    args = parser.parse_args()

    reading = evaluate()
    _print_reading(reading)
    if args.print_only:
        return
    result = reading and update_scorecard(reading)
    print()
    print(f"Scorecard row {result['action']} in {os.path.basename(SCORECARD_PATH)}: "
          f"{reading['month']}")


if __name__ == "__main__":
    main()
