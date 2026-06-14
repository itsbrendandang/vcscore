# vcscore — internal investor-diligence tool

Raising from VCs is hard, and the process is largely a black box. You fly mostly blind on
who you're taking money from and how they actually behave once the wire clears, especially
when things go wrong. There's plenty of public signal scattered across news, podcasts, and
posts, but nobody has it organized for a founder trying to decide.

`vcscore` pulls that scattered **public** signal together for your own diligence. It's the
mirror of [dtscore](../deeptech-scorer): instead of scoring companies, it organizes what's
publicly known about the people writing the checks.

The core question it answers: **how founder-friendly is this investor — how do they actually
treat founders, especially when things go wrong?** Behavior in adversity (down rounds,
recaps/washouts, founder removals, board conduct, follow-on support) is the sharpest tell, so
it's weighted heaviest. Everything else is secondary to "how are they to founders."

> **This is an internal tool, not a published product.** It organizes public information for
> *your own* decision. It asserts nothing of its own, and it is not a verdict on any firm.
> That scope is deliberate: it keeps you out of the reputation-publishing legal minefield.
> If you ever want a public version, that's a separate project with its own legal review.

## How it works

```
  gather (Claude + web search)  ─►  verify (fetch each source)  ─►  score (deterministic)  ─►  report
  findings: claim + source +         keep only findings whose       verified findings →          scorecard
  sign + severity, per dimension     source actually supports them   0-10 per dimension          or timeline
```

- **The LLM never sets the score.** It gathers *findings* (each tagged founder-friendly /
  unfriendly / neutral, with a severity and a source URL). Deterministic code turns the
  **verified** findings into numbers, so the scoring is transparent and tunable in `rubric.yaml`.
- **Citation verification** fetches every source URL and keeps a finding only if the page
  actually loads and mentions the firm. This catches the failure mode that matters most with
  sparse data: a plausible-looking but hallucinated or non-supporting source. Findings it
  can't confirm aren't deleted, they're listed under "check these yourself" and don't score.
- **No fabricated composites.** If fewer than 4 dimensions have verified signal (common, the
  juicy stuff is often private), there's no score, the firm renders as a **sourced incident
  timeline** instead. It degrades to "here's the record," never to "here's a made-up number."

## Usage

```bash
cd ~/vcscore

# Offline, no key needed:
./vcscore score firms/example-ventures.yaml --save-md   # score the fictional example
./vcscore rubric                                          # see/tune the dimensions + weights
./vcscore new acme-vc --firm "Acme Ventures"             # blank profile to fill by hand

# Needs ANTHROPIC_API_KEY + network:
export ANTHROPIC_API_KEY=sk-ant-...
./vcscore run "Acme Ventures"        # research + verify sources + score
./vcscore verify firms/acme-vc.yaml  # re-check the source links on a profile
```

`score`, `new`, `rubric` are fully offline. `run`/`gather` call Claude; `verify` fetches the
source URLs.

## Do this before trusting it

Whether this is worth using at all hinges on one thing: is there enough *public, verifiable*
adversity signal per firm, or does it cluster on a few famous blowups? Before relying on it,
spot-check by hand: pick a couple of firms you know something about, run `vcscore run`, and
confirm the receipts are real and the framing is fair. If most firms come back as thin
timelines, that's the tool being honest, not broken.

## Files

- `rubric.yaml` — 7 dimensions, weights (adversity heaviest), bands. The tunable brain.
- `gather.py` — Claude + web search → tagged findings (model `claude-opus-4-8`, adaptive thinking).
- `verify.py` — fetch each source, confirm it supports the claim.
- `scoring.py` — deterministic finding → score, unknown handling, timeline fallback.
- `report.py` — terminal + markdown, receipts + always-on disclaimer.
- `vcscore.py` / `vcscore` — CLI + wrapper.
- `tests/test_scoring.py` — offline tests for scoring + verification.
- `firms/example-ventures.yaml` — a **fictional** example firm.

## Roadmap

- **X / Twitter ecosystem monitor (planned).** Connect a bot to X to continuously watch the
  founder/investor ecosystem, surfacing fresh public signal about how firms treat founders and
  feeding it into the gather step, so a firm's picture updates over time instead of being a
  one-off lookup. Same rules apply: anything it surfaces still needs a verified public source
  before it scores, and it uses the official API, no scraping.

---

Sibling design philosophy to dtscore: LLM gathers the mess, deterministic code does the scoring.
