# HARDWOOD — Change Report
**Source:** review conversation (2026-06-20)

**BUILD STATUS (updated 2 — overhaul shipped):**
- ✅ **DONE & verified** — Tier pricing (§2), Interest (§2), Tip-off weighted coin flip (§3), Finals (now **sudden-death OT**) + center-court logo, post-game stats (now **team-aggregate only**, per your note — no per-player overwhelm).
- ✅ **STAT OVERHAUL SHIPPED (§1)** — shown stats are now **SHT / DEF / PLM / ATH** (Athleticism = Speed+Size). Pool converted in place (all 100 names/identities preserved) via `SHOT_PROFILE` (source of truth). Hidden stats derived in `_instantiate` (`s_rim/s_mid/s_three`, `d_onball/d_block/d_steal`, `p_handle/p_pass/p_vision`, `quickness`) and re-derived on level-up/chemistry. `_evaluate` now reads the **zone-specific** scoring stat (jumpers→SHT, rim→ATH finishing) at `ZONE_COEFF=0.05` — the Shaq fix + problem-6 lever.
- ⚖️ **Balance after tuning:** mirror dead even (win .441 / loss .443, ~4.1 pts/side), layup make **.630 = real .63**. Found & fixed one **clear imbalance**: Sharpshooter was OP (0.523 win) → trimmed its 3pt weight 1.1→0.95 and `BASE_THREE` .37→.35; archetype spread tightened to **0.383–0.480**.
- ⏳ **STILL OPEN / FINDINGS** — (a) **3-point frequency ~47% vs real 33%** — a shot-*selection* issue (the `ev**4` funnel, problem 1/§4), not make-rate; you control placement in real play, so see how it feels first. (b) **Post Scorer** is the weakest archetype (0.383) — watch it. (c) Optional ES-spreadsheet pool expansion (needs `openpyxl`; those xlsx are tiny).

Legend: ✅ locked (agreed, ready to build) · ✏️ needs your authoring input · ⛔ considered & deliberately kept/rejected · ↩️ a claim I retracted

---

## 1. The big one — Stat system overhaul ✅ (schema) / ✏️ (tuning)

**Why:** A single "Offense" number is an over-generalization. It forced a timid make-% multiplier (0.03/pt) so it wouldn't let a big man drain threes — which made offense weak and games lean **defensive**. Defense was already diversified (on-ball vs. steal), so it could carry a stronger effect. Fix = diversify offense the same way.

**Front of card stays simple: four shown stats.** Behind each, a few hidden stats the sim actually reads.

### New four visible stats
**Shooting (Sht) · Defense (Def) · Playmaking (Plm) · Athleticism (Ath)**

- "Offense" → renamed/refocused to **Shooting (Sht)** = jump shooting only.
- **Speed + Size combined** → **Athleticism (Ath)**.
- **Playmaking (Plm)** added.
- **Key consequence (agreed):** scoring now lives in **two** stats — jump scoring under **Sht**, rim scoring under **Ath**. This auto-solves the "Shaq problem": a post scorer reads **high Ath / low Sht** and dominates inside but bricks threes automatically; a sharpshooter reads the reverse. The card now tells the shot-profile story.

### Hidden stats (12 total, 3 per face)

| Shown | Hidden | Drives in sim | Hosts abilities |
|---|---|---|---|
| **Shooting (Sht)** | `midrange` | make-% on pull-ups/floaters | Deadeye, Limitless, |
| | `three` | make-% on threes; cancels deep penalty | Catch & Shoot, |
| | `composure` | contested-shot resistance | Quick Release, Heat Check |
| **Defense (Def)** | `on_ball` | perimeter contest, lowers man's make-% | On-Ball Menace, Lockdown, |
| | `block` | rim protection, suppresses layups | Rim Protector, Shot Blocker, |
| | `steal` | jumps passing lanes, forces TOs | Pickpocket, Interceptor |
| **Playmaking (Plm)** | `handle` | ball security; who initiates; low TO | Handles, Iso Threat, |
| | `passing` | pass accuracy, lowers feed risk | Tempo Control, Turnover Prone, |
| | `vision` | teammate make-% bonus off his pass | Dimer, Floor General, Ball Stopper |
| **Athleticism (Ath)** | `finishing` | make-% at the rim (the Shaq stat) | Eurostep, Dream Shake, |
| | `rebound` | OREB second chances + secures glass | Lob Threat, Soft Touch, |
| | `quickness` | transition, closeout, initiate eligibility | Putback |

**Known tradeoff (accepted):** combining Speed+Size means a quick small guard and a slow big can read similar *Ath* for opposite reasons; the hidden `quickness` vs `rebound`/`finishing` split + the archetype label carry the difference.

### ✏️ Still needs your authoring input (next deliverable)
1. **Per-archetype shot-profile table** — the Sht/Ath split for each of the 16 archetypes (e.g. Post Scorer = rim-heavy, Sharpshooter = three-heavy). *This table is the game's entire offensive identity — you hand-tune it before I regenerate the pool.*
2. **Make-% retune** in `_evaluate` — now that it reads the *matching* hidden stat, the multiplier can be **stronger** without overpowering. Calibrate so the star→role spread reproduces a realistic ~0.10 eFG gap (see §6 data).

### Downstream files touched
`gen_pool.py` (regenerate `_POOL_RAW` to the new shape) · `sim.py` (`_evaluate`, `_pass_risk`, `assign_defense`/contest, rebounding) · `static/app.js` (`statHTML`, tooltips) · `roster.md` (regen).

---

## 2. Economy ✅

| Change | Spec |
|---|---|
| **Variable pricing by tier** | T1–2 = **3**, T3–4 = **4**, T5–6 = **5** (was flat 3). Creates a real spend decision; with CAP_PER_ROUND 7 you often can't drop a fresh T5 without banking. |
| **Interest** | `+1 cap per 2 banked, capped at +2` → `bonus = min(2, cap // 2)`, paid at round resolution. Gives a save-vs-spend curve. |

These two together are the gold curve the genre lives on. Files: `sim.py` (`ARCHETYPES` cost / a tier-price map, `cap_income`), `app.py` (apply interest in `/api/play`).

---

## 3. Tip-off / who starts ✅

- **Rule:** team with higher **total Shooting** starts; on a tie → **weighted coin flip by center (slot-5) Athleticism** (thematic jump ball). Removes the current default-to-YOU.
- **Honest scope:** this is **presentation only** — both teams always get 5 possessions, so it does **not** move win rates. It fixes the feed always printing "You win the tip" on equal teams. File: `sim.py` `play_round` (`you_first`).

---

## 4. Offense distribution fix (problem 1) ✅ direction / ✏️ calibration

- **Issue measured:** one player takes **~68%** of a team's shots (the `ev ** 4` weighting at `sim.py:1124`), so your 4th/5th signings barely express.
- **Fix:** lower the exponent (≈4 → ≈2) and calibrate the shooter-selection weights to **real usage** (top option ~28–32% of shots, not 68%) using your basketball-reference data. Solves "my other signings feel like wallpaper" *and* makes it look like real basketball.
- ✏️ If you have a fuller league-wide stat export, point me at it for the exact usage curve (the 16 cached players I found skew to high-usage stars).

---

## 5. Considered & deliberately kept / not changing ⛔

| Item | Decision | Reason |
|---|---|---|
| **Chemistry** (flat +1 all stats) | **Keep** | Archetype-based (not name-based); the same combo fielded with different players feels different (a passing P&R vs a scoring P&R). Real, simple, incentivized. |
| **Defensive placement** | **Keep man-by-slot** | Deliberate simplicity; readable for users. |
| **Leveling cadence** | **Keep** | Archetype-merge (scoring PG in every tier) triggers at a rate you like. |
| **Loss cap = 3** | **Open/optional** | Flagged: harsh given per-game variance; consider a loss-streak comeback bump or 4 losses *if* games stay swingy after §1. Your call, deferred. |

---

## 6. Supporting data (from your basketball-reference logs)

Aggregated 808 player-games in `PythonProject7\nba_cache`:

| Metric | Real | Sim now | Takeaway |
|---|---|---|---|
| 3P% | 0.343 | 0.37 | base rates already well-calibrated — **don't touch make-rates** |
| 2P% (inside) | 0.570 | layup .64 / mid .41 | ditto |
| Turnover rate | ~12% | ~matches | fine |
| 3PA share | 33% | emergent | check the new sim reproduces it |
| Top-option shot share | ~28–32% | **68%** | the real target for §4 |

**2K attribute menu** (from the Rebuildle project, `PythonProject6`) used to source the hidden-stat names: shot (close/mid/three), layup, dunk, post (hook/fade/control), handle, pass, speed, acceleration, agility, vertical, strength, block, steal, rebound, hustle, IQ.

---

## 7. Retractions / corrections I owe you ↩️

Logged for honesty since the early review was too generous and partly wrong:
- ↩️ **"Confirmed mirror bug" (4.83 vs 4.97):** retracted. `play_round` runs the two halves as independent draws, so it's symmetric by construction; that gap is **sampling noise (~1.6 SE)**, not a bug. What you *noticed* was the cosmetic tip-line default — fixed in §3.
- ↩️ **"Economy is missing":** wrong — the save-vs-spend tension exists (you've started runs short-handed from misspending). §2 deepens it, doesn't add it.
- ↩️ **"Chemistry is a lie of flavor":** overstated — see §5.
- ↩️ **Leveling assumption:** I assumed exact-copy SAP; it's archetype-merge and triggers fine.

---

## 8. Problem 6, recorded (the core of the §1 retune)

In `_evaluate`, a point of OFF only added **0.03** to make-%, so the whole weak→elite scorer gap was +0.27 — **less than a single defender's contest (up to 0.34) or help (up to 0.45).** On any shot, *where the defender is* outweighed *how good the scorer is* → games lean defensive and a 2× roster only won 84%. Diversifying offense (§1) lets each hidden component carry a bigger multiplier without overpowering, which is the real fix.

---

## 9. Suggested build order

1. **§2 + §3** (small, safe, independent) — pricing, interest, tip-off.
2. **§1 schema** — you hand-tune the per-archetype shot-profile table → I regenerate the pool + wire `_evaluate` to read hidden stats + retune the multiplier (§8).
3. **§4** — drop the EV exponent and calibrate usage against your data.
4. Re-run balance + shot-concentration tables; revisit §5 loss-cap only if still swingy.
5. (Pre-existing TODOs, not from this convo: **Finals climax**, ~7 inert abilities, browser QA of the UI.)
</content>
</invoke>
