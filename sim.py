"""
Basketball Auto-Battler — sim core (importable, structured output).

This is the rules authority. The Flask app (app.py) is a thin host: it passes
run state in and out of these functions and the browser is a pure view. No
printing here — every possession returns structured events the frontend can
animate. All tuning knobs live at the top; the numbers will all change.

POSITION MATTERS. Players are placed anywhere on the half-court (coords 0-100,
basket at the top center). A player's distance to the basket sets the shot
type; their archetype's preferred zone gives a fit bonus/penalty; defenders
play man-to-man on the line between their man and the basket; clustering lets
defenders help (lower make %); passing risk scales with pass distance and
defenders in the lane.

No generative AI and no external assets are involved anywhere in this game —
the sim is plain deterministic game logic.
"""

import copy
import math
import random
import uuid

# ---------------------------------------------------------------------------
# TUNABLE KNOBS
# ---------------------------------------------------------------------------
POSSESSIONS_PER_SIDE = 5
FINALS_POSSESSIONS = 10   # the Finals runs twice as long — less variance, better team wins
LINEUP_SIZE = 5
SHOP_SIZE = 5
STARTING_CAP = 17
CAP_PER_ROUND = 7
REROLL_COST = 1
WINS_TO_FINISH = 12       # wins that clinch a Finals berth (championship run)
LOSSES_TO_BUST = 4        # losses that eliminate you

# Court / geometry (coords are 0-100 on both axes; basket near the top baseline)
BASKET = (50.0, 7.0)
LAYUP_MAX = 16.0          # distance < this = at the rim
MID_MAX = 40.0           # distance < this = midrange, else three (matches arc)
STANDOFF = 7.0           # how far a defender sits off his man toward the basket
CONTEST_RANGE = 24.0     # beyond this, a defender contests nothing
CONTEST_SCALE = 0.34     # max make-% an on-ball defender removes
HELP_RANGE = 20.0        # a help defender this close to the shooter chips in
HELP_PER = 0.075         # make-% removed per nearby help defender (bunching hurts)
HELP_CAP = 0.45          # every defender in the area piles on (high cap)
LANE_RANGE = 8.0         # a defender this close to the pass line threatens it
MIN_SEP = 11.0           # offensive players closer than this overlap (illegal)
SETUP_STEP = 8.0         # drift toward your role spot as the play develops
SHOT_STEP = 7.0          # the shooter's move to GET the shot (drive in / step out)
PASS_STEP = 5.0          # the passer steps into the play to deliver it
# how many passes a possession swings before the shot (when it isn't a self-shot):
# 2 is the norm, 1 fairly common, 3 rare. Capped at 3 by the available players.
PASS_WEIGHTS = {1: 0.28, 2: 0.54, 3: 0.18}
MOVE_STEP = 5.0          # how far players drift each beat DURING the play (live motion)
# Rebounding (hidden stat). Real NBA offensive-rebound rate is ~26%; this is a
# turn game, so we sit UNDER that — second chances are uncommon.
OREB_BASE = 0.12         # offensive-rebound chance at even rebounding
OREB_SWING = 0.40        # how much a rebounding edge shifts that chance
OREB_CAP = 0.22          # hard ceiling on offensive-rebound chance
PUTBACK_BONUS = 0.06     # extra OREB chance if a Putback player is on the floor
FIT_BONUS = 0.15         # shooting from your archetype's preferred zone
DEEP_PENALTY = 0.004     # make-% lost per unit of distance beyond the arc
# zone-specific scoring: make-% rises with the player's effective rating AT THAT
# zone (Shooting for jumpers, Athleticism/finishing at the rim). A bigger lever
# than the old flat offense term, because a player is only elite in his own zone.
ZONE_COEFF = 0.05
SCORE_REF = 6.0          # a neutral scoring rating (no bonus/penalty)
OPEN_BIAS = 0.5          # how strongly the offense funnels to an open (low-pressure) look
UNGUARDED_BONUS = 0.8    # extra pull toward a player with no man defender at all
PRESSURE_NORM = 0.4      # pressure level at which the open bonus fully fades out
DOUBLE_OFFSET = 4.0      # how far a doubling help defender sits off the player he traps

# Shot base make-rates before ratings/fit/defense
BASE_LAYUP = 0.64
BASE_MIDRANGE = 0.41
BASE_THREE = 0.35       # ~ real NBA league 3P% (your data: .343)

# ---------------------------------------------------------------------------
# ARCHETYPES — each carries a behavior policy + a preferred shot, not just stats
# ---------------------------------------------------------------------------
ARCHETYPES = {
    "Pass-First PG": dict(cost=3, spacing=1, behavior="distribute", abbr="PG",
                          base=dict(off=4, dfn=4, pas=8, stl=5)),
    "Scoring PG":    dict(cost=3, spacing=1, behavior="pull_up", abbr="PG",
                          base=dict(off=6, dfn=3, pas=5, stl=4)),
    "Slashing SF":   dict(cost=3, spacing=0, behavior="cut", abbr="SF",
                          base=dict(off=6, dfn=5, pas=4, stl=4)),
    "Shooting SF":   dict(cost=3, spacing=2, behavior="spot_up", abbr="SF",
                          base=dict(off=6, dfn=4, pas=3, stl=3)),
    "Stretch 4":     dict(cost=3, spacing=2, behavior="spot_up", abbr="PF",
                          base=dict(off=5, dfn=4, pas=3, stl=2)),
    "Screening Big": dict(cost=3, spacing=0, behavior="screen", abbr="C",
                          base=dict(off=4, dfn=7, pas=4, stl=2)),
    "Rim-Run Big":   dict(cost=3, spacing=0, behavior="roll", abbr="C",
                          base=dict(off=6, dfn=6, pas=2, stl=2)),
    "Lockdown Wing": dict(cost=3, spacing=1, behavior="spot_up", abbr="WG",
                          base=dict(off=4, dfn=8, pas=3, stl=7)),
    "3&D Wing":      dict(cost=3, spacing=2, behavior="spot_up", abbr="WG",
                          base=dict(off=6, dfn=6, pas=3, stl=5)),
    "Point Forward": dict(cost=3, spacing=1, behavior="distribute", abbr="SF",
                          base=dict(off=6, dfn=5, pas=7, stl=4)),
    "Combo Guard":   dict(cost=3, spacing=1, behavior="pull_up", abbr="CG",
                          base=dict(off=6, dfn=4, pas=5, stl=4)),
    "Sharpshooter":  dict(cost=3, spacing=2, behavior="spot_up", abbr="SG",
                          base=dict(off=7, dfn=3, pas=3, stl=3)),
    "Two-Way Forward": dict(cost=3, spacing=0, behavior="cut", abbr="SF",
                          base=dict(off=5, dfn=6, pas=4, stl=5)),
    "Stretch Center": dict(cost=3, spacing=2, behavior="spot_up", abbr="C",
                          base=dict(off=6, dfn=5, pas=3, stl=2)),
    "Post Scorer":   dict(cost=3, spacing=0, behavior="pull_up", abbr="C",
                          base=dict(off=7, dfn=5, pas=3, stl=2)),
    "Defensive Anchor": dict(cost=3, spacing=0, behavior="screen", abbr="C",
                          base=dict(off=3, dfn=8, pas=3, stl=3)),
}

# preferred shot per behavior (where this archetype is most effective)
PREFERRED_SHOT = {
    "distribute": None,       # playmaker, not a primary scorer
    "pull_up": "midrange",
    "cut": "layup",
    "roll": "layup",
    "screen": "layup",
    "spot_up": "three",
}

# Roster positions (1-5). Each archetype can fill one or two adjacent slots,
# so a free agent is draggable onto those slots in the position bar.
POSITION_LABELS = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}
ARCHETYPE_POSITIONS = {
    "Pass-First PG": [1],
    "Scoring PG":    [1, 2],
    "Shooting SF":   [2, 3],
    "Lockdown Wing": [2, 3],
    "3&D Wing":      [2, 3],
    "Slashing SF":   [3, 4],
    "Point Forward": [3, 4],
    "Stretch 4":     [4, 5],
    "Screening Big": [5],
    "Rim-Run Big":   [4, 5],
    "Combo Guard":   [1, 2],
    "Sharpshooter":  [2, 3],
    "Two-Way Forward": [3, 4],
    "Stretch Center": [4, 5],
    "Post Scorer":   [4, 5],
    "Defensive Anchor": [5],
}

# Rigid positioning: each archetype may stand in at most TWO spots.
# [primary (most effective), secondary (farther from the basket = less effective)]
ARCHETYPE_ANCHORS = {
    "Pass-First PG": [(50, 66), (50, 82)],
    "Scoring PG":    [(42, 38), (52, 62)],
    "Slashing SF":   [(44, 19), (36, 36)],
    "Shooting SF":   [(78, 46), (84, 62)],
    "Stretch 4":     [(22, 46), (16, 62)],
    "Screening Big": [(56, 19), (60, 36)],
    "Rim-Run Big":   [(50, 17), (42, 34)],
    "Lockdown Wing": [(14, 30), (12, 50)],
    "3&D Wing":      [(76, 50), (82, 64)],
    "Point Forward": [(40, 30), (34, 46)],
    "Combo Guard":   [(46, 40), (58, 58)],
    "Sharpshooter":  [(72, 42), (80, 58)],
    "Two-Way Forward": [(40, 22), (32, 40)],
    "Stretch Center": [(28, 42), (22, 58)],
    "Post Scorer":   [(58, 20), (64, 34)],
    "Defensive Anchor": [(50, 20), (46, 34)],
}

# Background tendencies by archetype (not shown as stats): how often a player
# starts with the ball (handle), takes the shot (shoot multiplier on look EV),
# and is used as a passer in the chain (pass weight). Pass-first PGs start with
# the ball most; point forwards initiate sometimes; bigs rarely.
ARCHETYPE_TENDENCY = {
    "Pass-First PG":   {"handle": 14, "shoot": 0.55, "pass": 14},
    "Point Forward":   {"handle": 9,  "shoot": 0.95, "pass": 11},
    "Scoring PG":      {"handle": 7,  "shoot": 1.30, "pass": 6},
    "Combo Guard":     {"handle": 8,  "shoot": 1.25, "pass": 6},
    "Slashing SF":     {"handle": 3,  "shoot": 1.20, "pass": 4},
    "Two-Way Forward": {"handle": 3,  "shoot": 0.95, "pass": 4},
    "Shooting SF":     {"handle": 2,  "shoot": 1.30, "pass": 3},
    "Sharpshooter":    {"handle": 2,  "shoot": 1.40, "pass": 2},
    "3&D Wing":        {"handle": 2,  "shoot": 1.00, "pass": 3},
    "Lockdown Wing":   {"handle": 2,  "shoot": 0.70, "pass": 3},
    "Stretch 4":       {"handle": 2,  "shoot": 1.10, "pass": 3},
    "Stretch Center":  {"handle": 1,  "shoot": 1.10, "pass": 2},
    "Rim-Run Big":     {"handle": 1,  "shoot": 1.00, "pass": 2},
    "Post Scorer":     {"handle": 1,  "shoot": 1.20, "pass": 2},
    "Screening Big":   {"handle": 1,  "shoot": 0.60, "pass": 3},
    "Defensive Anchor": {"handle": 1, "shoot": 0.50, "pass": 2},
}


def _tend(p, key):
    return ARCHETYPE_TENDENCY.get(p["archetype"], {}).get(key, 1.0)


# Hidden rebounding rating by archetype (bigs crash the glass, guards don't).
# Not shown as a stat — it quietly strengthens defense (securing the board) and
# occasionally earns the offense a second-chance putback.
ARCHETYPE_REB = {
    "Pass-First PG": 3, "Scoring PG": 3, "Combo Guard": 3,
    "Shooting SF": 4, "Sharpshooter": 4, "Point Forward": 5,
    "Lockdown Wing": 5, "3&D Wing": 5, "Slashing SF": 5,
    "Two-Way Forward": 6, "Stretch 4": 7, "Stretch Center": 7,
    "Rim-Run Big": 8, "Post Scorer": 8, "Screening Big": 9, "Defensive Anchor": 9,
}

# ---------------------------------------------------------------------------
# STAT MODEL — the player shows FOUR ratings: Shooting (sht), Defense (dfn),
# Playmaking (plm), Athleticism (ath). Behind them are a few hidden stats the
# sim actually reads, so the same simple number means different things by
# archetype. The big consequence: SCORING is split — jump scoring comes from
# `sht` (mid/three), rim scoring comes from `ath` (finishing). So a post big
# reads high ATH / low SHT and dominates inside but bricks threes automatically;
# a sharpshooter reads the reverse. SHOT_PROFILE is the source of truth.
# ---------------------------------------------------------------------------
# (rim, mid, three) scoring effectiveness per archetype
SHOT_PROFILE = {
    "Pass-First PG":   (0.5, 0.6, 0.5),
    "Scoring PG":      (0.5, 1.0, 0.6),
    "Slashing SF":     (1.0, 0.4, 0.2),
    "Shooting SF":     (0.3, 0.5, 1.0),
    "Stretch 4":       (0.2, 0.4, 1.0),
    "Screening Big":   (1.0, 0.2, 0.05),
    "Rim-Run Big":     (1.0, 0.2, 0.0),
    "Lockdown Wing":   (0.4, 0.5, 0.7),
    "3&D Wing":        (0.4, 0.4, 1.0),
    "Point Forward":   (0.6, 0.6, 0.5),
    "Combo Guard":     (0.5, 0.9, 0.7),
    "Sharpshooter":    (0.2, 0.4, 0.95),
    "Two-Way Forward": (0.9, 0.4, 0.3),
    "Stretch Center":  (0.5, 0.4, 1.0),
    "Post Scorer":     (1.0, 0.5, 0.05),
    "Defensive Anchor": (0.9, 0.2, 0.05),
}

# How a Defense rating splits into on-ball pressure / rim protection / lane-jumping
# steals, and how a Playmaking rating splits into handle / passing / vision.
# (steal_w high = ball-hawk guards/wings; block_w high = bigs.)
ARCHETYPE_DEF_SPLIT = {   # (on_ball, block, steal)
    "Pass-First PG":   (0.6, 0.1, 0.7), "Scoring PG": (0.6, 0.1, 0.6),
    "Slashing SF":     (0.7, 0.2, 0.6), "Shooting SF": (0.7, 0.2, 0.5),
    "Stretch 4":       (0.5, 0.5, 0.4), "Screening Big": (0.4, 0.9, 0.2),
    "Rim-Run Big":     (0.4, 0.9, 0.2), "Lockdown Wing": (0.9, 0.2, 0.8),
    "3&D Wing":        (0.8, 0.3, 0.7), "Point Forward": (0.7, 0.3, 0.6),
    "Combo Guard":     (0.6, 0.1, 0.6), "Sharpshooter": (0.6, 0.1, 0.5),
    "Two-Way Forward": (0.8, 0.4, 0.7), "Stretch Center": (0.5, 0.7, 0.3),
    "Post Scorer":     (0.4, 0.8, 0.2), "Defensive Anchor": (0.5, 1.0, 0.3),
}


def _hidden_stats(archetype, sht, dfn, plm, ath):
    """Derive the back-end stats the sim reads from the four shown ratings."""
    rim_w, mid_w, three_w = SHOT_PROFILE.get(archetype, (0.6, 0.6, 0.6))
    onb_w, blk_w, stl_w = ARCHETYPE_DEF_SPLIT.get(archetype, (0.7, 0.4, 0.5))
    size = ARCHETYPE_REB.get(archetype, 4)
    quick = _clamp(11 - size, 2, 9)            # guards quick, bigs not
    return {
        # scoring (zone-specific effectiveness)
        "s_mid": sht * mid_w,
        "s_three": sht * three_w,
        "s_rim": ath * rim_w,                  # finishing
        # defense
        "d_onball": dfn * onb_w,
        "d_block": dfn * blk_w,
        "d_steal": dfn * stl_w,
        # playmaking
        "p_handle": plm * 0.9 + quick * 0.1,
        "p_pass": plm,
        "p_vision": plm * 0.8,
        # athletic
        "quickness": quick,
    }


def _refresh_hidden(p):
    """Re-derive the back-end stats after the four shown ratings change
    (leveling, chemistry)."""
    p.update(_hidden_stats(p["archetype"], p["sht"], p["dfn"], p["plm"], p["ath"]))


# ---------------------------------------------------------------------------
# ABILITIES — one per player (SAP-style). `active` ones are wired into the sim
# below; the rest are declared data (assigned to players, effects to come, as
# the sim grows rebounds / fast breaks / fatigue / etc.). `cat` groups them.
# ---------------------------------------------------------------------------
ABILITIES = {
    # --- shooting (ACTIVE) --------------------------------------------------
    "deadeye":        dict(name="Deadeye", cat="shooting", active=True,
                           desc="Loses less accuracy when his jumper is contested."),
    "limitless":      dict(name="Limitless Range", cat="shooting", active=True,
                           desc="No accuracy penalty on deep threes."),
    "catch_shoot":    dict(name="Catch & Shoot", cat="shooting", active=True,
                           desc="Bonus accuracy on a shot taken right off a pass."),
    "heat_check":     dict(name="Heat Check", cat="shooting", active=False,
                           desc="After a make, his next shot gets a one-time boost."),
    "quick_release":  dict(name="Quick Release", cat="shooting", active=True,
                           desc="Hard to contest; help defense arrives too late."),
    "corner_spec":    dict(name="Corner Specialist", cat="shooting", active=False,
                           desc="Shoots better from the corners specifically."),
    # --- finishing (ACTIVE) -------------------------------------------------
    "dream_shake":    dict(name="Dream Shake", cat="finishing", active=True,
                           desc="Scores a rim-quality shot from midrange."),
    "eurostep":       dict(name="Eurostep", cat="finishing", active=True,
                           desc="Finishes at the rim through help defense."),
    "lob_threat":     dict(name="Lob Threat", cat="finishing", active=True,
                           desc="A pass to him at the rim is a near-automatic finish."),
    "putback":        dict(name="Putback", cat="finishing", active=True,
                           desc="Better chance to grab and score the team's own miss."),
    "soft_touch":     dict(name="Soft Touch", cat="finishing", active=True,
                           desc="Better on floaters and runners in the midrange."),
    # --- playmaking (ACTIVE) ------------------------------------------------
    "dimer":          dict(name="Dimer", cat="playmaking", active=True,
                           desc="Teammates shoot better on shots off his pass."),
    "floor_general":  dict(name="Floor General", cat="playmaking", active=True,
                           desc="Raises every teammate's offense a touch."),
    "tempo_control":  dict(name="Tempo Control", cat="playmaking", active=True,
                           desc="Lowers his team's turnover risk."),
    # --- ball-handling (ACTIVE) --------------------------------------------
    "killer_cross":   dict(name="Killer Crossover", cat="handling", active=True,
                           desc="Breaks down the top help defender on his drive."),
    "handles":        dict(name="Handles for Days", cat="handling", active=True,
                           desc="Very low turnover risk when he initiates."),
    "iso_threat":     dict(name="Iso Threat", cat="handling", active=True,
                           desc="Better shot quality when he creates his own look."),
    # --- defense on-ball (ACTIVE) ------------------------------------------
    "on_ball_menace": dict(name="On-Ball Menace", cat="defense", active=True,
                           desc="His man shoots worse even from a distance."),
    "lockdown":       dict(name="Lockdown", cat="defense", active=True,
                           desc="Heavily reduces his matchup's scoring."),
    "rim_protector":  dict(name="Rim Protector", cat="defense", active=True,
                           desc="Suppresses all shots near the basket."),
    "shot_blocker":   dict(name="Shot Blocker", cat="defense", active=False,
                           desc="Chance to swat his man's rim attempt."),
    # --- defense off-ball / steals (ACTIVE) --------------------------------
    "pickpocket":     dict(name="Pickpocket", cat="defense", active=True,
                           desc="High steal chance in his man's passing lane."),
    "interceptor":    dict(name="Interceptor", cat="defense", active=True,
                           desc="Jumps any passing lane near him, not just his man's."),
    # --- meta / economy -----------------------------------------------------
    "star_power":     dict(name="Star Power", cat="meta", active=True,
                           desc="Grants extra cap space each round while rostered."),
    "fan_favorite":   dict(name="Fan Favorite", cat="meta", active=True,
                           desc="Worth more on release (+2 cap back)."),
    "mentor":         dict(name="Mentor", cat="meta", active=False,
                           desc="An adjacent low-level teammate levels faster."),
    # --- negative / drawback ------------------------------------------------
    "turnover_prone": dict(name="Turnover Prone", cat="negative", active=True,
                           desc="Great scorer, but higher turnover risk."),
    "ball_stopper":   dict(name="Ball Stopper", cat="negative", active=True,
                           desc="Scores well but lowers teammates' offense."),
    "streaky":        dict(name="Streaky", cat="negative", active=False,
                           desc="Bigger swings — hotter and colder than his rating."),
}


def ability_name(aid):
    a = ABILITIES.get(aid)
    return a["name"] if a else ""


# ---------------------------------------------------------------------------
# CHEMISTRY — TFT-style archetype synergies. Field the listed archetypes
# together (one distinct player per slot) and each member gets +1 to ALL stats
# per active combo (stacking, capped by CHEM_CAP). Duos = 2 archetypes, trios = 3.
# ---------------------------------------------------------------------------
CHEM_CAP = 2  # most stacked chemistry bonus a single player can carry

CHEMISTRY = [
    # --- duos ---------------------------------------------------------------
    dict(name="Pick & Roll", kind="duo",
         archetypes=["Pass-First PG", "Rim-Run Big"],
         desc="A pass-first PG and a rim-runner — lethal off the screen."),
    dict(name="Inside-Outside", kind="duo",
         archetypes=["Scoring PG", "Rim-Run Big"],
         desc="A scoring guard and a dominant big stretch the defense."),
    dict(name="Splash Brothers", kind="duo",
         archetypes=["Shooting SF", "Stretch 4"],
         desc="Two deadly shooters — the floor is too spread to help."),
    dict(name="Twin Towers", kind="duo",
         archetypes=["Screening Big", "Rim-Run Big"],
         desc="Two bigs wall off the rim and own the glass."),
    dict(name="Lockdown Backcourt", kind="duo",
         archetypes=["Lockdown Wing", "3&D Wing"],
         desc="Two wing stoppers smother the perimeter."),
    dict(name="Veteran Backcourt", kind="duo",
         archetypes=["Pass-First PG", "Scoring PG"],
         desc="A true point and a scoring guard share the load."),
    dict(name="Sniper Corps", kind="duo",
         archetypes=["Sharpshooter", "Stretch Center"],
         desc="Two long-range bombers warp the defense."),
    dict(name="Microwave Backcourt", kind="duo",
         archetypes=["Combo Guard", "Sharpshooter"],
         desc="Instant-offense scoring backcourt."),
    dict(name="Bruiser Bigs", kind="duo",
         archetypes=["Post Scorer", "Defensive Anchor"],
         desc="A back-to-basket scorer and a rim wall."),
    # --- trios --------------------------------------------------------------
    dict(name="Three-Level Attack", kind="trio",
         archetypes=["Slashing SF", "Shooting SF", "Rim-Run Big"],
         desc="Slasher, shooter and rim-runner cover every scoring zone."),
    dict(name="Position-less Wings", kind="trio",
         archetypes=["Point Forward", "Lockdown Wing", "3&D Wing"],
         desc="Three switchable wings — versatile on both ends."),
    dict(name="Title Core", kind="trio",
         archetypes=["Pass-First PG", "Shooting SF", "Screening Big"],
         desc="Floor general, sharpshooter and a defensive anchor."),
    dict(name="Switch Everything", kind="trio",
         archetypes=["Two-Way Forward", "Lockdown Wing", "Defensive Anchor"],
         desc="Three stoppers who switch 1 through 5."),
]


def _match_combo(team, req_archs):
    """Greedily assign a DISTINCT player to each required archetype. Returns the
    member ids if the whole combo is covered, else None."""
    used, members = set(), []
    for a in req_archs:
        pick = next((p for p in team
                     if p["archetype"] == a and p["id"] not in used), None)
        if pick is None:
            return None
        used.add(pick["id"])
        members.append(pick["id"])
    return members


def active_chemistry(team):
    """Which archetype combos are live in this team. Returns
    (active: [{name,kind,desc,archetypes,members}], bonus: {player_id: +stat})."""
    active = []
    bonus = {p["id"]: 0 for p in team}
    for combo in CHEMISTRY:
        members = _match_combo(team, combo["archetypes"])
        if members:
            active.append({**combo, "members": members})
            for mid in members:
                bonus[mid] = min(CHEM_CAP, bonus[mid] + 1)
    return active, bonus


def _apply_chemistry(team):
    """Bake active-chemistry stat bonuses into the team (mutates). Returns the
    active-combo list (for display). Call only on throwaway copies."""
    active, bonus = active_chemistry(team)
    for p in team:
        b = bonus.get(p["id"], 0)
        if b:
            for k in ("sht", "dfn", "plm", "ath"):
                p[k] = min(STAT_CAP, p[k] + b)
            _refresh_hidden(p)
    return active


# ---------------------------------------------------------------------------
# TIERS — players unlock in free agency as you rack up wins. Lower tiers carry
# weaker archetypes and stats; climbing the ladder unlocks new archetypes and
# stronger players. Price is flat across tiers for now (cost lives in ARCHETYPES).
# ---------------------------------------------------------------------------
MAX_TIER = 6
# tiers unlock by GAMES PLAYED (wins + losses), not wins — everyone progresses
TIER_UNLOCK_GAMES = {1: 0, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10}

# Price by tier (was a flat 3). Higher tiers cost more, so signing a legend is a
# real spend decision you may have to bank toward. Overrides the archetype cost.
TIER_PRICE = {1: 3, 2: 3, 3: 4, 4: 4, 5: 5, 6: 5}


def tier_price(tier):
    return TIER_PRICE.get(tier, 3)


def interest(cap):
    """Banking reward: +1 cap for every 2 saved, capped at +2 (TFT-style)."""
    return min(2, cap // 2)


def unlocked_tiers(games):
    """Tiers available after this many games played."""
    return [t for t, need in TIER_UNLOCK_GAMES.items() if games >= need]


def next_unlock(games):
    """(tier, games_needed) of the next tier to unlock, or None if all unlocked."""
    for t in range(1, MAX_TIER + 1):
        if games < TIER_UNLOCK_GAMES[t]:
            return t, TIER_UNLOCK_GAMES[t]
    return None


def tier_ceiling_for_round(round_no):
    """How strong a random opponent may be: the top tier it can field."""
    if round_no <= 2:
        return 1
    if round_no <= 4:
        return 2
    if round_no <= 6:
        return 3
    if round_no <= 8:
        return 4
    if round_no <= 10:
        return 5
    return 6


# Preset, PERSISTENT player pool. A name always maps to the same archetype and
# the same base stats every run, so reputations stick ("I rode Mike Fletcher to
# 10 wins, he averaged 30"). These base stats are the player's identity; signing
# and merging (level_up) are what improve them within a run.
#   (name, archetype, tier, off, dfn, pas, stl, ability)
_POOL_RAW = [
    # --- Tier 1 ---
    ('Grant Miller', 'Scoring PG', 1, 7, 2, 5, 3, 'iso_threat'),
    ('Jabari Ward', 'Scoring PG', 1, 5, 2, 3, 2, 'iso_threat'),
    ('Jeremiah Hamilton', 'Slashing SF', 1, 4, 4, 3, 6, 'iso_threat'),
    ('Rome Allen', 'Slashing SF', 1, 3, 4, 2, 5, 'eurostep'),
    ('Isaiah Mathis', 'Shooting SF', 1, 7, 4, 3, 2, 'quick_release'),
    ('Jose Booker', 'Shooting SF', 1, 7, 3, 2, 2, 'catch_shoot'),
    ('Carson Reyes', 'Rim-Run Big', 1, 2, 5, 2, 8, 'ball_stopper'),
    ('Ivan Clark', 'Rim-Run Big', 1, 2, 5, 2, 7, 'ball_stopper'),
    ('Jackson Pike', 'Pass-First PG', 1, 3, 4, 7, 2, 'tempo_control'),
    ('Mike Fletcher', 'Pass-First PG', 1, 4, 3, 7, 2, 'tempo_control'),
    ('Zeke Edwards', 'Pass-First PG', 1, 4, 4, 7, 2, 'floor_general'),
    ('Damian Norman', 'Lockdown Wing', 1, 3, 7, 2, 2, 'on_ball_menace'),
    ('Devin Dawson', 'Lockdown Wing', 1, 3, 5, 2, 2, 'on_ball_menace'),
    ('Corey Booker', '3&D Wing', 1, 5, 6, 2, 3, 'deadeye'),
    ('Silas Rice', '3&D Wing', 1, 5, 6, 2, 3, 'deadeye'),
    ('Miles Patterson', 'Stretch 4', 1, 6, 3, 2, 3, 'deadeye'),
    ('Tyler Warner', 'Stretch 4', 1, 7, 4, 2, 3, 'catch_shoot'),
    ('Vince Ortega', 'Point Forward', 1, 4, 4, 5, 3, 'iso_threat'),
    ('Will Dawson', 'Point Forward', 1, 5, 4, 4, 4, 'tempo_control'),
    ('Jax Collins', 'Screening Big', 1, 2, 7, 2, 5, 'on_ball_menace'),
    ('Lamar Hamilton', 'Combo Guard', 1, 6, 2, 3, 2, 'deadeye'),
    ('Jax Davis', 'Sharpshooter', 1, 8, 2, 4, 2, 'catch_shoot'),
    ('Zeke Williams', 'Two-Way Forward', 1, 4, 6, 2, 5, 'on_ball_menace'),
    ('Lamar Payne', 'Stretch Center', 1, 6, 4, 2, 4, 'catch_shoot'),
    ('Javon Tate', 'Post Scorer', 1, 4, 4, 3, 8, 'ball_stopper'),
    ('Jeremiah Mensah', 'Defensive Anchor', 1, 2, 7, 3, 5, 'on_ball_menace'),
    # --- Tier 2 ---
    ('Jackson Murray', 'Scoring PG', 2, 8, 3, 4, 3, 'deadeye'),
    ('Ryan Mensah', 'Scoring PG', 2, 8, 4, 3, 3, 'turnover_prone'),
    ('Bryce Cruz', 'Slashing SF', 2, 5, 3, 4, 7, 'eurostep'),
    ('Desmond Mraz', 'Slashing SF', 2, 5, 5, 2, 7, 'killer_cross'),
    ('Corey Tran', 'Shooting SF', 2, 8, 6, 4, 2, 'catch_shoot'),
    ('Theo Murray', 'Shooting SF', 2, 9, 5, 4, 3, 'deadeye'),
    ('Ben Scott', 'Rim-Run Big', 2, 3, 6, 2, 10, 'rim_protector'),
    ('Jordan Butler', 'Rim-Run Big', 2, 3, 6, 3, 10, 'putback'),
    ('Cole Wells', 'Pass-First PG', 2, 4, 5, 9, 2, 'floor_general'),
    ('Cooper Harris', 'Pass-First PG', 2, 4, 3, 9, 2, 'handles'),
    ('Ryan Voss', 'Lockdown Wing', 2, 4, 7, 2, 3, 'on_ball_menace'),
    ('Ty Marsh', 'Lockdown Wing', 2, 3, 8, 3, 2, 'lockdown'),
    ('Isaac Hughes', '3&D Wing', 2, 6, 6, 2, 3, 'quick_release'),
    ('Kevin Boyd', '3&D Wing', 2, 5, 5, 2, 3, 'on_ball_menace'),
    ('Jason Mraz', 'Stretch 4', 2, 8, 5, 4, 3, 'limitless'),
    ('Nash Boyd', 'Stretch 4', 2, 9, 6, 4, 3, 'catch_shoot'),
    ('Quincy Rivera', 'Point Forward', 2, 6, 3, 6, 4, 'floor_general'),
    ('Grant Vance', 'Screening Big', 2, 2, 9, 3, 6, 'rim_protector'),
    ('Mason Nelson', 'Combo Guard', 2, 8, 5, 5, 3, 'handles'),
    ('Zeke Dawson', 'Sharpshooter', 2, 9, 4, 4, 2, 'catch_shoot'),
    ('Quincy Johnson', 'Two-Way Forward', 2, 4, 6, 4, 5, 'eurostep'),
    ('Mike Perry', 'Stretch Center', 2, 7, 5, 2, 4, 'fan_favorite'),
    ('Malik Jenkins', 'Post Scorer', 2, 5, 5, 4, 9, 'putback'),
    ('Trent Fields', 'Defensive Anchor', 2, 2, 8, 3, 5, 'rim_protector'),
    # --- Tier 3 ---
    ('Grant Whitlock', 'Scoring PG', 3, 10, 3, 6, 4, 'soft_touch'),
    ('Isaiah Fox', 'Scoring PG', 3, 10, 2, 6, 4, 'iso_threat'),
    ('Bradley Ingram', 'Slashing SF', 3, 5, 5, 3, 8, 'eurostep'),
    ('Davon Fox', 'Slashing SF', 3, 6, 6, 4, 9, 'killer_cross'),
    ('Brock Thomas', 'Shooting SF', 3, 11, 7, 3, 3, 'catch_shoot'),
    ('Ezra Dixon', 'Shooting SF', 3, 9, 7, 3, 3, 'quick_release'),
    ('Jaylen Robinson', 'Rim-Run Big', 3, 3, 7, 2, 11, 'soft_touch'),
    ('Marquise Murphy', 'Rim-Run Big', 3, 3, 8, 3, 10, 'rim_protector'),
    ('Ty Dawson', 'Pass-First PG', 3, 4, 4, 10, 2, 'dimer'),
    ('Kai Campbell', 'Lockdown Wing', 3, 5, 9, 4, 3, 'on_ball_menace'),
    ('Damon Griffin', '3&D Wing', 3, 7, 10, 3, 4, 'catch_shoot'),
    ('Jalen Walker', 'Stretch 4', 3, 10, 7, 4, 3, 'deadeye'),
    ('Mario Salas', 'Point Forward', 3, 7, 6, 8, 5, 'tempo_control'),
    ('Jeremiah Haas', 'Screening Big', 3, 2, 9, 5, 7, 'on_ball_menace'),
    ('Trey Lindqvist', 'Combo Guard', 3, 8, 6, 5, 3, 'deadeye'),
    ('Jackson Freeman', 'Sharpshooter', 3, 11, 2, 2, 2, 'catch_shoot'),
    ('Eli Patterson', 'Two-Way Forward', 3, 5, 10, 5, 6, 'on_ball_menace'),
    ('Mario West', 'Stretch Center', 3, 9, 7, 3, 5, 'rim_protector'),
    ('Quentin Cunningham', 'Post Scorer', 3, 5, 8, 4, 10, 'iso_threat'),
    ('Chase Webb', 'Defensive Anchor', 3, 2, 11, 4, 6, 'rim_protector'),
    # --- Tier 4 ---
    ('Jett Clark', 'Scoring PG', 4, 10, 5, 7, 4, 'turnover_prone'),
    ('Grant Underwood', 'Slashing SF', 4, 5, 7, 3, 8, 'eurostep'),
    ('Hollis Allen', 'Shooting SF', 4, 12, 6, 3, 3, 'limitless'),
    ('Grant Love', 'Rim-Run Big', 4, 4, 11, 4, 13, 'soft_touch'),
    ('Damian Mack', 'Pass-First PG', 4, 4, 6, 12, 2, 'tempo_control'),
    ('Myles Hall', 'Lockdown Wing', 4, 4, 11, 3, 3, 'on_ball_menace'),
    ('Kareem Warner', '3&D Wing', 4, 8, 11, 3, 4, 'on_ball_menace'),
    ('Dominic Turner', 'Stretch 4', 4, 9, 7, 3, 3, 'deadeye'),
    ('Jabari Dawson', 'Point Forward', 4, 7, 5, 9, 5, 'dimer'),
    ('Damon Mathis', 'Screening Big', 4, 2, 12, 5, 6, 'on_ball_menace'),
    ('Rell Kringle', 'Combo Guard', 4, 11, 7, 7, 4, 'deadeye'),
    ('Trent Adams', 'Sharpshooter', 4, 12, 5, 3, 2, 'corner_spec'),
    ('Jarrett Washington', 'Two-Way Forward', 4, 5, 11, 5, 6, 'pickpocket'),
    # --- Tier 5 ---
    ('Tobias Hughes', 'Scoring PG', 5, 11, 6, 7, 4, 'soft_touch'),
    ('Marcus Freeman', 'Slashing SF', 5, 6, 9, 6, 10, 'soft_touch'),
    ('Dee Underwood', 'Shooting SF', 5, 12, 8, 3, 3, 'quick_release'),
    ('Davon Walker', 'Rim-Run Big', 5, 4, 12, 3, 13, 'rim_protector'),
    ('Quinn Holt', 'Pass-First PG', 5, 4, 7, 13, 2, 'handles'),
    ('Wes Wright', 'Lockdown Wing', 5, 4, 12, 4, 3, 'interceptor'),
    ('Jeremiah Dixon', '3&D Wing', 5, 9, 12, 4, 4, 'quick_release'),
    ('Bradley Vance', 'Stretch 4', 5, 13, 7, 5, 4, 'deadeye'),
    ('Josh Cox', 'Point Forward', 5, 8, 6, 10, 6, 'handles'),
    ('Jalen Morgan', 'Screening Big', 5, 2, 13, 6, 7, 'rim_protector'),
    # --- Tier 6 ---
    ('Ace Nakamura', 'Scoring PG', 6, 12, 6, 9, 4, 'handles'),
    ('Marv Quill', 'Scoring PG', 6, 12, 5, 9, 4, 'star_power'),
    ('Zeke Abara', 'Slashing SF', 6, 6, 10, 4, 10, 'eurostep'),
    ('Damon Greer', 'Shooting SF', 6, 13, 8, 6, 3, 'limitless'),
    ('Trey Salas', 'Rim-Run Big', 6, 4, 11, 4, 15, 'lob_threat'),
    ('Sol Ingram', 'Lockdown Wing', 6, 5, 13, 4, 3, 'lockdown'),
    ('Kobi Sefu', 'Screening Big', 6, 3, 14, 9, 10, 'dream_shake'),
]
POOL = [{"name": n, "archetype": a, "tier": t, "sht": sh, "dfn": d,
         "plm": pl, "ath": at, "ability": ab}
        for (n, a, t, sh, d, pl, at, ab) in _POOL_RAW]


# ---------------------------------------------------------------------------
# COMMENTARY — randomized basketball phrasing for the play-by-play
# ---------------------------------------------------------------------------
PASS_VERBS = ["dishes to", "kicks it out to", "finds", "swings it to", "feeds",
              "threads it to", "drops it off to", "hits", "lobs it to"]
STEAL_LINES = ["PICKED OFF by {d}!", "{d} jumps the lane — STEAL!",
               "{d} reads it and takes it away!", "Stolen by {d}!",
               "{d} pickpockets him!", "{d} deflects and recovers — turnover!"]
MADE = {
    "layup": ["throws it DOWN!", "finishes at the rim", "lays it in off the glass",
              "slices to the cup — and the bucket", "strong finish through contact",
              "rises up and flushes it", "scoops it in"],
    "midrange": ["knocks down the jumper", "pull-up is GOOD", "drains the mid-range",
                 "cashes the elbow jumper", "rises and fires — money"],
    "three": ["from way downtown — BANG!", "splashes the triple", "buries it from deep",
              "wet from beyond the arc", "drills the three", "lets it fly — GOT IT"],
}
MISS = {
    "layup": ["can't finish at the rim", "blows the layup", "bricks it inside",
              "is walled off at the rim"],
    "midrange": ["pull-up is short", "misfires on the jumper", "clanks the mid-range",
                 "rattles it out"],
    "three": ["rims out from deep", "bricks the three", "off the mark from downtown",
              "front-irons the triple", "way short from deep"],
}
MISS_CONTESTED = ["is STUFFED by {d}!", "gets it swatted by {d}!",
                  "rises but {d} contests — no good", "shoots over {d} — off the iron"]
OPEN_PREFIX = ["wide open, ", "with room, ", "uncontested, ", "all alone, "]


def _shot_text(shooter, shot, made, man, pressure, pts):
    if made:
        line = random.choice(MADE[shot])
        pre = random.choice(OPEN_PREFIX) if pressure < 0.07 else ""
        return f"{shooter['name']} {pre}{line} (+{pts})"
    if pressure > 0.20 and man:
        return f"{shooter['name']} " + random.choice(MISS_CONTESTED).format(d=man["name"])
    return f"{shooter['name']} {random.choice(MISS[shot])}"


def _instantiate(entry, level=1):
    """Build a live player dict from a preset pool entry. Leveling lifts every
    stat (+2 per level past 1), capped, but the base identity stays the same."""
    archetype = entry["archetype"]
    a = ARCHETYPES[archetype]

    def lift(v):
        return min(16, v + (level - 1) * 2)

    sht, dfn = lift(entry["sht"]), lift(entry["dfn"])
    plm, ath = lift(entry["plm"]), lift(entry["ath"])
    p = {
        "id": uuid.uuid4().hex[:8],
        "name": entry["name"],
        "archetype": archetype,
        "tier": entry["tier"],
        "ability": entry.get("ability"),
        "ability_name": ability_name(entry.get("ability")),
        "abbr": a["abbr"],
        "behavior": a["behavior"],
        "spacing": a["spacing"],
        "cost": tier_price(entry["tier"]),
        "level": level,
        "xp": XP_FOR_LEVEL[level],   # copies absorbed so far (SAP-style progress)
        # the four SHOWN ratings
        "sht": sht, "dfn": dfn, "plm": plm, "ath": ath,
        "reb": ARCHETYPE_REB.get(archetype, 4),   # hidden rebounding rating
        "pos": None,    # {x, y} — must be one of the player's anchors
        "anchors": [{"x": float(x), "y": float(y)}
                    for (x, y) in ARCHETYPE_ANCHORS[archetype]],
        "positions": list(ARCHETYPE_POSITIONS[archetype]),  # eligible 1-5 slots
        "slot": None,   # which roster position this player was signed into
    }
    p.update(_hidden_stats(archetype, sht, dfn, plm, ath))   # back-end stats
    return p


def make_shop(games=0):
    """Fill the market from the preset pool, drawing only tiers unlocked by
    games played. No duplicate names within a single shop."""
    tiers = set(unlocked_tiers(games))
    available = [e for e in POOL if e["tier"] in tiers]
    k = min(SHOP_SIZE, len(available))
    picks = random.sample(available, k) if k else []
    return [_instantiate(e) for e in picks]


def roll_from_tier(tier):
    """Instantiate one random player from a given tier (capped at MAX_TIER).
    Used for the SAP-style 'level up -> a higher-tier card appears' reward."""
    tier = max(1, min(tier, MAX_TIER))
    pool = [e for e in POOL if e["tier"] == tier]
    return _instantiate(random.choice(pool)) if pool else None


def refresh_shop(old, games=0):
    """Reroll / next-round refresh that HOLDS frozen cards in place (SAP /
    Battlegrounds style). Frozen slots carry over; every other slot (including
    ones that were signed away = None) is refilled with a fresh unlocked player.
    Frozen cards stay frozen until bought or manually unfrozen."""
    tiers = set(unlocked_tiers(games))
    out, kept_names = [], set()
    for slot in (old or []):
        if slot and slot.get("frozen"):
            out.append(slot)
            kept_names.add(slot["name"])
        else:
            out.append(None)
    out = (out + [None] * SHOP_SIZE)[:SHOP_SIZE]

    pool = [e for e in POOL if e["tier"] in tiers and e["name"] not in kept_names]
    random.shuffle(pool)
    pi = 0
    for i in range(SHOP_SIZE):
        if out[i] is None and pi < len(pool):
            out[i] = _instantiate(pool[pi])
            pi += 1
    return out


# ---------------------------------------------------------------------------
# POSITIONS
# ---------------------------------------------------------------------------
def _too_close(pos, placed):
    return any(_dist((pos["x"], pos["y"]), (q["x"], q["y"])) < MIN_SEP
              for q in placed)


def _find_open(anchors, placed):
    """A spot for a player that is NOT on top of anyone already placed: try the
    archetype anchors first, then spiral outward from the primary anchor until a
    clear spot is found. Guarantees separation (the court easily fits five)."""
    for a in anchors:
        if not _too_close({"x": a["x"], "y": a["y"]}, placed):
            return (a["x"], a["y"])
    ax, ay = anchors[0]["x"], anchors[0]["y"]
    for r in range(int(MIN_SEP), 72, 3):
        for deg in range(0, 360, 18):
            rad = math.radians(deg)
            x = _clamp(ax + r * math.cos(rad), 6, 94)
            y = _clamp(ay + r * math.sin(rad), 6, 94)
            if not _too_close({"x": x, "y": y}, placed):
                return (x, y)
    return (ax, ay)


def ensure_positions(team):
    """Place every unplaced player so NO two players are on top of each other —
    preferring its anchors, otherwise the nearest clear spot."""
    placed = [p["pos"] for p in team if p.get("pos") and "x" in p["pos"]]
    for p in team:
        if p.get("pos") and "x" in p["pos"]:
            continue
        x, y = _find_open(p["anchors"], placed)
        p["pos"] = {"x": x, "y": y}
        placed.append(p["pos"])
    return team


def snap_to_anchor(player, x, y):
    """Move a player to whichever of its anchors is nearest to (x, y)."""
    best = min(player["anchors"],
               key=lambda a: _dist((a["x"], a["y"]), (x, y)))
    player["pos"] = {"x": best["x"], "y": best["y"]}
    return player


def overlapping_ids(team):
    """Ids of players standing on top of each other (closer than MIN_SEP)."""
    bad = set()
    pts = [(p["id"], p["pos"]) for p in team if p.get("pos") and "x" in p["pos"]]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            a, b = pts[i][1], pts[j][1]
            if _dist((a["x"], a["y"]), (b["x"], b["y"])) < MIN_SEP:
                bad.add(pts[i][0]); bad.add(pts[j][0])
    return sorted(bad)


def random_team(round_no):
    """Field a full five from the preset pool — one player per roster position
    1-5 — that doesn't overlap, so positional matchups are well-defined. The
    tier ceiling rises with the round, so opponents get tougher as you climb."""
    ceil = tier_ceiling_for_round(round_no)
    by_pos = {s: [e for e in POOL
                  if e["tier"] <= ceil and s in ARCHETYPE_POSITIONS[e["archetype"]]]
              for s in range(1, 6)}
    out = []
    for s in range(1, 6):
        lvl = 1 + (1 if random.random() < 0.10 + 0.035 * round_no else 0)
        p = _instantiate(random.choice(by_pos[s]), level=lvl)
        p["slot"] = s
        out.append(p)
    ensure_positions(out)        # guarantees no two players overlap
    return out


# ---------------------------------------------------------------------------
# GEOMETRY HELPERS
# ---------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _pt(p):
    return (p["pos"]["x"], p["pos"]["y"])


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seg_dist(p, a, b):
    """Distance from point p to segment ab."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return _dist(p, a)
    t = _clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
    return _dist(p, (ax + t * dx, ay + t * dy))


def shot_from_distance(d):
    if d < LAYUP_MAX:
        return "layup", BASE_LAYUP, 2
    if d < MID_MAX:
        return "midrange", BASE_MIDRANGE, 2
    return "three", BASE_THREE, 3


def archetype_fit(behavior, shot):
    pref = PREFERRED_SHOT.get(behavior)
    if pref is None:           # pure playmaker, not built to score
        return -0.07
    if shot == pref:
        return FIT_BONUS
    if shot == "midrange":     # midrange is nobody's strength but nobody's death
        return -0.03
    return -FIT_BONUS          # taking a shot far outside your archetype


def _defender_spot_xy(ox, oy):
    """Where a man-to-man defender stands relative to his man's live spot: on the
    line toward the basket, STANDOFF off (closer if the man is near the rim)."""
    bx, by = BASKET
    vx, vy = bx - ox, by - oy
    d = math.hypot(vx, vy)
    if d < 0.001:
        return (ox, oy + STANDOFF)
    step = min(STANDOFF, max(1.5, d - 2.0))
    return (ox + vx / d * step, oy + vy / d * step)


def _preferred_spot(p):
    """A player's ideal spot = their primary (most effective) anchor."""
    a = p["anchors"][0]
    return (a["x"], a["y"])


def _step_toward(sx, sy, tx, ty, cap):
    """Move from (sx,sy) toward (tx,ty), at most `cap` units. Clamped to court."""
    dx, dy = tx - sx, ty - sy
    d = math.hypot(dx, dy)
    if d <= cap or d == 0:
        nx, ny = tx, ty
    else:
        f = cap / d
        nx, ny = sx + dx * f, sy + dy * f
    return (_clamp(nx, 4, 96), _clamp(ny, 4, 96))


def _push_outside_arc(x, y, margin=2.0):
    """The ball never starts inside the 3-point line — if the handler's spot is
    inside the arc, step him straight back out past it."""
    bx, by = BASKET
    vx, vy = x - bx, y - by
    d = math.hypot(vx, vy) or 1.0
    if d >= MID_MAX + margin:
        return (x, y)
    f = (MID_MAX + margin) / d
    return (_clamp(bx + vx * f, 4, 96), _clamp(by + vy * f, 4, 96))


def _weighted_sample(items, weights, k):
    """Pick k distinct items by weight (no replacement)."""
    items, weights = list(items), list(weights)
    out = []
    for _ in range(min(k, len(items))):
        total = sum(weights)
        r = random.uniform(0, total) if total > 0 else 0
        upto = 0
        for i, w in enumerate(weights):
            upto += w
            if upto >= r:
                out.append(items.pop(i))
                weights.pop(i)
                break
    return out


def setup_positions(offense):
    """As the play develops, each player drifts toward their role spot — capped
    by SETUP_STEP so where you PLACED them still dominates. id -> (x, y)."""
    return {p["id"]: _step_toward(*_pt(p), *_preferred_spot(p), SETUP_STEP)
            for p in offense}


def _shot_target(behavior, x, y):
    """Where a player moves to GET their shot: shooters step out behind the arc,
    slashers/bigs drive to the rim, pull-up guards settle into midrange."""
    bx, by = BASKET
    vx, vy = x - bx, y - by                 # direction from basket to player
    d = math.hypot(vx, vy) or 1.0
    ux, uy = vx / d, vy / d
    pref = PREFERRED_SHOT.get(behavior)
    if pref == "three":
        desired = max(d, MID_MAX + 3)       # step behind the three-point line
    elif pref == "layup":
        desired = LAYUP_MAX - 5             # get closer, attack the rim
    elif pref == "midrange":
        desired = (LAYUP_MAX + MID_MAX) / 2
    else:
        desired = d                         # playmaker: hold
    return (bx + ux * desired, by + uy * desired)


def live_defense(offense, mapping, off_pos, doubles=None):
    """Man-to-man defenders track their man's live (dribbled) spot; any doubling
    defender sits next to the player he traps so he counts as help. id -> (x, y)."""
    pos = {}
    for o in offense:
        d = mapping.get(o["id"])
        if d:
            ox, oy = off_pos[o["id"]]
            pos[d["id"]] = _defender_spot_xy(ox, oy)
    for did, oid in (doubles or {}).items():
        if oid in off_pos:
            ox, oy = off_pos[oid]
            # stand just to the side of the trapped man (toward the baseline)
            pos[did] = (_clamp(ox + DOUBLE_OFFSET, 4, 96),
                        _clamp(oy - DOUBLE_OFFSET * 0.5, 4, 96))
    return pos


def possession_layout(offense, defense, off_pos, def_pos):
    """Token coords for one possession (after dribbling), for the frontend."""
    off_layout = [{"id": o["id"], "x": off_pos[o["id"]][0], "y": off_pos[o["id"]][1]}
                  for o in offense if o["id"] in off_pos]
    def_layout = [{"id": did, "x": xy[0], "y": xy[1]} for did, xy in def_pos.items()]
    placed = set(def_pos)
    for d in defense:                      # unguarded defenders sag to the paint
        if d["id"] not in placed:
            def_layout.append({"id": d["id"], "x": 50.0, "y": 18.0})
    return {"offense": off_layout, "defense": def_layout}


def assign_defense(offense, defense):
    """Man-to-man BY POSITION: the defender at each roster position guards the
    offensive player at the same position (PG on PG, C on C, ...). Anyone left
    unmatched (mismatched/short lineups) is picked up by the best free defender.

    When the defense OUTNUMBERS the offense (the offense started short of five),
    each surplus defender double-teams: it looks at the two offensive players
    nearest the basket and traps the one with the higher offense rating.

    Returns (mapping: offense id -> defender, doubles: defender id -> offense id)."""
    mapping = {}                       # offense id -> defender dict
    used = set()
    for o in offense:
        d = next((x for x in defense
                  if x.get("slot") == o.get("slot") and x["id"] not in used), None)
        if d:
            mapping[o["id"]] = d
            used.add(d["id"])
    leftovers = sorted((x for x in defense if x["id"] not in used),
                       key=lambda d: d["dfn"], reverse=True)
    i = 0
    for o in offense:
        if o["id"] not in mapping and i < len(leftovers):
            mapping[o["id"]] = leftovers[i]
            used.add(leftovers[i]["id"])
            i += 1

    # surplus defenders (offense was short-handed) double the biggest threat
    doubles = {}
    placed = [o for o in offense if o.get("pos") and "x" in o["pos"]]
    for d in defense:
        if d["id"] in used or not placed:
            continue
        near2 = sorted(placed, key=lambda o: _dist(_pt(o), BASKET))[:2]
        target = max(near2, key=lambda o: o["sht"] + o["ath"])
        doubles[d["id"]] = target["id"]
        used.add(d["id"])
    return mapping, doubles


# ---------------------------------------------------------------------------
# POSSESSION
# ---------------------------------------------------------------------------
def _team_off_bonus(offense):
    """Team-wide offense deltas from abilities: Floor General lifts teammates,
    Ball Stopper drags them down. id -> integer delta on the OFF rating."""
    bonus = {p["id"]: 0 for p in offense}
    for p in offense:
        ab = p.get("ability")
        delta = 1 if ab == "floor_general" else -1 if ab == "ball_stopper" else 0
        if delta:
            for q in offense:
                if q["id"] != p["id"]:
                    bonus[q["id"]] += delta
    return bonus


def _pass_risk(passer, receiver, defense, off_pos, def_pos, to_mult=1.0):
    pp, rp = off_pos[passer["id"]], off_pos[receiver["id"]]
    pd = _dist(pp, rp)
    lane = 0.0
    culprit = None
    worst = 0.0
    for d in defense:
        if d["id"] not in def_pos:
            continue
        sd = _seg_dist(def_pos[d["id"]], pp, rp)
        if sd < LANE_RANGE:
            dab = d.get("ability")           # ball-hawks jump the lane harder
            grab = 1.8 if dab == "interceptor" else 1.5 if dab == "pickpocket" else 1.0
            contrib = (d.get("d_steal", d["dfn"] * 0.5) / 10.0) * 0.06 * (1 - sd / LANE_RANGE) * grab
            lane += contrib
            if contrib > worst:
                worst, culprit = contrib, d
    # the farther the pass travels, the easier it is to jump (steeper distance term)
    p = 0.02 + 0.006 * pd + lane - 0.02 * (passer["plm"] - 5)
    if passer.get("ability") == "handles":         # secure handle
        p *= 0.65
    if receiver.get("ability") == "turnover_prone": # risky to feed
        p *= 1.4
    p *= to_mult                                    # team-wide (e.g. Tempo Control)
    return _clamp(p, 0.02, 0.6), culprit


def _evaluate(shooter, defense, mapping, off_pos, def_pos,
              passer=None, off_pass=False, off_bonus=None):
    """Expected look quality for `shooter` taking the shot this possession,
    using live (post-dribble) positions. Player abilities adjust the look:
    the shooter's, his man defender's, and any rim-protecting help defender's."""
    sp = off_pos[shooter["id"]]
    d = _dist(sp, BASKET)
    shot, base, pts = shot_from_distance(d)
    sab = shooter.get("ability")
    bonus = 0.0
    # zone-specific scoring rating: jumpers use Shooting (mid/three), the rim
    # uses Athleticism (finishing). This is what splits a big's game from a guard's.
    zone_rating = {"layup": shooter.get("s_rim", shooter["ath"]),
                   "midrange": shooter.get("s_mid", shooter["sht"]),
                   "three": shooter.get("s_three", shooter["sht"])}[shot]

    # Dream Shake: a big scores a midrange look like a rim finish
    if sab == "dream_shake" and shot == "midrange":
        base, zone_rating = BASE_LAYUP, shooter.get("s_rim", shooter["ath"])

    man = mapping.get(shooter["id"])
    contest = 0.0
    if man and man["id"] in def_pos:
        gap = _dist(sp, def_pos[man["id"]])
        closeness = _clamp(1 - gap / CONTEST_RANGE, 0, 1)
        mab = man.get("ability")
        if mab == "on_ball_menace":          # bothers his man even at distance
            closeness = max(closeness, 0.5)
        contest = (man["dfn"] / 10.0) * closeness * CONTEST_SCALE
        if shot == "layup":                  # rebounding = rim presence on defense
            contest += (man.get("reb", 4) / 10.0) * 0.03
        if mab == "lockdown":
            contest *= 1.6

    # help defenders within range each chip in; rim protectors hit layups harder
    helps = []
    for od in defense:
        if man and od["id"] == man["id"]:
            continue
        if od["id"] in def_pos and _dist(def_pos[od["id"]], sp) < HELP_RANGE:
            h = (od["dfn"] / 10.0) * HELP_PER
            if od.get("ability") == "rim_protector" and shot == "layup":
                h += (od["dfn"] / 10.0) * HELP_PER * 1.5
            helps.append(h)
    if sab == "killer_cross" and helps:      # blow by the single biggest helper
        helps.remove(max(helps))
    help_d = min(sum(helps), HELP_CAP)

    # offensive abilities shape the look
    if sab == "limitless":
        deep = 0.0
    else:
        deep = DEEP_PENALTY * max(0.0, d - MID_MAX) if shot == "three" else 0.0
    if sab == "deadeye" and shot in ("midrange", "three"):
        contest *= 0.55
    if sab == "quick_release":
        help_d *= 0.5
    if sab == "eurostep" and shot == "layup":
        help_d *= 0.4
        bonus += 0.05
    if sab == "soft_touch" and shot == "midrange":
        bonus += 0.06
    if sab == "iso_threat":
        bonus += 0.04
    if sab == "catch_shoot" and off_pass and shot in ("midrange", "three"):
        bonus += 0.07
    if sab == "lob_threat" and off_pass and shot == "layup":
        bonus += 0.13
    if off_pass and passer and passer.get("ability") == "dimer":
        bonus += 0.06

    off_adj = (off_bonus or {}).get(shooter["id"], 0)
    prob = _clamp(base + ZONE_COEFF * (zone_rating + off_adj - SCORE_REF) + bonus
                  - contest - help_d - deep, 0.05, 0.96)
    pressure = contest + help_d
    return dict(shot=shot, pts=pts, prob=prob, fit=0.0, pressure=pressure, man=man)


def _open_factor(shooter, look, mapping):
    """Multiplier that funnels the offense toward the open man: the lower the
    pressure on a look the more attractive it is, and a player with no man
    defender at all gets the biggest pull."""
    openness = 1 - _clamp(look["pressure"] / PRESSURE_NORM, 0, 1)
    factor = 1.0 + OPEN_BIAS * openness
    if mapping.get(shooter["id"]) is None:
        factor += UNGUARDED_BONUS
    return factor


def _reb(p):
    """Hidden rebounding rating (fallback for older snapshots without it)."""
    return p.get("reb", ARCHETYPE_REB.get(p["archetype"], 4))


def _advance(offense, cur, shooter_id, shot_spot, beat):
    """Advance one beat of PURPOSEFUL motion: the shooter works toward his shot
    spot; everyone else just holds spacing at their role spot (small settle —
    no wandering, no drifting away from the basket). Returns id -> (x, y)."""
    nxt = {}
    for p in offense:
        if p["id"] == shooter_id:
            tx, ty = shot_spot
            step = MOVE_STEP
        else:
            a = p["anchors"][0]           # primary (role) spot — hold your spacing
            tx, ty = a["x"], a["y"]
            step = MOVE_STEP * 0.4        # gentle settle, not constant motion
        nxt[p["id"]] = _step_toward(cur[p["id"]][0], cur[p["id"]][1], tx, ty, step)
    return nxt


def _oreb_won(offense, defense):
    """Did the offense grab the offensive rebound? Tuned UNDER real NBA OREB%
    (~26%) since this is a turn game — second chances are uncommon."""
    off_r = sum(_reb(p) for p in offense)
    def_r = sum(_reb(p) for p in defense)
    share = off_r / (off_r + def_r) if (off_r + def_r) else 0.5
    chance = OREB_BASE + OREB_SWING * (share - 0.5)
    if any(p.get("ability") == "putback" for p in offense):
        chance += PUTBACK_BONUS
    return random.random() < _clamp(chance, 0.04, OREB_CAP)


def run_possession(offense, defense, mapping, doubles=None, off_bonus=None, to_mult=1.0):
    """One possession: players drift into the play (setup), the team picks the
    best developing look, then that action is executed with justified movement —
    the shooter moves to get the shot, the passer steps in to deliver it.
    `off_bonus`/`to_mult` carry team-wide ability effects. Returns
    (points, events, setup_layout, shot_layout)."""
    events = []
    if not offense:
        miss = [{"kind": "miss", "text": "Empty lineup — no shot.",
                 "actor": None, "target": None, "points": 0}]
        empty = {"offense": [], "defense": []}
        return 0, miss, empty, empty, None

    # --- who starts with the ball: weighted by archetype "handle" tendency ---
    initiator = random.choices(offense,
                               weights=[max(0.1, _tend(p, "handle")) for p in offense])[0]

    # --- setup: everyone drifts toward their role spot -----------------------
    setup = setup_positions(offense)
    # the ball never starts inside the arc — the handler steps back out if needed
    setup[initiator["id"]] = _push_outside_arc(*setup[initiator["id"]])
    def_setup = live_defense(offense, mapping, setup, doubles)
    setup_layout = possession_layout(offense, defense, setup, def_setup)

    options = []
    for s in offense:
        passing_opt = s["id"] != initiator["id"]
        look = _evaluate(s, defense, mapping, setup, def_setup,
                         passer=initiator, off_pass=passing_opt, off_bonus=off_bonus)
        to_p, culprit = (0.0, None)
        if passing_opt:
            to_p, culprit = _pass_risk(initiator, s, defense, setup, def_setup, to_mult)
        # favor the open man + the archetype's shooting tendency
        ev = (look["prob"] * look["pts"] * (1 - to_p)
              * _open_factor(s, look, mapping) * _tend(s, "shoot"))
        options.append((s, ev))
    weights = [max(0.0001, ev) ** 4 for _, ev in options]
    shooter = random.choices([o[0] for o in options], weights=weights, k=1)[0]

    # --- build the pass chain: initiator -> [intermediates] -> shooter -------
    passing = shooter["id"] != initiator["id"]
    if passing:
        others = [p for p in offense
                  if p["id"] not in (initiator["id"], shooter["id"])]
        want = random.choices([1, 2, 3], weights=[PASS_WEIGHTS[1], PASS_WEIGHTS[2],
                                                  PASS_WEIGHTS[3]])[0]
        want = min(want, len(others) + 1)          # need want-1 intermediates
        mids = (_weighted_sample(others, [max(0.1, _tend(p, "pass")) for p in others],
                                 want - 1) if want > 1 else [])
        chain = [initiator] + mids + [shooter]
    else:
        chain = [shooter]                           # initiator takes it himself

    sx, sy = setup[shooter["id"]]
    shot_spot = _step_toward(sx, sy, *_shot_target(shooter["behavior"], sx, sy), SHOT_STEP)

    # --- walk the play beat-by-beat; players keep MOVING the whole time -------
    cur, beat = dict(setup), 1
    for i in range(len(chain) - 1):
        frm, to = chain[i], chain[i + 1]
        cur = _advance(offense, cur, shooter["id"], shot_spot, beat); beat += 1
        cur_def = live_defense(offense, mapping, cur, doubles)
        layout = possession_layout(offense, defense, cur, cur_def)
        risk, culprit = _pass_risk(frm, to, defense, cur, cur_def, to_mult)
        if random.random() < risk:          # intercepted BEFORE reaching the target
            thief = culprit or mapping.get(to["id"])
            tname = thief["name"] if thief else "the defense"
            events.append({
                "kind": "steal", "actor": (thief["id"] if thief else None),
                "target": to["id"], "points": 0, "layout": layout,
                "text": "   " + random.choice(STEAL_LINES).format(d=tname) + " Turnover.",
            })
            return 0, events, setup_layout, layout, initiator["id"]
        events.append({
            "kind": "pass", "actor": frm["id"], "target": to["id"], "points": 0,
            "layout": layout,
            "text": f"{frm['name']} {random.choice(PASS_VERBS)} {to['name']}",
        })

    # --- the shot (shooter has worked to his spot) ---------------------------
    cur = _advance(offense, cur, shooter["id"], shot_spot, beat)
    cur[shooter["id"]] = shot_spot
    cur_def = live_defense(offense, mapping, cur, doubles)
    shot_layout = possession_layout(offense, defense, cur, cur_def)
    look = _evaluate(shooter, defense, mapping, cur, cur_def,
                     passer=(chain[-2] if passing else None), off_pass=passing,
                     off_bonus=off_bonus)
    contest_def = look["man"]["id"] if look["man"] else None
    made = random.random() < look["prob"]
    text = _shot_text(shooter, look["shot"], made, look["man"],
                      look["pressure"], look["pts"])
    pts = look["pts"] if made else 0
    events.append({
        "kind": "made" if made else "miss", "actor": shooter["id"],
        "target": contest_def, "points": pts, "shot": look["shot"],
        "layout": shot_layout, "text": text,
    })

    # --- rebounding: a MISS can be grabbed by the offense for ONE putback ----
    if not made and _oreb_won(offense, defense):
        rebounder = max(offense, key=_reb)
        # crash the boards — collapse toward the rim
        reb_pos = {p["id"]: _step_toward(cur[p["id"]][0], cur[p["id"]][1],
                                         BASKET[0], BASKET[1] + 8, MOVE_STEP) for p in offense}
        reb_pos[rebounder["id"]] = (BASKET[0], BASKET[1] + 7)
        reb_def = live_defense(offense, mapping, reb_pos, doubles)
        reb_layout = possession_layout(offense, defense, reb_pos, reb_def)
        events.append({
            "kind": "rebound", "actor": rebounder["id"], "target": None, "points": 0,
            "layout": reb_layout,
            "text": f"   {rebounder['name']} grabs the offensive board!",
        })
        pb = _clamp(BASE_LAYUP - 0.08 + 0.03 * (rebounder["ath"] - 6)
                    + (0.08 if rebounder.get("ability") == "putback" else 0), 0.2, 0.85)
        pb_made = random.random() < pb
        pts += 2 if pb_made else 0
        events.append({
            "kind": "made" if pb_made else "miss", "actor": rebounder["id"],
            "target": None, "points": 2 if pb_made else 0, "shot": "layup",
            "layout": reb_layout,
            "text": f"   {rebounder['name']} " + ("puts it back!" if pb_made
                                                  else "can't convert the putback"),
        })

    return pts, events, setup_layout, shot_layout, initiator["id"]


def _play_half(offense, defense, possessions=POSSESSIONS_PER_SIDE):
    """Run one team's possessions; each starts with a capped dribble toward
    ideal spots. Returns (points, [possession dicts with per-poss layout])."""
    mapping, doubles = assign_defense(offense, defense)
    off_bonus = _team_off_bonus(offense)
    to_mult = 0.85 if any(p.get("ability") == "tempo_control" for p in offense) else 1.0
    poss_list, total = [], 0
    for _ in range(possessions):
        pts, evs, setup_layout, shot_layout, handler = run_possession(
            offense, defense, mapping, doubles, off_bonus, to_mult)
        total += pts
        poss_list.append({
            "points": pts,
            "events": evs,
            "handler": handler,            # who actually started with the ball
            "layout": setup_layout,        # where players drift as the play sets up
            "shot_layout": shot_layout,    # final spots when the shot/pass happens
        })
    return total, poss_list


def _center(team):
    """The team's center (roster slot 5), else its biggest body by rebounding."""
    c = [p for p in team if p.get("slot") == 5]
    if c:
        return c[0]
    return max(team, key=_reb) if team else None


def decide_tip(you, opp):
    """Who gets the ball first: the team with the higher total scoring rating.
    On a tie it's a coin flip WEIGHTED by each center's size (the jump ball),
    so equal teams no longer default to YOU. Returns True if YOU win the tip.
    (Presentation only — both teams get the same number of possessions.)"""
    yo = sum(p["sht"] + p["ath"] for p in you)
    oo = sum(p["sht"] + p["ath"] for p in opp)
    if yo != oo:
        return yo > oo
    yc, oc = _center(you), _center(opp)
    yw = _reb(yc) if yc else 1
    ow = _reb(oc) if oc else 1
    return random.random() < yw / (yw + ow)


def _box_score(team, own_poss, opp_poss):
    """Per-player box score for `team`: pts, FGM/FGA, assists, rebounds.
    Offensive rebounds come straight from the possession events; defensive
    rebounds (the opponent's misses this team secured) are distributed across
    the team weighted by rebounding rating."""
    box = {p["id"]: {"id": p["id"], "name": p["name"], "slot": p.get("slot"),
                     "pts": 0, "fgm": 0, "fga": 0, "ast": 0, "reb": 0}
           for p in team}
    for poss in own_poss:
        evs = poss["events"]
        for i, ev in enumerate(evs):
            a = ev.get("actor")
            if a not in box:
                continue
            if ev["kind"] in ("made", "miss") and ev.get("shot"):
                box[a]["fga"] += 1
                if ev["kind"] == "made":
                    box[a]["fgm"] += 1
                    box[a]["pts"] += ev.get("points", 0)
                    # assist: the pass immediately before a make
                    if i > 0 and evs[i - 1]["kind"] == "pass":
                        pa = evs[i - 1].get("actor")
                        if pa in box:
                            box[pa]["ast"] += 1
            elif ev["kind"] == "rebound":          # offensive board
                box[a]["reb"] += 1

    # defensive rebounds: opponent misses that were NOT offensive-rebounded
    dreb = 0
    for poss in opp_poss:
        evs = poss["events"]
        for i, ev in enumerate(evs):
            if ev["kind"] == "miss" and ev.get("shot"):
                nxt = evs[i + 1] if i + 1 < len(evs) else None
                if not (nxt and nxt["kind"] == "rebound"):
                    dreb += 1
    if dreb and team:
        weights = [max(0.1, _reb(p)) for p in team]
        for _ in range(dreb):
            who = random.choices(team, weights=weights)[0]
            box[who["id"]]["reb"] += 1
    return list(box.values())


def finals_opponent():
    """A stacked championship opponent for the Finals: a full five drawn from the
    top tiers, several already leveled up. The toughest team in the game."""
    by_pos = {s: [e for e in POOL
                  if e["tier"] >= MAX_TIER - 1
                  and s in ARCHETYPE_POSITIONS[e["archetype"]]]
              for s in range(1, 6)}
    out = []
    for s in range(1, 6):
        pool = by_pos[s] or [e for e in POOL if s in ARCHETYPE_POSITIONS[e["archetype"]]]
        lvl = 2 if random.random() < 0.6 else 1
        p = _instantiate(random.choice(pool), level=lvl)
        p["slot"] = s
        out.append(p)
    ensure_positions(out)
    return out


def _sudden_death(you, opp, you_first):
    """Finals overtime: alternating single possessions until ONE team scores —
    first bucket wins. Returns (verdict, extra_you_poss, extra_opp_poss) so the
    OT trips animate and score like any other possession."""
    you_map, you_dbl = assign_defense(you, opp)
    opp_map, opp_dbl = assign_defense(opp, you)
    you_ob, opp_ob = _team_off_bonus(you), _team_off_bonus(opp)
    you_to = 0.85 if any(p.get("ability") == "tempo_control" for p in you) else 1.0
    opp_to = 0.85 if any(p.get("ability") == "tempo_control" for p in opp) else 1.0

    def trip(off, dfn, mp, db, ob, to):
        pts, evs, sl, shl, h = run_possession(off, dfn, mp, db, ob, to)
        return pts, {"points": pts, "events": evs, "handler": h,
                     "layout": sl, "shot_layout": shl, "ot": True}

    yposs, oposs = [], []
    order = ["you", "opp"] if you_first else ["opp", "you"]
    for _ in range(20):                       # cap guards against an endless tie
        for side in order:
            if side == "you":
                pts, poss = trip(you, opp, you_map, you_dbl, you_ob, you_to)
                yposs.append(poss)
                if pts > 0:
                    return "win", yposs, oposs
            else:
                pts, poss = trip(opp, you, opp_map, opp_dbl, opp_ob, opp_to)
                oposs.append(poss)
                if pts > 0:
                    return "loss", yposs, oposs
    win = sum(p["sht"] + p["ath"] for p in you) >= sum(p["sht"] + p["ath"] for p in opp)
    return ("win" if win else "loss"), yposs, oposs


def play_round(lineup, opponent, finals=False):
    # simulate on buffed copies so chemistry applies without mutating the
    # player's persistent roster
    you = copy.deepcopy(lineup)
    opp = copy.deepcopy(opponent)
    chem_you = _apply_chemistry(you)
    chem_opp = _apply_chemistry(opp)
    ensure_positions(you)
    ensure_positions(opp)

    npos = FINALS_POSSESSIONS if finals else POSSESSIONS_PER_SIDE
    you_pts, you_poss = _play_half(you, opp, npos)
    opp_pts, opp_poss = _play_half(opp, you, npos)
    you_first = decide_tip(you, opp)
    ot = False

    # a tie is a PUSH — except the Finals can't end tied: sudden-death overtime,
    # first team to score takes the title.
    if you_pts > opp_pts:
        verdict = "win"
    elif you_pts < opp_pts:
        verdict = "loss"
    elif finals:
        ot = True
        verdict, ot_you, ot_opp = _sudden_death(you, opp, you_first)
        you_poss += ot_you
        opp_poss += ot_opp
        you_pts = sum(p["points"] for p in you_poss)
        opp_pts = sum(p["points"] for p in opp_poss)
    else:
        verdict = "push"

    return {
        "you_possessions": you_poss,
        "opp_possessions": opp_poss,
        "you_pts": you_pts,
        "opp_pts": opp_pts,
        "verdict": verdict,
        "won": verdict == "win",
        "you_first": you_first,
        "ot": ot,
        "you_box": _box_score(you, you_poss, opp_poss),
        "opp_box": _box_score(opp, opp_poss, you_poss),
        "chem_you": [{"name": c["name"], "kind": c["kind"]} for c in chem_you],
        "chem_opp": [{"name": c["name"], "kind": c["kind"]} for c in chem_opp],
    }


# ---------------------------------------------------------------------------
# ECONOMY / BUILD helpers (rules stay in Python)
# ---------------------------------------------------------------------------
# release refund rises with tier (T1-2 -> 1, T3-4 -> 2, T5-6 -> 3); some
# abilities make a player worth more on release.
RELEASE_BONUS = {"fan_favorite": 2}
TIER_SELL = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}


def sell_refund(player):
    base = TIER_SELL.get(player.get("tier", 1), 1)
    return base + RELEASE_BONUS.get(player.get("ability"), 0)


STAR_POWER_CAP = 2  # extra cap per round for each Star Power player rostered


def cap_income(lineup):
    """Per-round cap income, raised by any Star Power players in the lineup."""
    stars = sum(1 for p in lineup if p.get("ability") == "star_power")
    return CAP_PER_ROUND + STAR_POWER_CAP * stars


STAT_CAP = 16  # ceiling for a single rating after leveling

# Super Auto Pets leveling: a player levels by absorbing copies. It takes 2
# copies to reach L2, then 3 more (5 total) to reach L3, which is the max.
MAX_LEVEL = 3
XP_FOR_LEVEL = {1: 0, 2: 2, 3: 5}   # copies absorbed needed to REACH each level


def level_for_xp(xp):
    if xp >= XP_FOR_LEVEL[3]:
        return 3
    if xp >= XP_FOR_LEVEL[2]:
        return 2
    return 1


def xp_to_next(player):
    """Copies still needed for the next level, or 0 if maxed. (current, needed)."""
    lvl = player.get("level", 1)
    if lvl >= MAX_LEVEL:
        return 0
    return XP_FOR_LEVEL[lvl + 1] - player.get("xp", 0)


def level_up(base, incoming):
    """Absorb one `incoming` copy into `base` (same archetype). A copy adds AT
    MOST +1 per attribute, and ONLY on the attributes the incoming player is
    actually BETTER at — the base never inherits the copy's raw numbers. This
    keeps a player anchored to its own tier: you can't rocket a Tier-1 roster up
    by feeding it Tier-6 copies; real upgrades mean releasing and buying higher.
    Level recomputes from copies absorbed (L2 at 2, L3 at 5); REACHING a new
    level grants +1 to ALL stats on top of the per-copy bump. Returns
    (base, leveled_up?)."""
    old_level = base.get("level", 1)
    for k in ("sht", "dfn", "plm", "ath"):
        if incoming[k] > base[k]:
            base[k] = min(STAT_CAP, base[k] + 1)
    base["xp"] = min(XP_FOR_LEVEL[MAX_LEVEL], base.get("xp", 0) + 1)
    base["level"] = level_for_xp(base["xp"])
    leveled = base["level"] > old_level
    if leveled:                       # hitting a new level: +1 to EVERY stat
        for k in ("sht", "dfn", "plm", "ath"):
            base[k] = min(STAT_CAP, base[k] + 1)
    _refresh_hidden(base)
    return base, leveled
