# Standing Prediction — Banks Absorb the AI Wave

**Frozen 2026-08-03.** This project's [verdict](VERDICT.md) ends with a *prediction*,
not a finding. Rather than leave it as prose nobody ever checks, it is fixed here
as a falsifiable claim with named signals, and the monthly refresh
([`.github/workflows/monthly-refresh.yml`](.github/workflows/monthly-refresh.yml))
scores it against fresh data every month — see the scorecard below.

## The claim

> **Banks absorb the AI wave.** The AI-native second wave does not disrupt
> incumbent banks at scale the way Wave 1 threatened to. The banks'
> governance-first posture — treating agentic AI as a risk to be governed rather
> than a product to rush out — is a *deliberate strategy* to absorb AI on their
> own terms. If it holds, an AI-native challenger never gets the room to disrupt
> them at scale.

## What would confirm it, what would break it

The scorecard reads two **observable** posture signals straight off the
pipeline's own output ([`data/raw/edgar_stance.csv`](data/raw/edgar_stance.csv),
[`output/break_results.json`](output/break_results.json)) — no new data
collection — and one context signal:

| Signal | Source | Confirms | Breaks |
|--------|--------|----------|--------|
| **Bank posture** | stance labels, `traditional_bank` filers | banks keep framing agentic AI mostly as *risk to govern* | banks flip to reactively *deploying* it (governing < deploying) |
| **Fintech deploy lead** | stance labels, fintech filers | fintechs are the ones *deploying* AI, out ahead of banks | banks catch/overtake fintechs on deployment |
| **Wave 2 ignition** *(context only)* | Wave 2 acceleration break stability | — | — (an ignition banks can see coming is *consistent* with the claim, so it never flips the lean by itself) |

**Lean:** `✅ Holding` while both posture signals confirm · `⚠️ Watch` when one
erodes · `❌ Contrary` when both do.

**Honest blind spot:** the genuine breaker — a *private*, AI-native challenger
disrupting at scale — is invisible to this public-company sample. The scorecard
tracks only the observable mechanism, and this line is here so that limit is
never quietly dropped.

## Scorecard

Auto-upserted by [`predictions.py`](predictions.py) on each monthly refresh (one
row per month; a re-run in the same month replaces its row). Newest at the bottom.

| Refresh | Bank posture (risk / deploy) | Fintech deploy lead | Wave 2 ignition (attention) | Lean |
|---------|------------------------------|---------------------|-----------------------------|------|
<!-- SCORECARD:ROWS:START -->
| 2026-08 | governance-first (10 risk / 0 deploy) | yes (2 vs 0) | 95% (robust) | ✅ Holding |
<!-- SCORECARD:ROWS:END -->
