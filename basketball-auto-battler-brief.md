# Project Brief — Basketball Auto-Battler (working title TBD)

**For:** Claude Code
**From:** Xavier
**Status:** Early concept. Intentionally high-level — most decisions are still open. Where something isn't specified below, **ask me before assuming.**

---

## The idea in one line

A TFT / auto-battler–style game reskinned as basketball: you build a lineup in a shop/build phase, then it auto-resolves as a **scored game** against another lineup. Most points wins — no combat, no HP, no elimination.

## Core loop (high level)

Two repeating phases:

1. **Build phase** — acquire players from a rotating market, merge duplicates to level them up, position them, and manage a budget. The decisions here *are* the game.
2. **Game phase** — your lineup automatically plays out a short game against an opponent's lineup. You don't control the action; you watch the result of how you built. The outcome is a **score**, not a knockout.

Closest references: **Teamfight Tactics** and **Super Auto Pets** — same genre DNA, but the auto-battle is reskinned so players *score* instead of fight.

## Systems to carry over (conceptual — all tuning is open)

We want to keep the multi-layered depth of the genre, not a single rating-sum. At a high level:

- **Economy / tempo** — a budget resource with a save-vs-spend tension (interest-style incentives, streak bonuses, etc.). Exact model TBD.
- **Rotating market** — players appear to acquire and can be refreshed, with some randomness.
- **Merge & level** — combine duplicate players to level them; leveling should strengthen their *abilities*, not just raw stats.
- **Archetypes & synergies** — lineup composition unlocks bonuses at breakpoints (e.g., fielding enough of an archetype). Specific archetypes TBD.
- **Positioning / spacing** — where players sit on a half-court matters (spacing, matchups). This is a real skill layer, not cosmetic.
- **Signature abilities** — players have abilities that trigger during the game and chain with each other.
- **Scoring resolution** — the "battle" is a possession-based scored game; more points wins. How literal vs. abstract the sim is = open.
- **Modes** — likely an async mode first (play against snapshots of other players' lineups, no live opponent), with a live multiplayer lobby possible later.
- **Generic players** — fictional, archetype-based players (no real names, likenesses, or teams) to avoid licensing.

## Intentionally undecided — open questions for Xavier

> Claude Code: please surface these to me rather than picking defaults.

**Direction & scope**
- Start with basketball / 5-on-5 (maps cleanly to a 5-slot lineup), or a different structure?
- What is the smallest prototype that proves "score, don't fight" is actually fun?
- Async-first, or live-lobby-first?

**Resolution / sim**
- How literal should the sim be — abstracted possession rolls, or a light play-by-play?
- How long is a "game" (possessions / quarters)?
- What inputs decide a possession (matchup, spacing, abilities, RNG weighting)?
- Should the result be **readable** — i.e., show *why* a lineup won (which matchups and abilities mattered)?

**Build systems**
- How many court slots and bench depth?
- How does leveling work — merge duplicates only, or other paths?
- Roughly how many archetypes, and how many synergy breakpoints?
- How much should positioning/spacing matter relative to raw roster quality?

**Economy**
- What's the budget resource (cap space, scouting points, generic currency)?
- How much should economy/tempo matter vs. lineup strength?

**Content & later**
- Do we ever want a "real-data" mode (current real players mapped onto archetypes via public stats/names only — no logos or likenesses), or stay fully fictional?
- Monetization, platform, and tech-stack preferences?
- Art direction / tone (street-ball vibe, clean modern, retro, etc.)?

## Suggested first step (loose)

Build a throwaway prototype of **just the core loop**: draft a handful of generic archetype players, set a simple lineup and spacing, and auto-resolve a scored game against a fixed opponent — enough to feel whether "build it, then watch it score" is satisfying. Economy depth, synergies, modes, and art all come *after* we know the loop is fun.

## Guardrails

- Keep players fully generic/fictional — no real names, teams, logos, or distinctive identifying attributes.
- Build systems to be easily tunable; the numbers will change a lot.
- This brief is high-level on purpose. **When in doubt, ask me.**
