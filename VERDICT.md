# Verdict: Did FinTech Lose to the Banks, or Is a Bigger AI Wave About to Hit?

**Thesis question:** Digital payment platforms, neobanks, and embedded finance
players have taken significant market share from legacy institutions. Has that
disruption (Wave 1) run its course, or is a second wave of AI-native financial
services (Wave 2) only now beginning?

## Verdict

Both framings — "fintech lost" and "AI is about to disrupt the disruptors" —
are too simple. The honest, data-backed verdict has three parts:

1. **The first wave of fintech has, in a real sense, already lost.** The
   2010-2021 generation of app-based challengers (Robinhood-style neobanks,
   PayPal, Block/Square) mostly built nicer banking apps, not a structurally
   different kind of bank. When rates rose, several of them lost money outright
   while the incumbents' profits grew. The public banks have since re-absorbed
   the price leadership these companies briefly took. This part is well
   evidenced — the companies are public, multi-year, and the data is clean.
2. **The second wave, AI-native finance, cannot actually be measured yet** —
   and that thinness is itself the finding, not a gap to paper over. The
   companies that would represent this wave are mostly private or too new to
   have meaningful stock history, so there is no honest way to price "is
   AI-native finance winning." What *can* be measured — search attention,
   regulatory disclosure language — is present, but only barely, and only
   since 2024.
3. **The most likely real outcome is a repeat, not a reversal: the banks
   probably absorb the AI wave too.** The dramatic "banks are too old and
   clunky to use AI" story is a live possibility, not a demonstrated one —
   and one relevant data point in this project (below) is at least
   consistent with the opposite: incumbents, not challengers, are the ones
   currently showing up in the AI-disclosure evidence.

The single most defensible technical result in the whole project is that
**splitting Wave 1 and Wave 2 apart reveals a story that looking at a blended
index gets wrong** — not because the blend is flat (it isn't, in the real
data), but because it silently misattributes which wave is driving it. See
**Part 4** below — this needed correcting from an earlier draft of this
verdict, and the corrected version is stronger than the original claim.

---

## Part 1: Wave 1 fintech has largely lost

**Price evidence (`charts/indexed_performance.png`, `data/raw/prices.csv`)** —
rebasing each company's stock to 100 at its start date:

| Ticker | Category | Peak (indexed) | Peak date | Value at 2026-07-02 |
|---|---|---|---|---|
| XYZ (Block) | embedded finance | **779** | 2021-08-05 | 218 |
| PYPL (PayPal) | embedded finance | 418 | 2021-07-23 | **62** (below its own 2018 start) |
| SOFI | neobank | 264 | 2025-11-12 | 150 |
| NU (Nubank) | neobank | 182 | 2026-01-28 | 132 |
| JPM | traditional bank | — | steady climb | **389** |
| BCS (Barclays) | traditional bank | — | steady climb | 335 |
| HSBC | traditional bank | — | steady climb | 299 |

The disruptors had a real, dramatic moment — Block up nearly 8x, PayPal up
over 4x — in 2020-2021. It didn't hold. PayPal is the *only* company in the
dataset to end up below its own starting price five years later. The
traditional banks, which barely participated in the 2021 boom, have been
compounding steadily since 2023-2024 and are now either the best performers
(JPM) or have fully caught back up (BCS, HSBC).

**Profitability evidence — new, and it strengthens the "struggled to make
money when rates rose" mechanism (`data/raw/fundamentals.csv`, not
previously wired into any chart in this project):**

| Ticker | 2022 net income | 2023 net income |
|---|---|---|
| SOFI | **-$320M** | -$301M |
| XYZ (Block) | **-$541M** | +$10M |
| NU (Nubank) | **-$365M** | +$1,031M |
| JPM | +$37.7B | +$49.6B |
| HSBC | +$15.6B | +$23.5B |

2022 was the fastest Fed hiking cycle in decades, and it's exactly the year
all three disruptors in this dataset post operating losses, while the two
banks' profits grew substantially. Higher rates directly pad bank net
interest margins while raising the cost of capital for often-unprofitable,
capital-intensive challengers — the timing here lines up with that mechanism.

**Now checked directly, not just asserted (`collect_rates.py`,
`data/raw/fed_funds_rate.csv`, `charts/rates_vs_netincome.png`):** the
effective Fed funds rate was pinned near zero (0.06%-0.08%) through all of
2021, then rises essentially the entire way through 2022 and into 2023,
peaking at **5.33% in August 2023** — the steepest, fastest climb in the
whole 2018-2026 series. Plotted directly against each company's net income
in three stacked panels (rate / banks / disruptors, kept on separate axes
since a $58B JPM year and a -$320M SOFI year can't share one linear scale),
the disruptors' loss years sit visibly inside the hiking window while the
banks' income climbs through the same stretch without interruption. This is
still a timing correlation, not a controlled causal test (no counterfactual
"disruptors under flat rates" exists to compare against) — but it's now a
plotted correlation against real Fed data, not a claim taken on faith.

**What this evidence can't confirm:** whether banks won by *copying features*
or *acquiring* challengers is a plausible real-world mechanism but not
something any data collected here tests — there's no product-feature or M&A
data in this project. Treat that specific mechanism as outside knowledge, not
a finding of this codebase.

**Structural break confirmation (`output/break_results.json`,
`charts/two_wave_index.png`)** — the Wave 1 sub-index shows a significant
break at **April 2021** (Chow F=9.094, p<0.001) where it rolls over from
rising to declining, and a second break at **June 2025** (F=54.151, p<0.001)
where it partially, abruptly rebounds. Momentum
(`charts/momentum_handoff.png`) is negative for most of 2021-2025 — literally
losing ground year over year during the period this project would call
Wave 1's "disruption."

## Part 2: Wave 2 (AI-native finance) is not yet measurable — and that's informative, not a gap

This project cannot price "is AI-native finance winning" the way it can
price Wave 1, because the companies that would represent that wave are
mostly private or too newly public to have real stock history. Trying to
force a market-price answer here would mean reading a signal into a handful
of thin, noisy tickers that isn't really there. The honest move — which this
verdict takes — is to say so, and to treat the thinness of every measurable
proxy as evidence that the wave is early, not evidence that it's absent.

**SEC filings — the sharpest available signal, and it's thin by design, not by
accident (`data/raw/edgar_mentions.csv`)**. Filings were searched for
`"artificial intelligence"` (`ai_broad`, the saturated baseline everyone
already uses) and the "AI agent" / "agentic AI" phrase family (`agentic`, the
Wave-2-specific language). By year, summed across all 5 companies:

| Year | `agentic` mentions | `ai_broad` mentions |
|---|---|---|
| 2019-2025 | **0 every year** | 1 → 3 → 4 → 4 → 3 → 5 → 5 |
| 2026 | **4 total** (JPM, HSBC, PayPal, Block — one filing each) | 5 |

Seven straight years of zero, then four filings in the most recent cycle —
across a universe of five companies. That is a real, dated first-appearance
in a legally-binding disclosure (not marketing copy), but it is also
*exactly* the kind of thin signal that shouldn't be over-read into a market
call. `ai_broad`, for comparison, is already saturated by 2019 — confirming
it's a baseline, not a discriminator.

**Checked against the entire market, not just these 5 companies
(`collect_edgar_marketwide.py`, `data/raw/edgar_marketwide.csv`,
`charts/edgar_marketwide.png`)** — the same `agentic` query, same form type,
same years, but with no company filter at all, across every 10-K filer in
EDGAR:

| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Market-wide `agentic` filings | 5 | 1 | 0 | 1 | 3 | 6 | **111** | **383** |

This is the single strongest piece of evidence in the whole project for "the
thinness is early, not absent, and not an artifact of a 5-company sample."
Market-wide, `agentic` language sits in the low single digits — against a
10-K filer population in the tens of thousands — for six straight years,
then jumps roughly 18x in 2025 and grows further in 2026. That's the same
shape as the 5-company sample, at a completely different scale, found
independently. It directly answers the obvious objection to Part 2: no, this
isn't just an artifact of which 5 companies happened to get picked.

(Two data points here needed manual re-verification: the unscoped market-wide
query is noticeably flakier than the per-company queries — it returned a
spurious `0` for `ai_broad` 2026 on first pull, which was 3640 on retry
seconds later, consistent with 2025's 3324, and `agentic` 2024 failed after
its automatic retries and was re-queried by hand to get 6. Both are recorded
in `collect_edgar_marketwide.py`'s comments. Worth knowing if you re-run this
and see a suspicious zero.)

**Search attention** — Wave 2 terms ("AI agent finance", "agentic AI
banking", "autonomous wealth management") register **literally zero** search
interest every year from 2018 through 2023. Interest turns on in 2024-2025
and reaches ~22 by 2026 — real, but from a standing start, over two years,
and still below Wave 1's level.

**No market proxy exists.** Unlike Wave 1, there is no "AI-native fintech"
stock basket in this project — because, per your framing, the relevant
companies aren't public. This isn't a limitation to fix with more tickers;
it's the actual state of the world this verdict is trying to describe.

## Part 3: The likely winner is the banks, again — plausible, not proven

The dramatic version of the Wave 2 thesis assumes incumbent banks are too
encumbered by legacy infrastructure to use AI effectively, leaving room for a
new AI-native challenger to repeat the Wave 1 playbook. That assumption is
not well supported by anything measurable here, and one available data point
leans the other way: **all four companies whose 2026 filings contain
`agentic` language are already-established incumbents in this dataset — JPM,
HSBC, PayPal, and Block.** None are a new AI-native entrant, because none
exist in the sample.

This is **consistent with** "incumbents move first," not **proof of** it —
be precise about that distinction if you cite it. The dataset was built from
public companies only, which structurally excludes any private AI-native
challenger that might be moving just as fast or faster out of public view.
Absence of a counter-example in a sample that couldn't contain one either way
is weak evidence, not strong evidence. What tips the prediction toward
"banks win again" is mostly outside this codebase: balance-sheet scale,
existing compute/data budgets, and the fact that (per Part 1) the banks are
the ones with the profits to fund an AI build-out right now, while several of
the would-be Wave 1 challengers were posting losses as recently as 2022-2023.

## Part 4: What "averaging vs. splitting" actually shows (corrected)

An earlier draft of this project's hypothesis claimed that a blended
Wave-1-plus-Wave-2 index would show *nothing dramatic* — that averaging a
fading wave against a rising one cancels the signal, and only splitting them
apart reveals the story. Checking that claim against the actual pipeline
output shows it's **not quite right, and the corrected version is a
sharper point**:

```
Real data, composite FDI:      2 breaks detected (Apr 2021, Jun 2025)
                                Chow p = 0.006 and p < 0.001 — both significant
Synthetic demo data, FDI:      0 breaks detected at all
```

The "averaging cancels the signal" story is exactly what the **synthetic
demo** shows (`output/break_results_synthetic.json`) — it was built by
construction to prove that point. It is **not** what the real collected data
shows. In the real run, the blended index has two highly significant,
dramatic turning points. So "you'd see nothing in the blend" is false for
this project's actual result.

What *is* true, and is the better version of the same insight: the blended
FDI's two break dates are **identical to Wave 1's alone** (April 2021, June
2025), purely because Wave 1 and Wave 2 happen to both inflect upward around
the same months in 2025. Read the blend at face value and you'd date "the AI
story" to April 2021 — which is actually Wave 1 rolling over, unrelated to
AI. **The blend doesn't hide that something happened; it misattributes what
happened and when.** Splitting the waves apart is what lets you correctly
date and assign each story to its real cause — not what makes an otherwise
invisible signal visible.

`charts/incumbent_response.png` adds a related nuance: incumbents'
AI-disclosure ramp doesn't move *simultaneously* with fintech market
pressure — it lags. Fintech pressure (Wave 1) peaked in 2021; AI-language
intensity actually dips through 2023-2024 before climbing into 2025-2026.
The banks' formal AI disclosure shows up years after the competitive threat
that (per Part 3) might be motivating it, not concurrently with it.

## Limitations — read before over-citing this

- **Proxies, not ground truth.** Search interest measures attention, not
  adoption. Filing language measures what companies *say*, not what they
  ship or how much revenue it drives. Stock price reflects expectations, not
  realized market share. Net income is a real financial outcome, but only
  four fiscal years are available per company via `yfinance`, too short to
  fully separate a rate-cycle effect from company-specific factors.
- **Short Wave 2 window.** The genuine acceleration signal covers roughly
  2024-2026 — about two years. A single flat year would meaningfully change
  the picture; this cannot yet be distinguished from a temporary spike with
  full confidence.
- **Thin, noisy tail.** The final one to two months of the combined index
  (June-July 2026) reverse sharply in *both* sub-indices simultaneously —
  treated as noise here, not a new trend, but worth re-checking in 6-12
  months.
- **Small, hand-picked, all-public company set — partially mitigated for
  Part 2.** 5 companies for EDGAR, 7 tickers for market prices, all of them
  public incumbents or already-public 2010s fintechs. The market-wide EDGAR
  check above confirms the "thin until 2024-2025" shape isn't a 5-company
  artifact, but the underlying gap remains for Part 3: there is still no way,
  with any data collected here, to see a private AI-native challenger even
  if one existed and was winning right now.
- **Part 3 is a prediction, explicitly labeled as such.** It should not be
  cited with the same confidence as Parts 1 and 2, which describe what
  already happened.

## Bottom line

**Fintech didn't die, and AI hasn't clearly taken over anything yet.** The
first wave of app-based fintech grew up, and by the measures available here
(price, profitability, search attention), it's been substantially reabsorbed
by the banks it once threatened — most sharply visible in the 2022 net-income
split, where the challengers posted losses in the same year bank profits
grew. The second wave is too early to call with market data because the
relevant companies aren't public; what thin, measurable evidence does exist
(EDGAR `agentic` language, search interest) is consistent with an early,
real inflection starting around 2024, not with nothing happening. The smart
bet, though not something this project can prove, is that the banks capture
the AI wave the same way they captured the first one — they have the profits
to fund it, and (so far, in this small sample) they're the ones with their
name on the filings that mention it.
