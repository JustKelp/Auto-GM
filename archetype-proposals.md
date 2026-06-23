# Archetype Expansion — proposals for the 200-player pool

**What this is.** Options for *new* archetypes to add to HARDWOOD, grounded in the
2015-16 SportVU tracking set (the same data behind the current 16 — see
`../NBAHeatmaps/archetypes.py` and `archetype_expansion.md`). You asked for a focus
on **guards** but to look across the board. Go through and mark each one
**ADD / KEEP / REMOVE / MERGE**; nothing here is wired in yet.

**How to read a proposal.** Each block gives a paste-ready spec:
- **Slots** — roster positions it can fill (1=PG 2=SG 3=SF 4=PF 5=C)
- **Role** — the real-world standard
- **2015-16 exemplars** — real players for `archetypes.py` so the heatmap (anchors +
  shot mix) can be derived on the next `build.py`/`export.py` run
- **Fills** — the gap vs the current 16
- **Stat shape** — `sht/dfn/plm/ath` budget split (the `gen_pool.ARCH_SHAPE` format;
  remember scoring is SPLIT: jump-scoring → SHT, rim-finishing → ATH, steals fold into DFN)
- **Shot mix** — (rim, mid, three) for `ARCHETYPE_ZONE_MIX`
- **Behavior** — one of the existing engine behaviors: `distribute / pull_up / cut /
  roll / screen / spot_up`
- **Abilities** — candidate signature pool
- **Rec** — my recommendation (⭐ = strongest adds)

---

## Part 1 — the current 16 (mark KEEP / REMOVE / MERGE)

The PG slot (1) is the thinnest in the game — only **Pass-First PG, Scoring PG, Combo
Guard** can play it. Two current buckets are also broad enough that you *could* split
them (which is most of where the new guard options below come from).

| # | Archetype | Slots | Note / overlap | Keep? |
|---|---|---|---|---|
| 1 | Pass-First PG | 1 | distinct (pure floor general) | [ ] |
| 2 | Scoring PG | 1,2 | broad — leans jumper-scorer; downhill guards don't fit | [ ] |
| 3 | Combo Guard | 1,2 | **very broad** — currently absorbs microwave scorers, 3-level scorers, slashers | [ ] |
| 4 | Sharpshooter | 2,3 | distinct (off-ball movement shooter) | [ ] |
| 5 | Shooting SF | 2,3 | distinct | [ ] |
| 6 | Lockdown Wing | 2,3 | a *wing* stopper — no guard-sized equivalent exists | [ ] |
| 7 | 3&D Wing | 2,3 | a *wing* 3&D — no guard-sized equivalent exists | [ ] |
| 8 | Slashing SF | 3,4 | a *wing* slasher — no guard-sized equivalent | [ ] |
| 9 | Point Forward | 3,4 | distinct | [ ] |
| 10 | Two-Way Forward | 3,4 | a *wing* two-way — no guard equivalent | [ ] |
| 11 | Stretch 4 | 4,5 | distinct | [ Combine with stretch center] |
| 12 | Rim-Run Big | 4,5 | leans vertical/lob; energy/putback bigs blur in | [ ] |
| 13 | Stretch Center | 4,5 | distinct | [Combine with stretch 4 ] |
| 14 | Post Scorer | 4,5 | distinct | [ ] |
| 15 | Screening Big | 5 | distinct | [ ] |
| 16 | Defensive Anchor | 5 | distinct | [ ] |
Microwave Scorer
Three-Level Scorer
Downhill Guard
Utility (Glue Wing)
Playmaking Big
Energy Big

**Theme:** the wing tier has Lockdown / 3&D / Slashing / Two-Way variants, but the
**guard tier has no defensive, no slashing, and no instant-offense variant** — they all
collapse into "Combo Guard." That's the main expansion opportunity.

---

## Part 2 — GUARD proposals (your priority)

### G1. Two-Way Guard  ⭐
- **Slots:** 1, 2
- **Role:** lead/combo guard who guards the point of attack *and* runs offense — mid
  usage, real defense, steady playmaking. The guard version of Two-Way Forward.
- **2015-16 exemplars:** Mike Conley · Jrue Holiday · Kyle Lowry · George Hill ·
  Patrick Beverley · Avery Bradley · Jeff Teague · Goran Dragic
- **Fills:** there is *no* two-way guard today — defensive guards have to be "Lockdown
  Wing" (wrong size) or "Combo" (no defense). Biggest single gap.
- **Stat shape:** `dict(sht=.26, dfn=.38, plm=.26, ath=.10)`
- **Shot mix:** (0.10, 0.27, 0.63)
- **Behavior:** distribute · **Abbr:** PG/SG
- **Abilities:** on_ball_menace, pickpocket, floor_general, tempo_control, lockdown
- **Rec:** ⭐ add — fixes the clearest hole and enables new chemistry (e.g. "Two-Way Backcourt").

### G2. Microwave Scorer (Sixth Man)  ⭐
- **Slots:** 1, 2
- **Role:** instant-offense bench scorer — high usage in bursts, pull-ups + deep threes,
  streaky, minimal playmaking/defense.
- **2015-16 exemplars:** Lou Williams · Jamal Crawford · Nick Young · Jordan Clarkson ·
  Mo Williams · Marcus Thornton · Jeremy Lin
- **Fills:** splits the scoring-only volume guy out of "Combo Guard"; pairs perfectly
  with the now-active **Heat Check / Streaky** abilities.
- **Stat shape:** `dict(sht=.50, dfn=.18, plm=.18, ath=.14)`
- **Shot mix:** (0.08, 0.34, 0.58)
- **Behavior:** pull_up · **Abbr:** SG
- **Abilities:** heat_check, streaky, iso_threat, quick_release, limitless
- **Rec:** ⭐ add — showcases the new abilities and is a recognizable, fun role.

### G3. Slashing Guard (Downhill Guard)  ⭐
- **Slots:** 1, 2
- **Role:** explosive guard who attacks the rim off the bounce and in transition,
  finishes/draws fouls, jumper is secondary.
- **2015-16 exemplars:** Russell Westbrook · John Wall · Eric Bledsoe · Ty Lawson ·
  Reggie Jackson · Michael Carter-Williams · Emmanuel Mudiay
- **Fills:** Scoring PG is jumper-based; Slashing SF is a wing. No rim-attacking guard
  exists — and after the SHT/ATH fix, this is the guard whose scoring lives in ATH.
- **Stat shape:** `dict(sht=.18, dfn=.22, plm=.26, ath=.34)`
- **Shot mix:** (0.22, 0.30, 0.48)
- **Behavior:** cut · **Abbr:** PG
- **Abilities:** eurostep, killer_cross, handles, iso_threat, turnover_prone
- **Rec:** ⭐ add — distinct scoring profile (rim/ATH) and good archetype-diversity.

### G4. 3&D Guard (Point-of-Attack Pest)
- **Slots:** 1, 2
- **Role:** undersized guard who hounds ball-handlers and spaces the corner three —
  low usage, high steals, catch-and-shoot only.
- **2015-16 exemplars:** Patrick Beverley · Avery Bradley · Marcus Smart · Tony Allen ·
  Cory Joseph · E'Twaun Moore · Delon Wright
- **Fills:** guard-sized 3&D (today only the wing 3&D / Lockdown Wing exist).
  Some overlap with **G1 Two-Way Guard** — pick one, or keep G4 as the lower-usage/pure-3&D version.
- **Stat shape:** `dict(sht=.34, dfn=.48, plm=.10, ath=.08)`
- **Shot mix:** (0.07, 0.18, 0.75)
- **Behavior:** spot_up · **Abbr:** SG
- **Abilities:** catch_shoot, corner_spec, on_ball_menace, pickpocket, lockdown
- **Rec:** add *if* you don't take G1, or keep both (G1 = on-ball creator + D, G4 = off-ball 3&D).

### G5. Three-Level Scorer (Shot-Creating Guard)
- **Slots:** 2, 3
- **Role:** high-usage shotmaker who scores at all three levels off the dribble; not a
  primary passer.
- **2015-16 exemplars:** DeMar DeRozan · CJ McCollum · Devin Booker · Bradley Beal ·
  Dwyane Wade · Khris Middleton
- **Fills:** the elite iso scorer — distinct from Combo (lower usage) and Sharpshooter
  (off-ball). Strong overlap with **G2 Microwave** (G2 = bench/streaky, G5 = star starter).
- **Stat shape:** `dict(sht=.46, dfn=.20, plm=.16, ath=.18)`
- **Shot mix:** (0.13, 0.37, 0.50)
- **Behavior:** pull_up · **Abbr:** SG
- **Abilities:** iso_threat, soft_touch, deadeye, heat_check, star_power
- **Rec:** add as a high-tier "star" guard; consider merging with G2 if you want fewer buckets.

---

## Part 3 — WING & BIG proposals (looked at everything)

### W1. Connector / Glue Wing
- **Slots:** 2, 3, 4
- **Role:** low-usage do-everything wing — cuts, swings the ball, defends, hits the open
  three. The "winning plays" guy.
- **2015-16 exemplars:** Andre Iguodala · Joe Ingles · Shaun Livingston · Boris Diaw ·
  Andre Iguodala · Marcus Morris
- **Fills:** between 3&D (shooter) and Two-Way Forward (high usage) — a true connector.
- **Stat shape:** `dict(sht=.24, dfn=.34, plm=.30, ath=.12)`
- **Shot mix:** (0.14, 0.25, 0.61)
- **Behavior:** cut · **Abbr:** WG
- **Abilities:** floor_general, dimer, on_ball_menace, tempo_control
- **Rec:** nice-to-have; lower priority than the guards.

### B1. Playmaking Big (Point Center)  ⭐
- **Slots:** 4, 5
- **Role:** offensive hub big — high-post reads, hand-offs, elite passing for size.
- **2015-16 exemplars:** Nikola Jokic · Draymond Green · Boris Diaw · Marc Gasol ·
  Al Horford
- **Fills:** a real hole — no big initiates offense today (Point Forward is a wing,
  Stretch Center just shoots). Enables "point-five" / hand-off offense + new chemistry.
- **Stat shape:** `dict(sht=.20, dfn=.34, plm=.34, ath=.12)`
- **Shot mix:** (0.30, 0.40, 0.30)
- **Behavior:** distribute (or screen) · **Abbr:** C
- **Abilities:** floor_general, dimer, tempo_control, handles
- **Rec:** ⭐ add — distinctive, and the screen mechanic makes a passing big shine.

### B2. Energy Big (Hustle / Putback Big)
- **Slots:** 4, 5
- **Role:** offensive-glass + rim-runner + energy, very low usage, lives on putbacks and
  dives.
- **2015-16 exemplars:** Tristan Thompson · Kenneth Faried · Montrezl Harrell ·
  Ed Davis · Jordan Hill · Richaun Holmes
- **Fills:** today the offensive-rebound/energy guy blurs into Rim-Run (lob/vertical) and
  Screening (screens). This is the second-chance specialist.
- **Stat shape:** `dict(sht=.05, dfn=.40, plm=.08, ath=.47)`  *(also high hidden REB)*
- **Shot mix:** (0.50, 0.35, 0.15)
- **Behavior:** roll · **Abbr:** C
- **Abilities:** putback, lob_threat, rim_protector
- **Rec:** add if you want more big variety; overlaps Rim-Run, so optional.

---

## Summary & recommendation

| Tier | Proposal | Slots | Priority |
|---|---|---|---|
| Guard | **G1 Two-Way Guard** | 1,2 | ⭐ top |
| Guard | **G2 Microwave Scorer** | 1,2 | ⭐ top |
| Guard | **G3 Slashing Guard** | 1,2 | ⭐ top |
| Guard | G4 3&D Guard | 1,2 | high (or merge w/ G1) |
| Guard | G5 Three-Level Scorer | 2,3 | medium (or merge w/ G2) |
| Wing | W1 Connector Wing | 2,3,4 | low |
| Big | **B1 Playmaking Big** | 4,5 | ⭐ high |
| Big | B2 Energy Big | 4,5 | low/optional |

**My pick for the guard tier:** add **G1, G2, G3** (cleanly distinct: defense / instant-offense /
rim-attack), and **B1 Playmaking Big** for the frontcourt. That takes guards from 4 → 7 and
gives the PG slot real variety, without much overlap. Treat G4/G5 as merge-or-add decisions
and W1/B2 as optional flavor.

## Next steps (once you've marked your picks)
1. Add each chosen archetype to `sim.py`: `ARCHETYPES`, `ARCHETYPE_POSITIONS`,
   `SHOT_PROFILE`, `ARCHETYPE_DEF_SPLIT`, `ARCHETYPE_REB`, `ARCHETYPE_TENDENCY`,
   `ARCHETYPE_ZONE_MIX`, `PREFERRED_SHOT` (via behavior), and `gen_pool.ARCH_SHAPE` +
   `ARCH_ABILITIES`.
2. Add its 2015-16 exemplars to `../NBAHeatmaps/archetypes.py` and re-run
   `build.py` → `export.py` to derive real **anchors + shot mix** (replaces my estimates).
3. Regenerate the pool (`gen_pool.py`) so the new archetypes populate across tiers.
4. Optionally add new **chemistry** combos (e.g. Two-Way Backcourt, Point-Center hand-off).
