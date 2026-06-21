# Abilities & Signature Moves — research / shortlist

**For:** Xavier to mark up. Tick `[x]` the ones you think work, strike through ones you don't, scribble new ones at the bottom of each section. Once you've marked it I'll wire the keepers into `sim.py`.

**How to read the "Hooks into" column:** every ability has to attach to a number the sim already computes, or it's just flavor. The current sim levers are:
- shot make-% (`_evaluate`: base + off + fit − contest − help − deep)
- pass/steal risk (`_pass_risk`)
- the shooter-selection weighting (which player takes the shot)
- positioning / movement (setup drift, shot-target step)
- defense contest & help amounts
- a NEW lever we'd add: **start-of-possession / start-of-game triggers** (SAP-style)

Keep abilities to **one clear lever each** at first — that's what stays readable on the court.

---

## A. Trigger types (the grammar — pick which ones the game supports)

Borrowed from Super Auto Pets (start-of-battle, on-summon, on-faint) and 2K badges (passive thresholds). For a *scored* basketball game these map cleanly:

- [x] **Passive** — always on (e.g. +shooting from the corner). Simplest. Like 2K badges.
- [ ] **Start of game** — fires once before tip (e.g. "+1 OFF to adjacent shooters"). SAP "start of battle."
- [x] **On-possession** — rolls each possession (e.g. "20% chance to draw a foul = free point").
- [ ] **On-score / streak** — builds up (e.g. NBA Jam "on fire" after 2 straight buckets → make-% boost).
- [ ] **On-trigger-by-teammate** — synergy chains (screen frees the cutter; lob big finishes a PG dish).
- [x] **Conditional** — only vs certain opponents/spots (e.g. "+DEF vs three-point-heavy teams").

> My rec: ship **Passive + Start-of-game + Synergy-chain** first. "On fire" streaks are great flavor but add the most sim complexity — flag it for v2.

---

## B. Signature moves (real players → generic abilities)

Names stay fictional in-game; these are the *mechanics* to borrow. Inspirations listed so you can judge the fantasy.

| ✓ | Ability (working name) | Inspired by | In-game effect | Hooks into |
|---|---|---|---|---|
| [x] | **Dream Shake** | Hakeem's footwork | Big gets a layup-tier shot from midrange (post fadeaway counts as rim) | shot type / fit |
| [ ] | **One-Legged Fade** | Dirk fadeaway | Ignores up to X of the on-ball contest penalty | `contest` term |
| [x] | **Killer Crossover** | Iverson / Hardaway | First defender in the lane is "broken" — removed from this possession's help | `help_d` |
| [x] | **Eurostep** | Ginóbili / Wade | +finish % at the rim through contact (beats help) | rim make-% |
| [ ] | **Sky Hook** | Kareem | Unblockable: contest can't drop the shot below a floor % | clamp on `prob` |
| [x] | **Logo Pull** | Curry / Lillard | Can shoot 3 from deeper with no deep-distance penalty | `deep` term |
| [x] | **Fadeaway J** | Jordan / Kobe | +midrange make-%, immune to help defense | midrange + `help_d` |
| [x] | **Dimer** | Stockton / CP3 | Teammate who receives this player's pass gets +make-% on the shot | pass → shot link |
| [x] | **Lob Threat** | Vince / Zion | If this big receives a pass at the rim, the finish is near-automatic | rim make-% on pass |
| [x] | **Pickpocket** | Payton / Kawhi | +steal chance when guarding his man's passing lane | `_pass_risk` lane |
| [x] | **Brick Wall** | screen-setting bigs | His screen gives the freed teammate a bigger open look | synergy chain |
| [x] | **Heat Check** | Klay / J.R. | After a make, next shot this game gets a one-time boost | on-score trigger |

---

## C. 2K-style "badge" passives (cleaner, less character-specific)

Good for filling out lower tiers where players are plain. Five-rank ladder (Bronze→Legend) optional later.

| ✓ | Badge | 2K source | In-game effect | Hooks into |
|---|---|---|---|---|
| [ ] | **Deadeye** | Outside Scoring | Less make-% lost to a contest on jumpers | `contest` |
| [ ] | **Limitless Range** | Outside Scoring | No penalty on deep threes | `deep` |
| [ ] | **Slippery Off-Ball** | Gen. Offense | Starts each possession with extra separation (auto more open) | setup spacing |
| [x] | **On-Ball Menace** | Defense | Hands his man a make-% penalty even at distance | `contest` floor |
| [ ] | **Interceptor / Glove** | Defense | Big boost to steal chance in nearby lanes | `_pass_risk` |
| [ ] | **High-Flying Denier** | Defense | Extra help-defense suppression of rim shots | `help_d` (rim) |
| [ ] | **Handles for Days** | Playmaking | Lower turnover risk when this player initiates | passer risk |
| [ ] | **Brick Wall** | Gen. Offense | (see synergy) screen reduces defender's contest on the cutter | synergy |

---

## D. Arcade / street mechanics (run-level spice — optional, higher complexity)

| ✓ | Mechanic | Source | Idea for our game |
|---|---|---|---|
| [ ] | **On Fire** | NBA Jam | 2 straight makes by one player → that player's make-% spikes until the other team scores |
| [ ] | **Gamebreaker** | NBA Street | Fill a style meter over a game → one possession worth +1 extra point |
| [ ] | **Turbo / tempo** | NBA Jam/Street | A team-wide "pace" stat: more possessions but lower make-% (a build identity, not an ability) |
| [ ] | **Hot hand carryover** | arcade | A player who balls out one round starts the next with a small boost (feeds the "Mike Fletcher legend" idea) |

---

## E. Duos & Big 3s (your request — named-player chemistry)

SAP/TFT synergy, but tied to *specific preset players* so chemistry is part of the lore. When the named pair/trio share a lineup, **+1 to all four stats** (your spec) — or a flavored effect:

| ✓ | Combo type | Effect | Notes |
|---|---|---|---|
| [ ] | **Duo (named pair)** | Both get +1 OFF/DEF/PAS/STL | flat, simple, your spec |
| [ ] | **Big 3 (named trio)** | All three +1 all stats (or +2 to one signature stat each) | rarer, splashier |
| [ ] | **Pick-and-roll duo** | A specific PG + Big: the lob/dump-off finish is boosted | mechanic, not just stats |
| [ ] | **Splash bros duo** | Two shooters: each ignores the other's defender's help | spacing fantasy |
| [ ] | **Lockdown duo** | Two defenders: opponent's pass risk up team-wide | defensive identity |
| [ ] | **Archetype synergy** (generic, not named) | e.g. "2+ shooters → everyone +three%" — TFT trait breakpoints as a fallback for un-paired players | keeps low tiers interesting |

> Open question for you: should chemistry be **named-pair only** (rare, collectible, "I found the Fletcher–Reyes duo"), **archetype-trait** (TFT breakpoints, always available), or **both layered**? My lean: both — traits as the floor, named duos as the chase.

---

## F. Things to decide before I build (quick marks)

- [1] Max abilities per player: **1** (clean) or **2** (deeper, busier)?
- [Level up] Do abilities **level up** with the player (SAP merge), or stay fixed?
- [All players have abilities low tier has worse abilities ] Should low-tier players have **no ability** (so unlocking one feels good), or weak ones?
- [no ] "On fire" / streak mechanics in v1, or defer to v2?

---

### Your additions (write below)
- Abilities can be anything that effect the game for example your PG could have the "star power" that give you extra cap space if hes on your team
- even negativa abillites maybe a player has really good scoring but has an ability that makes them more turnover prone 
-The current Concept of in game abilities is good and the inspiration from real basketball moves is smart but incoorperate more abilities from all aspects of the game 
- Output a simple list of just abilities with a short description after then ill fo through change the description to what i want and add/remove/edit how i see fit

---

**Sources:**
- [NBA 2K25 Badges Explained — Game Rant](https://gamerant.com/nba-2k25-badges-explained-changes-progression-tiers/)
- [NBA 2K25 Badge system explained — Charlie INTEL](https://www.charlieintel.com/nba-2k/nba-2k25-badge-system-explained-335528/)
- [Why Being On Fire Was So Cool in NBA Jam — NLSC](https://www.nba-live.com/ww-why-being-on-fire-was-so-cool-in-nba-jam/)
- [NBA Jam — StrategyWiki](https://strategywiki.org/wiki/NBA_Jam)
- [NBA Street Vol. 2 — Giant Bomb](https://giantbomb.com/wiki/Games/NBA_Street_Vol_2)
- [13 Basketball Signature Moves That Changed The Game — Sports Feel Good Stories](https://www.sportsfeelgoodstories.com/basketballs-signature-moves/)
- [The Origins of Hakeem Olajuwon's "Dream Shake" — The Ringer](https://www.theringer.com/2024/10/15/nba/hakeem-olajuwon-dream-shake-book-excerpt-the-life-and-legacy)
- [Super Auto Pets mechanics — a327ex.com](https://a327ex.com/posts/super_auto_pets_mechanics)
- [Glossary — Super Auto Pets Wiki](https://superautopets.fandom.com/wiki/Glossary)
