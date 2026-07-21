# Verdict: FinTech Disruption of Traditional Banking

**Thesis question:** Digital payment platforms, neobanks, and embedded finance players have taken significant market share from legacy institutions. Thesis evaluate whether FinTech disruption has run its course or whether the second wave of AI-native financial services is just beginning

## Verdict

The **first wave of fintech** has, in many respects, already reached its limits. Between 2010 and 2021, digital payment platforms, neobanks, and fintech challengers such as PayPal, Block (formerly Square), and Robinhood primarily differentiated themselves through superior user experience rather than fundamentally different banking models. Although these firms captured market share and reshaped customer expectations, many experienced significant profitability challenges after 2021, while incumbent banks regained momentum as rising interest rates strengthened their earnings. As a result, traditional institutions have largely reclaimed the pricing power and competitive position that fintech firms briefly challenged. This conclusion is supported by robust, transparent financial data from publicly listed companies over multiple years.

The **second wave of AI-native finance** presents a fundamentally different challenge, but one that cannot yet be evaluated with the same level of confidence. Most AI-first financial firms remain private or are too young to provide meaningful financial or market performance data. Consequently, there is insufficient evidence to determine whether AI-native firms are creating lasting competitive advantages or simply attracting early attention. The available indicators—such as Google search interest and AI-related regulatory disclosures—show only modest increases beginning in 2024. Rather than representing a weakness of the analysis, this lack of measurable evidence is itself an important finding: the AI-native wave is still too early to assess conclusively.

Taken together, the evidence points toward a more likely outcome: **incumbent banks are better positioned to absorb AI than to be displaced by it.** While the narrative that legacy institutions are too slow or technologically outdated remains plausible, current evidence provides little empirical support. Instead, the limited observable data suggests that established banks are adopting and disclosing AI initiatives at least as actively as emerging challengers.

The project's strongest empirical contribution is the distinction between the two waves of fintech innovation. Treating fintech as a single, continuous phenomenon obscures important structural differences. Separating the first wave of app-based challengers from the emerging AI-native wave reveals that they are driven by fundamentally different dynamics and stages of maturity. This distinction provides a more accurate interpretation of the evidence than a blended analysis, which risks attributing observed trends to the wrong source.


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

**Profitability evidence (`data/raw/fundamentals.csv`, not previously wired
into any chart in this project):**

| Ticker | 2022 net income | 2023 net income |
|---|---|---|
| SOFI | **-$320M** | -$301M |
| XYZ (Block) | **-$541M** | +$10M |
| NU (Nubank) | **-$365M** | +$1,031M |
| JPM | +$37.7B | +$49.6B |
| HSBC | +$15.6B | +$23.5B |

2022 was a losing year for these three disruptors, while both banks' profits
grew substantially.

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

## Part 2: Wave 2 (AI-native finance) is not yet measurable

This project cannot price "is AI-native finance winning" the way it can
price Wave 1, because the companies that would represent that wave are
mostly private or too newly public to have real stock history. Trying to
force a market-price answer here would mean reading a signal into a handful
of thin, noisy tickers that isn't really there. The honest move — which this
verdict takes — is to say so, and to treat the thinness of every measurable
proxy as evidence that the wave is early, not evidence that it's absent.

**SEC filings — the sharpest available signal, and it's thin by design, not by
accident (`data/raw/edgar_mentions.csv`, charted alongside the market-wide
check below in `charts/edgar_marketwide.png`)**. Filings were searched for
`"artificial intelligence"` (`ai_broad`, the saturated baseline everyone
already uses) and the "AI agent" / "agentic AI" phrase family (`agentic`, the
Wave-2-specific language). By year, summed across all 7 companies:

| Year | `agentic` mentions | `ai_broad` mentions |
|---|---|---|
| 2019-2025 | **0 every year** | 1 → 3 → 4 → 5 → 5 → 7 → 7 |
| 2026 | **5 total** (JPM, HSBC, Barclays, PayPal, Block — one filing each) | 7 |

Seven straight years of zero, then five filings in the most recent cycle —
across a universe of seven companies. That is a real, dated first-appearance
in a legally-binding disclosure (not marketing copy), but it is also
*exactly* the kind of thin signal that shouldn't be over-read into a market
call. `ai_broad`, for comparison, is already saturated by 2019 — confirming
it's a baseline, not a discriminator.

**Checked against the entire market, not just these 7 companies
(`collect_edgar_marketwide.py`, `data/raw/edgar_marketwide.csv`,
`charts/edgar_marketwide.png`)** — the same `agentic` query, same form type,
same years, but with no company filter at all, across every 10-K filer in
EDGAR:

| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Market-wide `agentic` filings | 5 | 1 | 0 | 1 | 3 | 6 | **111** | **388** |

This is the single strongest piece of evidence in the whole project for "the
thinness is early, not absent, and not an artifact of a 7-company sample."
Market-wide, `agentic` language sits in the low single digits — against a
10-K filer population in the tens of thousands — for six straight years,
then jumps roughly 18x in 2025 and grows further in 2026. That's the same
shape as the 7-company sample, at a completely different scale, found
independently. It directly answers the obvious objection to Part 2: no, this
isn't just an artifact of which 7 companies happened to get picked.

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
leans the other way: **all five companies whose 2026 filings contain
`agentic` language are already-established incumbents in this dataset — JPM,
HSBC, Barclays, PayPal, and Block.** None are a new AI-native entrant, because
none exist in the sample. Notably, **neither neobank in the sample — SoFi nor
Nubank — shows `agentic` language even in 2026**; the signal is concentrated
entirely among the traditional banks and the older, already-public
embedded-finance players, which is the opposite of what the "AI-native
upstart" version of the Wave 2 thesis would predict.

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
