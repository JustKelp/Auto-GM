"""One-shot generator: builds a ~100-player preset pool and rewrites _POOL_RAW
in sim.py. Deterministic (fixed seed) so every player's identity is stable.

- Worse players sit in Tier 1, better in later tiers (stat budget rises by tier).
- Abilities are reused by real-life prevalence: common skills (catch & shoot,
  rim protector, deadeye) are weighted high; signatures (dream shake, star power,
  limitless) are rare and gated to higher tiers.
- Abilities are archetype-appropriate (a PG won't roll Rim Protector).
"""
import os
import re
import random
import sys

random.seed(20260620)

# archetype -> how its stat budget splits across off/dfn/pas/stl (weights ~1.0)
ARCH_SHAPE = {
    "Scoring PG":    dict(off=.45, dfn=.15, pas=.25, stl=.15),
    "Slashing SF":   dict(off=.40, dfn=.25, pas=.15, stl=.20),
    "Shooting SF":   dict(off=.45, dfn=.25, pas=.15, stl=.15),
    "Rim-Run Big":   dict(off=.40, dfn=.35, pas=.10, stl=.15),
    "Pass-First PG": dict(off=.15, dfn=.20, pas=.45, stl=.20),
    "Lockdown Wing": dict(off=.15, dfn=.40, pas=.15, stl=.30),
    "3&D Wing":      dict(off=.30, dfn=.35, pas=.10, stl=.25),
    "Stretch 4":     dict(off=.40, dfn=.25, pas=.15, stl=.20),
    "Point Forward": dict(off=.30, dfn=.20, pas=.35, stl=.15),
    "Screening Big": dict(off=.20, dfn=.45, pas=.20, stl=.15),
    "Combo Guard":   dict(off=.40, dfn=.20, pas=.25, stl=.15),
    "Sharpshooter":  dict(off=.50, dfn=.15, pas=.15, stl=.20),
    "Two-Way Forward": dict(off=.30, dfn=.35, pas=.15, stl=.20),
    "Stretch Center": dict(off=.40, dfn=.30, pas=.15, stl=.15),
    "Post Scorer":   dict(off=.45, dfn=.30, pas=.15, stl=.10),
    "Defensive Anchor": dict(off=.15, dfn=.50, pas=.15, stl=.20),
}
ARCHS = list(ARCH_SHAPE)  # round-robin order (Scoring PG first so it repeats in T4)

# archetype -> [(ability, prevalence_weight, min_tier)]
ARCH_ABILITIES = {
    "Pass-First PG": [("floor_general", 3, 1), ("tempo_control", 3, 1), ("handles", 2, 1),
                      ("dimer", 2, 2), ("pickpocket", 1, 2), ("on_ball_menace", 1, 1)],
    "Scoring PG":    [("iso_threat", 3, 1), ("handles", 2, 1), ("deadeye", 2, 1),
                      ("soft_touch", 2, 1), ("turnover_prone", 2, 1), ("limitless", 1, 2),
                      ("star_power", 1, 3), ("fan_favorite", 1, 3)],
    "Slashing SF":   [("eurostep", 3, 1), ("iso_threat", 2, 1), ("soft_touch", 2, 1),
                      ("killer_cross", 2, 2), ("turnover_prone", 1, 1)],
    "Shooting SF":   [("catch_shoot", 4, 1), ("deadeye", 3, 1), ("quick_release", 2, 1),
                      ("limitless", 2, 2), ("corner_spec", 1, 1)],
    "Lockdown Wing": [("on_ball_menace", 3, 1), ("pickpocket", 2, 1), ("interceptor", 2, 2),
                      ("lockdown", 3, 2)],
    "3&D Wing":      [("catch_shoot", 3, 1), ("deadeye", 2, 1), ("on_ball_menace", 2, 1),
                      ("quick_release", 2, 1), ("lockdown", 1, 3)],
    "Stretch 4":     [("catch_shoot", 3, 1), ("deadeye", 3, 1), ("soft_touch", 2, 1),
                      ("limitless", 2, 2)],
    "Point Forward": [("floor_general", 3, 1), ("tempo_control", 2, 1), ("iso_threat", 2, 1),
                      ("dimer", 3, 2), ("handles", 1, 1)],
    "Screening Big": [("rim_protector", 4, 1), ("on_ball_menace", 2, 1), ("ball_stopper", 1, 1),
                      ("interceptor", 1, 2), ("dream_shake", 1, 3)],
    "Rim-Run Big":   [("rim_protector", 3, 1), ("lob_threat", 3, 1), ("soft_touch", 2, 1),
                      ("ball_stopper", 2, 1), ("putback", 2, 1), ("dream_shake", 1, 3)],
    "Combo Guard":   [("iso_threat", 3, 1), ("handles", 2, 1), ("deadeye", 2, 1),
                      ("quick_release", 2, 1), ("turnover_prone", 1, 1)],
    "Sharpshooter":  [("catch_shoot", 4, 1), ("deadeye", 3, 1), ("limitless", 2, 2),
                      ("quick_release", 2, 1), ("corner_spec", 2, 1)],
    "Two-Way Forward": [("on_ball_menace", 3, 1), ("eurostep", 2, 1), ("soft_touch", 2, 1),
                      ("pickpocket", 1, 1), ("lockdown", 1, 3)],
    "Stretch Center": [("catch_shoot", 3, 1), ("deadeye", 2, 1), ("rim_protector", 2, 1),
                      ("limitless", 1, 2), ("fan_favorite", 1, 2)],
    "Post Scorer":   [("soft_touch", 3, 1), ("dream_shake", 1, 3), ("ball_stopper", 2, 1),
                      ("iso_threat", 2, 1), ("rim_protector", 1, 1), ("putback", 2, 1)],
    "Defensive Anchor": [("rim_protector", 4, 1), ("on_ball_menace", 2, 1),
                      ("interceptor", 2, 2), ("ball_stopper", 1, 1)],
}

TIER_BUDGET = {1: 16, 2: 20, 3: 24, 4: 28, 5: 32, 6: 36}  # total stat points, +/- noise
TIER_CAP = {1: 7, 2: 9, 3: 11, 4: 12, 5: 13, 6: 14}       # per-stat cap by tier
TIER_COUNTS = {1: 26, 2: 24, 3: 20, 4: 13, 5: 10, 6: 7}   # pyramid -> 100

# marquee names kept for continuity (stats regenerated, ability fixed);
# the legends now anchor the new top tier (6)
FORCED = [
    ("Mike Fletcher", "Pass-First PG", 1, "tempo_control"),
    ("Ace Nakamura", "Scoring PG", 6, "handles"),
    ("Marv Quill", "Scoring PG", 6, "star_power"),
    ("Zeke Abara", "Slashing SF", 6, "eurostep"),
    ("Damon Greer", "Shooting SF", 6, "limitless"),
    ("Trey Salas", "Rim-Run Big", 6, "lob_threat"),
    ("Sol Ingram", "Lockdown Wing", 6, "lockdown"),
    ("Kobi Sefu", "Screening Big", 6, "dream_shake"),
]

# names live in a SEPARATE project (PlayerNames) and are imported here; if that
# project isn't on the path, fall back to a small built-in bank.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PlayerNames"))
    from player_names import FIRST_NAMES as FIRST, LAST_NAMES as LAST, FAMOUS_FULL_NAMES
except Exception:
    FIRST = ["Ace", "Bryce", "Cam", "Dre", "Eli", "Marcus", "Jalen", "Tyler",
             "Jordan", "Cole", "Trey", "Malik", "Devin", "Silas", "Omar"]
    LAST = ["Rivera", "Stone", "Webb", "Ellis", "Frost", "Williams", "Johnson",
            "Davis", "Harris", "Walker", "Reed", "Banks", "Greer", "Pike", "Voss"]
    FAMOUS_FULL_NAMES = set()

used_names = {nm for (nm, _, _, _) in FORCED}
REAL_NAMES = set(FAMOUS_FULL_NAMES)   # never emit a real athlete's full name


def gen_name():
    while True:
        n = f"{random.choice(FIRST)} {random.choice(LAST)}"
        if n not in used_names and n.lower() not in REAL_NAMES:
            used_names.add(n)
            return n


def gen_stats(arch, tier):
    budget = TIER_BUDGET[tier] + random.randint(-2, 2)
    shape = ARCH_SHAPE[arch]
    cap = TIER_CAP[tier]
    return {k: max(2, min(cap, round(shape[k] * budget) + random.randint(-1, 1)))
            for k in ("off", "dfn", "pas", "stl")}


def pick_ability(arch, tier):
    opts = [(a, w) for (a, w, mt) in ARCH_ABILITIES[arch] if mt <= tier]
    return random.choices([a for a, _ in opts], weights=[w for _, w in opts])[0]


entries = []
forced_per_tier = {t: 0 for t in TIER_COUNTS}

# 1) place the forced marquee players exactly where specified
for (nm, arch, tier, ab) in FORCED:
    st = gen_stats(arch, tier)
    entries.append((nm, arch, tier, st["off"], st["dfn"], st["pas"], st["stl"], ab))
    forced_per_tier[tier] += 1

# 2) fill the remaining slots per tier, round-robin over all archetypes so the
#    low tiers cover every position
for tier in (1, 2, 3, 4, 5, 6):
    fill = TIER_COUNTS[tier] - forced_per_tier[tier]
    for i in range(fill):
        arch = ARCHS[i % len(ARCHS)]
        nm, ab = gen_name(), pick_ability(arch, tier)
        st = gen_stats(arch, tier)
        entries.append((nm, arch, tier, st["off"], st["dfn"], st["pas"], st["stl"], ab))

assert len(entries) == 100, len(entries)
# every position must be fieldable from Tier 1 (random_team relies on it)
from collections import defaultdict
ARCH_POS = {  # mirror sim.ARCHETYPE_POSITIONS for the check
    "Pass-First PG": [1], "Scoring PG": [1, 2], "Shooting SF": [2, 3],
    "Lockdown Wing": [2, 3], "3&D Wing": [2, 3], "Slashing SF": [3, 4],
    "Point Forward": [3, 4], "Stretch 4": [4, 5], "Screening Big": [5],
    "Rim-Run Big": [4, 5], "Combo Guard": [1, 2], "Sharpshooter": [2, 3],
    "Two-Way Forward": [3, 4], "Stretch Center": [4, 5], "Post Scorer": [4, 5],
    "Defensive Anchor": [5],
}
t1pos = set()
for e in entries:
    if e[2] == 1:
        t1pos.update(ARCH_POS[e[1]])
assert t1pos >= {1, 2, 3, 4, 5}, f"tier1 missing positions: {{1,2,3,4,5}} - {t1pos}"

# build the literal
lines = ["_POOL_RAW = ["]
cur = None
for e in sorted(entries, key=lambda x: (x[2], ARCHS.index(x[1]), x[0])):
    if e[2] != cur:
        cur = e[2]
        lines.append(f"    # --- Tier {cur} ---")
    lines.append(f"    ({e[0]!r}, {e[1]!r}, {e[2]}, {e[3]}, {e[4]}, "
                 f"{e[5]}, {e[6]}, {e[7]!r}),")
lines.append("]")
literal = "\n".join(lines)

with open("sim.py", encoding="utf-8") as f:
    src = f.read()
src = re.sub(r"_POOL_RAW = \[.*?\n\]", lambda m: literal, src, flags=re.S, count=1)
with open("sim.py", "w", encoding="utf-8") as f:
    f.write(src)
print(f"rewrote _POOL_RAW with {len(entries)} players")
