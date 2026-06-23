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
POSSESSIONS_PER_SIDE = 7
FINALS_POSSESSIONS = 15   # the Finals runs longer — less variance, better team wins
LINEUP_SIZE = 5
SHOP_SIZE = 5
STARTING_CAP = 17
CAP_PER_ROUND = 8
REROLL_COST = 1
WINS_TO_FINISH = 12       # wins that clinch a Finals berth (championship run)
LOSSES_TO_BUST = 4        # losses that eliminate you

# Court / geometry (coords are 0-100 on both axes; basket near the top baseline)
BASKET = (50.0, 5.0)
LAYUP_MAX = 16.0          # distance < this = at the rim
MID_MAX = 40.0           # distance < this = midrange, else three (matches arc)
STANDOFF = 7.0           # how far a defender sits off his man toward the basket
CONTEST_RANGE = 24.0     # beyond this, a defender contests nothing
CONTEST_SCALE = 0.25     # max make-% an on-ball defender removes (lowered for scoring)
HELP_RANGE = 20.0        # a help defender this close to the shooter chips in
HELP_PER = 0.045         # make-% removed per nearby help defender (bunching hurts)
HELP_CAP = 0.30          # every defender in the area piles on
LANE_RANGE = 8.0         # a defender this close to the pass line threatens it
# Turnover model — lower = more video-game-like, higher scoring (tuned 2026-06-21).
TO_BASE = 0.004          # base pass-turnover chance (tuned to ~10% of possessions)
TO_DIST = 0.0008         # added turnover chance per unit of pass distance
STEAL_LANE = 0.012       # steal contribution per defender sitting in the lane
TO_CAP = 0.16            # hard ceiling on a single pass's turnover chance
MIN_SEP = 11.0           # offensive players closer than this overlap (illegal)
SETUP_STEP = 8.0         # drift toward your role spot as the play develops
SHOT_STEP = 7.0          # the shooter's move to GET the shot (drive in / step out)
PASS_STEP = 5.0          # the passer steps into the play to deliver it
# how many passes a possession swings before the shot (when it isn't a self-shot):
# 2 is the norm, 1 fairly common, 3 rare. Capped at 3 by the available players.
PASS_WEIGHTS = {1: 0.28, 2: 0.54, 3: 0.18}
MOVE_STEP = 5.0          # how far players drift each beat DURING the play (live motion)
# --- purposeful movement + screens (2026-06-22) -----------------------------
# Players move with intent and the sim emits many small frames so motion glides
# instead of jumping. Off-ball players space the floor; a big can set a screen.
DEVELOP_FRAMES = 2       # smooth frames as the play develops before the ball swings
PRESHOT_FRAMES = 3       # smooth frames as the shooter curls into his shot
PASS_FRAMES = 1          # settle frames before each pass
CROWD_DIST = 17.0        # a spacer closer than this to the ball slides away to open space
SPACE_STEP = 6.0         # how far a spacer relocates toward open space
SCREEN_CHANCE = 0.55     # how often a screen is set (when an eligible big is on the floor)
SCREEN_BEHAVIORS = ("screen", "roll")   # archetypes that set screens (bigs)
SCREEN_OPEN = 0.11       # extra make-% the freed shooter gets coming off a clean screen
SCREEN_SET_DIST = 8.0    # the big must get this close to the defender to actually set the pick
SCREEN_APPROACH = 1.7    # the screener hustles to the pick faster than a normal drift
SCREEN_MAX_FRAMES = 5    # cap on frames spent getting into the screen
SCREEN_SIDE = 4.5        # the screener stands this far to ONE SIDE of the man (not stacked on him)
SCREEN_HOLD_FRAMES = 3   # how long the big STAYS planted on the pick before he rolls/pops
TRAIL_GAP = 9.0          # how far the beaten defender trails BEHIND the freed shooter
SHOOTER_BURST = 1.4      # the freed man accelerates off the screen the instant it's set
SCREEN_RELOCATE = 15.0   # how far the freed man relocates off the pick to open space
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

# Shot base make-rates before ratings/fit/defense (raised for a higher-scoring,
# video-game feel — 2026-06-21; shot MIX preserved via ZONE_CAL).
BASE_LAYUP = 0.74
BASE_MIDRANGE = 0.49
BASE_THREE = 0.41

# --- signature-ability tuning (heat_check / corner_spec / shot_blocker / mentor /
#     streaky). These five are wired into the possession sim below. ----------------
HEAT_STREAK = 2          # consecutive makes that trigger a Heat Check player's heat
HEAT_BONUS = 0.10        # make-% added while hot
HEAT_SELECT = 1.8        # how much more the offense funnels to a hot Heat Check player
STREAK_SWING = 0.09      # Streaky: make-% nudged toward repeating his last outcome
CORNER_BONUS = 0.09      # Corner Specialist: make-% added on a corner three
CORNER_X = 22.0          # within this of a sideline (|x-50|>=50-CORNER_X) counts as corner
CORNER_Y = 24.0          # ...and this close to the baseline (y<=CORNER_Y)
BLOCK_SCALE = 0.040      # Shot Blocker: block chance per point of rim-protection rating
BLOCK_MID = 0.45         # blocks are far rarer on midrange pull-ups than at the rim
MENTOR_PER = 0.012       # make-% a Mentor grants a teammate per round played together
MENTOR_CAP = 0.09        # ...capped, so tenure pays off but never dominates

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
# [primary (identity zone), secondary (midrange)]. DATA-DERIVED from 2015-16
# SportVU tracking (NBAHeatmaps/export.py, zone-aware: primary = densest spot in
# the archetype's dominant zone per ARCHETYPE_ZONE_MIX, secondary = midrange).
# Replaced the earlier hand-authored anchors (2026-06-21).
ARCHETYPE_ANCHORS = {
    "Pass-First PG": [(83, 51), (65, 13)],
    "Scoring PG":    [(53, 83), (47, 35)],
    "Slashing SF":   [(7, 15), (51, 35)],
    "Shooting SF":   [(7, 13), (67, 15)],
    "Stretch 4":     [(19, 53), (65, 13)],
    "Screening Big": [(51, 11), (65, 19)],
    "Rim-Run Big":   [(53, 13), (51, 39)],
    "Lockdown Wing": [(93, 11), (47, 43)],
    "3&D Wing":      [(93, 15), (63, 17)],
    "Point Forward": [(7, 15), (67, 19)],
    "Combo Guard":   [(77, 71), (47, 41)],
    "Sharpshooter":  [(93, 13), (47, 37)],
    "Two-Way Forward": [(93, 9), (65, 13)],
    "Stretch Center": [(35, 45), (35, 19)],
    "Post Scorer":   [(59, 11), (69, 19)],
    "Defensive Anchor": [(51, 13), (35, 15)],
}

# Share of offensive frontcourt time spent at the rim / midrange / three, by
# archetype. DATA-DERIVED from 2015-16 SportVU tracking (NBAHeatmaps). The lever
# for shot-diet realism (game 3PA freq ~47% vs real ~33%); NOT yet wired into
# shot selection — see the EV funnel TODO in _evaluate (step 8).
ARCHETYPE_ZONE_MIX = {   # (rim, midrange, three)
    "Pass-First PG":    (0.09, 0.252, 0.657),
    "Scoring PG":       (0.082, 0.235, 0.683),
    "Slashing SF":      (0.101, 0.298, 0.601),
    "Shooting SF":      (0.09, 0.309, 0.601),
    "Stretch 4":        (0.173, 0.297, 0.53),
    "Screening Big":    (0.222, 0.4, 0.379),
    "Rim-Run Big":      (0.271, 0.425, 0.304),
    "Lockdown Wing":    (0.092, 0.244, 0.664),
    "3&D Wing":         (0.115, 0.259, 0.627),
    "Point Forward":    (0.144, 0.333, 0.524),
    "Combo Guard":      (0.056, 0.277, 0.667),
    "Sharpshooter":     (0.049, 0.24, 0.711),
    "Two-Way Forward":  (0.14, 0.367, 0.493),
    "Stretch Center":   (0.195, 0.395, 0.409),
    "Post Scorer":      (0.193, 0.5, 0.306),
    "Defensive Anchor": (0.267, 0.424, 0.309),
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


def display_shooting(archetype, sht):
    """The SHOWN 'Shooting' rating, recomputed to reflect a player's REAL jump-shot
    threat instead of the raw `sht` budget. A big with a high raw `sht` reads near-0
    here because his archetype rarely shoots jumpers and converts them poorly; a
    sharpshooter reads near his full rating. Derived straight from the quantities the
    sim already uses: effective = sht * (how good his jumpers are, weighted by how
    OFTEN he takes mid vs three per ARCHETYPE_ZONE_MIX). Rim scoring lives in ATH and
    is shown there, so this number is specifically his perimeter/jump shooting."""
    rim_w, mid_w, three_w = SHOT_PROFILE.get(archetype, (0.6, 0.6, 0.6))
    _, mid_occ, three_occ = ARCHETYPE_ZONE_MIX.get(archetype, (0.33, 0.33, 0.34))
    jump_occ = mid_occ + three_occ
    eff = ((mid_occ * mid_w + three_occ * three_w) / jump_occ
           if jump_occ > 0 else (mid_w + three_w) / 2)
    return round(sht * eff)


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
        # the SHOWN shooting rating (effective jumper threat, not the raw budget)
        "sht_disp": display_shooting(archetype, sht),
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
    "heat_check":     dict(name="Heat Check", cat="shooting", active=True,
                           desc="On a back-to-back make he heats up: shoots more often AND more accurately."),
    "quick_release":  dict(name="Quick Release", cat="shooting", active=True,
                           desc="Hard to contest; help defense arrives too late."),
    "corner_spec":    dict(name="Corner Specialist", cat="shooting", active=True,
                           desc="Big accuracy boost on threes taken from the corners."),
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
    "shot_blocker":   dict(name="Shot Blocker", cat="defense", active=True,
                           desc="Real chance to SWAT a nearby rim or midrange attempt."),
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
    "mentor":         dict(name="Mentor", cat="meta", active=True,
                           desc="Lifts teammates' accuracy — the longer they've played together, the more."),
    # --- negative / drawback ------------------------------------------------
    "turnover_prone": dict(name="Turnover Prone", cat="negative", active=True,
                           desc="Great scorer, but higher turnover risk."),
    "ball_stopper":   dict(name="Ball Stopper", cat="negative", active=True,
                           desc="Scores well but lowers teammates' offense."),
    "streaky":        dict(name="Streaky", cat="negative", active=True,
                           desc="Rides the wave — far more likely than most to repeat his last shot's outcome."),
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
MAX_TIER = 7
# tiers unlock by GAMES PLAYED (wins + losses), not wins — everyone progresses.
# Tier 7 (the "Legend" tier) unlocks deep into the 12-win championship run.
TIER_UNLOCK_GAMES = {1: 0, 2: 2, 3: 4, 4: 6, 5: 8, 6: 10, 7: 12}

# Price by tier (was a flat 3). Higher tiers cost more, so signing a legend is a
# real spend decision you may have to bank toward. Overrides the archetype cost.
TIER_PRICE = {1: 3, 2: 3, 3: 4, 4: 4, 5: 5, 6: 5, 7: 6}


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
    """How strong a random opponent may be: the top tier it can field. Bumped up
    a notch for the deeper 12-win run, topping out at the new Tier 7 late."""
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
    if round_no <= 12:
        return 6
    return 7


# Preset, PERSISTENT player pool. A name always maps to the same archetype and
# the same base stats every run, so reputations stick ("I rode Mike Fletcher to
# 10 wins, he averaged 30"). These base stats are the player's identity; signing
# and merging (level_up) are what improve them within a run.
#   (name, archetype, tier, sht, dfn, plm, ath, ability)
#   sht=Shooting, dfn=Defense, plm=Playmaking, ath=Athleticism (these four are the
#   shown ratings the sim reads directly — NOT off/dfn/pas/stl; see gen_pool.py).
_POOL_RAW = [
    # --- Tier 1 ---
    ('Dominic Vance', 'Scoring PG', 1, 8, 6, 4, 2, 'iso_threat'),
    ('Jake Reed', 'Scoring PG', 1, 7, 6, 6, 2, 'soft_touch'),
    ('Ryan Burns', 'Scoring PG', 1, 7, 6, 4, 2, 'handles'),
    ('Tobias Tate', 'Scoring PG', 1, 7, 4, 5, 3, 'iso_threat'),
    ('Aaron Pike', 'Slashing SF', 1, 4, 7, 2, 5, 'turnover_prone'),
    ('Davon Murray', 'Slashing SF', 1, 3, 6, 4, 6, 'iso_threat'),
    ('Noah Yates', 'Slashing SF', 1, 5, 8, 2, 7, 'eurostep'),
    ('Terry Ortega', 'Slashing SF', 1, 5, 7, 3, 7, 'soft_touch'),
    ('Lamar Flowers', 'Shooting SF', 1, 8, 8, 2, 2, 'deadeye'),
    ('Landon Frazier', 'Shooting SF', 1, 8, 6, 3, 3, 'deadeye'),
    ('Sam Mraz', 'Shooting SF', 1, 8, 6, 2, 2, 'catch_shoot'),
    ('Tobias Walker', 'Shooting SF', 1, 8, 7, 4, 2, 'catch_shoot'),
    ('Aaron Fisher', 'Rim-Run Big', 1, 2, 8, 3, 7, 'rim_protector'),
    ('Caleb Green', 'Rim-Run Big', 1, 2, 8, 2, 6, 'putback'),
    ('Cooper Fisher', 'Rim-Run Big', 1, 2, 7, 3, 8, 'lob_threat'),
    ('Keon Reyes', 'Rim-Run Big', 1, 3, 8, 2, 8, 'soft_touch'),
    ('Adrian Ward', 'Pass-First PG', 1, 2, 7, 8, 2, 'on_ball_menace'),
    ('Mike Fletcher', 'Pass-First PG', 1, 3, 7, 8, 2, 'tempo_control'),
    ('Sam Zima', 'Pass-First PG', 1, 4, 8, 8, 2, 'floor_general'),
    ('Silas Howard', 'Pass-First PG', 1, 3, 8, 8, 2, 'tempo_control'),
    ('Terry Hill', 'Pass-First PG', 1, 3, 8, 8, 2, 'tempo_control'),
    ('Carson Davis', 'Lockdown Wing', 1, 3, 8, 4, 2, 'on_ball_menace'),
    ('Kareem Dawson', 'Lockdown Wing', 1, 2, 8, 4, 2, 'on_ball_menace'),
    ('Nash Price', 'Lockdown Wing', 1, 3, 8, 3, 2, 'on_ball_menace'),
    ('Xavier Harris', 'Lockdown Wing', 1, 2, 8, 3, 2, 'on_ball_menace'),
    ('Donovan Long', '3&D Wing', 1, 5, 8, 2, 2, 'catch_shoot'),
    ('Hunter Warner', '3&D Wing', 1, 4, 8, 3, 2, 'deadeye'),
    ('Trent Stone', '3&D Wing', 1, 6, 8, 4, 2, 'catch_shoot'),
    ('Cooper Shaw', 'Stretch 4', 1, 8, 8, 4, 2, 'deadeye'),
    ('Jake Mills', 'Stretch 4', 1, 7, 8, 4, 2, 'deadeye'),
    ('Tariq Rice', 'Stretch 4', 1, 7, 7, 3, 2, 'catch_shoot'),
    ('Garrett Coleman', 'Point Forward', 1, 4, 6, 8, 3, 'iso_threat'),
    ('Jaden Booker', 'Point Forward', 1, 3, 5, 8, 3, 'floor_general'),
    ('Jose Jones', 'Point Forward', 1, 6, 6, 7, 4, 'handles'),
    ('Jabari Sims', 'Screening Big', 1, 2, 8, 4, 5, 'rim_protector'),
    ('Mark Udeze', 'Screening Big', 1, 2, 8, 4, 3, 'on_ball_menace'),
    ('Wes Taylor', 'Screening Big', 1, 2, 8, 4, 4, 'shot_blocker'),
    ('Dante Mathis', 'Combo Guard', 1, 8, 5, 6, 2, 'handles'),
    ('Landon Novak', 'Combo Guard', 1, 7, 6, 6, 3, 'handles'),
    ('Rome Simmons', 'Combo Guard', 1, 7, 6, 6, 2, 'deadeye'),
    ('Darius Washington', 'Sharpshooter', 1, 8, 8, 3, 2, 'quick_release'),
    ('Dawson Diallo', 'Sharpshooter', 1, 8, 8, 3, 2, 'corner_spec'),
    ('Marcus Wright', 'Sharpshooter', 1, 8, 7, 3, 3, 'quick_release'),
    ('Bradley Parker', 'Two-Way Forward', 1, 4, 8, 4, 3, 'on_ball_menace'),
    ('Dawson Jenkins', 'Two-Way Forward', 1, 3, 8, 4, 3, 'soft_touch'),
    ('Tobias Nelson', 'Two-Way Forward', 1, 4, 8, 4, 5, 'on_ball_menace'),
    ('Jack Ingram', 'Stretch Center', 1, 7, 7, 2, 2, 'catch_shoot'),
    ('Josh Sefu', 'Stretch Center', 1, 8, 8, 4, 3, 'catch_shoot'),
    ('Trevor Jenkins', 'Stretch Center', 1, 8, 8, 3, 2, 'rim_protector'),
    ('Devon Jenkins', 'Post Scorer', 1, 3, 7, 2, 6, 'ball_stopper'),
    ('Micah Locke', 'Post Scorer', 1, 5, 8, 2, 8, 'soft_touch'),
    ('Rell Porter', 'Post Scorer', 1, 4, 7, 3, 7, 'soft_touch'),
    ('Flynn Frazier', 'Defensive Anchor', 1, 2, 8, 3, 2, 'shot_blocker'),
    ('Landon Marsh', 'Defensive Anchor', 1, 2, 8, 2, 3, 'shot_blocker'),
    ('Quinn Hill', 'Defensive Anchor', 1, 2, 8, 4, 2, 'on_ball_menace'),
    # --- Tier 2 ---
    ('Bradley Turner', 'Scoring PG', 2, 11, 7, 7, 4, 'soft_touch'),
    ('Trevor Cook', 'Scoring PG', 2, 8, 6, 6, 2, 'limitless'),
    ('Zeke Simmons', 'Scoring PG', 2, 9, 5, 7, 2, 'heat_check'),
    ('Alec Shaw', 'Slashing SF', 2, 5, 10, 4, 8, 'iso_threat'),
    ('Dalton Voss', 'Slashing SF', 2, 5, 11, 4, 7, 'soft_touch'),
    ('Jett Griffin', 'Slashing SF', 2, 5, 9, 2, 8, 'killer_cross'),
    ('Cam Holt', 'Shooting SF', 2, 10, 9, 4, 3, 'limitless'),
    ('Kobi Norman', 'Shooting SF', 2, 11, 9, 4, 2, 'catch_shoot'),
    ('Mike Washington', 'Shooting SF', 2, 10, 9, 2, 2, 'deadeye'),
    ('Desmond Ward', 'Rim-Run Big', 2, 3, 11, 2, 9, 'putback'),
    ('Landon Pike', 'Rim-Run Big', 2, 2, 9, 3, 9, 'ball_stopper'),
    ('Will Lane', 'Rim-Run Big', 2, 3, 10, 2, 10, 'putback'),
    ('Corey Watson', 'Pass-First PG', 2, 4, 11, 11, 2, 'handles'),
    ('Damon Morris', 'Pass-First PG', 2, 2, 11, 11, 2, 'pickpocket'),
    ('Dillon Parker', 'Pass-First PG', 2, 2, 11, 11, 2, 'pickpocket'),
    ('Carson Johnson', 'Lockdown Wing', 2, 2, 11, 4, 2, 'lockdown'),
    ('Emmanuel Udeze', 'Lockdown Wing', 2, 2, 11, 3, 2, 'pickpocket'),
    ('Sam Washington', 'Lockdown Wing', 2, 2, 11, 5, 2, 'on_ball_menace'),
    ('Bradley Kemp', '3&D Wing', 2, 8, 11, 3, 3, 'quick_release'),
    ('Finn Brooks', '3&D Wing', 2, 7, 11, 3, 2, 'quick_release'),
    ('Theo Hall', '3&D Wing', 2, 8, 11, 4, 3, 'catch_shoot'),
    ('Harrison Crawford', 'Stretch 4', 2, 9, 9, 3, 3, 'catch_shoot'),
    ('Jacoby Peters', 'Stretch 4', 2, 11, 11, 4, 2, 'limitless'),
    ('Pax Collins', 'Stretch 4', 2, 11, 9, 5, 2, 'soft_touch'),
    ('Gabe Gordon', 'Point Forward', 2, 5, 7, 10, 2, 'handles'),
    ('Quentin Williams', 'Point Forward', 2, 6, 7, 10, 3, 'mentor'),
    ('Jimmy Whitlock', 'Screening Big', 2, 2, 11, 4, 5, 'ball_stopper'),
    ('Zeke Voss', 'Screening Big', 2, 2, 11, 4, 6, 'shot_blocker'),
    ('Jack Greer', 'Combo Guard', 2, 8, 8, 6, 2, 'handles'),
    ('Rome Roberts', 'Combo Guard', 2, 8, 7, 5, 4, 'heat_check'),
    ('Devon Mathis', 'Sharpshooter', 2, 11, 9, 5, 2, 'quick_release'),
    ('Quinn Tate', 'Sharpshooter', 2, 9, 7, 3, 2, 'deadeye'),
    ('Jared Brown', 'Two-Way Forward', 2, 3, 11, 3, 6, 'eurostep'),
    ('Rell Shaw', 'Two-Way Forward', 2, 4, 11, 3, 6, 'eurostep'),
    ('Jeremiah Green', 'Stretch Center', 2, 9, 11, 5, 3, 'limitless'),
    ('Noah Watson', 'Stretch Center', 2, 9, 8, 2, 2, 'catch_shoot'),
    ('Cam Gordon', 'Post Scorer', 2, 3, 9, 3, 7, 'ball_stopper'),
    ('Dante Taylor', 'Post Scorer', 2, 4, 10, 5, 9, 'soft_touch'),
    ('Isaac Sims', 'Defensive Anchor', 2, 2, 11, 3, 2, 'shot_blocker'),
    ('Travis Turner', 'Defensive Anchor', 2, 2, 11, 5, 4, 'ball_stopper'),
    # --- Tier 3 ---
    ('Brandon Henderson', 'Scoring PG', 3, 10, 8, 6, 2, 'turnover_prone'),
    ('Donovan Brown', 'Scoring PG', 3, 12, 6, 6, 3, 'turnover_prone'),
    ('Mateo Marsh', 'Scoring PG', 3, 12, 7, 8, 5, 'soft_touch'),
    ('Greg Tran', 'Slashing SF', 3, 7, 12, 6, 9, 'soft_touch'),
    ('Otis Sanders', 'Slashing SF', 3, 7, 10, 4, 9, 'eurostep'),
    ('Tobias Cruz', 'Slashing SF', 3, 6, 11, 5, 10, 'iso_threat'),
    ('Alec Mraz', 'Shooting SF', 3, 12, 9, 5, 2, 'limitless'),
    ('Vince Rogers', 'Shooting SF', 3, 12, 10, 3, 3, 'deadeye'),
    ('Xavier Rivera', 'Shooting SF', 3, 12, 11, 5, 4, 'deadeye'),
    ('Devon Murphy', 'Rim-Run Big', 3, 3, 12, 2, 10, 'putback'),
    ('Ryan Cruz', 'Rim-Run Big', 3, 2, 12, 4, 12, 'lob_threat'),
    ('Aaron Foster', 'Pass-First PG', 3, 3, 11, 12, 2, 'handles'),
    ('Logan Graham', 'Pass-First PG', 3, 4, 12, 12, 2, 'dimer'),
    ('Aaron King', 'Lockdown Wing', 3, 4, 12, 4, 2, 'pickpocket'),
    ('Darius Lane', 'Lockdown Wing', 3, 4, 12, 4, 2, 'lockdown'),
    ('Jett Foster', '3&D Wing', 3, 9, 12, 4, 3, 'corner_spec'),
    ('Lamar Freeman', '3&D Wing', 3, 7, 12, 4, 2, 'deadeye'),
    ('Amari Mack', 'Stretch 4', 3, 12, 11, 5, 2, 'catch_shoot'),
    ('Ryan Tate', 'Stretch 4', 3, 11, 9, 4, 3, 'soft_touch'),
    ('Hunter Glenn', 'Point Forward', 3, 7, 10, 9, 3, 'handles'),
    ('Kobi Lane', 'Point Forward', 3, 7, 10, 12, 3, 'dimer'),
    ('Aaron Wallace', 'Screening Big', 3, 2, 12, 5, 5, 'on_ball_menace'),
    ('Dominic Wright', 'Screening Big', 3, 2, 12, 6, 5, 'dream_shake'),
    ('Dante Graham', 'Combo Guard', 3, 9, 10, 7, 3, 'quick_release'),
    ('Dominic Ellis', 'Combo Guard', 3, 11, 8, 7, 3, 'iso_threat'),
    ('Davon Ross', 'Sharpshooter', 3, 12, 11, 3, 2, 'catch_shoot'),
    ('Silas Ingram', 'Sharpshooter', 3, 12, 11, 4, 2, 'catch_shoot'),
    ('Kevin Voss', 'Two-Way Forward', 3, 4, 12, 4, 7, 'pickpocket'),
    ('Kevin Wells', 'Two-Way Forward', 3, 4, 12, 5, 6, 'on_ball_menace'),
    ('Javon Udeze', 'Stretch Center', 3, 10, 12, 4, 5, 'limitless'),
    ('Quincy Novak', 'Stretch Center', 3, 10, 12, 5, 5, 'fan_favorite'),
    ('Cam Miller', 'Post Scorer', 3, 6, 11, 5, 10, 'dream_shake'),
    ('Derrick Dawson', 'Post Scorer', 3, 6, 11, 5, 10, 'putback'),
    ('Khalil Webb', 'Defensive Anchor', 3, 2, 12, 5, 4, 'rim_protector'),
    ('Ronnie Cook', 'Defensive Anchor', 3, 2, 12, 4, 4, 'interceptor'),
    # --- Tier 4 ---
    ('Brock Hayes', 'Scoring PG', 4, 13, 8, 9, 3, 'iso_threat'),
    ('Logan Payne', 'Scoring PG', 4, 12, 10, 8, 5, 'heat_check'),
    ('Sol Cruz', 'Slashing SF', 4, 6, 14, 5, 10, 'killer_cross'),
    ('Theo Jones', 'Slashing SF', 4, 5, 12, 4, 12, 'eurostep'),
    ('Bryce Bell', 'Shooting SF', 4, 15, 14, 6, 4, 'catch_shoot'),
    ('David Phillips', 'Shooting SF', 4, 15, 12, 5, 4, 'deadeye'),
    ('Rashad Ingram', 'Rim-Run Big', 4, 2, 15, 5, 13, 'dream_shake'),
    ('Russell Ellis', 'Rim-Run Big', 4, 2, 15, 4, 12, 'ball_stopper'),
    ('Brandon Hayes', 'Pass-First PG', 4, 4, 13, 14, 3, 'mentor'),
    ('Dante Green', 'Pass-First PG', 4, 4, 14, 15, 2, 'mentor'),
    ('Avery Kringle', 'Lockdown Wing', 4, 3, 15, 5, 2, 'on_ball_menace'),
    ('Troy Gray', 'Lockdown Wing', 4, 4, 15, 4, 2, 'interceptor'),
    ('Jaylon Flowers', '3&D Wing', 4, 10, 15, 4, 2, 'quick_release'),
    ('Tobias Haas', '3&D Wing', 4, 10, 15, 6, 4, 'catch_shoot'),
    ('Grant Yates', 'Stretch 4', 4, 13, 14, 4, 2, 'catch_shoot'),
    ('Ty Hall', 'Stretch 4', 4, 13, 13, 6, 3, 'catch_shoot'),
    ('Carson Bennett', 'Point Forward', 4, 7, 12, 13, 5, 'floor_general'),
    ('Joel Anderson', 'Point Forward', 4, 7, 12, 13, 5, 'tempo_control'),
    ('Damon Riley', 'Screening Big', 4, 2, 15, 6, 6, 'shot_blocker'),
    ('Kobi Banks', 'Combo Guard', 4, 12, 10, 9, 3, 'iso_threat'),
    ('Julian Davis', 'Sharpshooter', 4, 15, 13, 7, 2, 'limitless'),
    ('Jax Scott', 'Two-Way Forward', 4, 5, 15, 5, 7, 'lockdown'),
    ('Josh Bryant', 'Stretch Center', 4, 11, 14, 5, 3, 'catch_shoot'),
    ('Jaden Thomas', 'Post Scorer', 4, 6, 11, 4, 12, 'soft_touch'),
    ('Damian Thompson', 'Defensive Anchor', 4, 2, 15, 5, 5, 'shot_blocker'),
    # --- Tier 5 ---
    ('Vince Green', 'Scoring PG', 5, 14, 11, 11, 5, 'iso_threat'),
    ('Wes Bryant', 'Scoring PG', 5, 15, 10, 9, 6, 'soft_touch'),
    ('Ty Thomas', 'Slashing SF', 5, 9, 15, 6, 13, 'killer_cross'),
    ('Wes Norman', 'Slashing SF', 5, 6, 13, 7, 12, 'iso_threat'),
    ('Enzo Voss', 'Shooting SF', 5, 16, 14, 6, 2, 'catch_shoot'),
    ('Ryan Glenn', 'Shooting SF', 5, 16, 15, 6, 4, 'limitless'),
    ('Bryce Barnes', 'Rim-Run Big', 5, 4, 16, 3, 14, 'soft_touch'),
    ('Garrett Johnson', 'Rim-Run Big', 5, 3, 16, 5, 15, 'lob_threat'),
    ('Trent Morris', 'Pass-First PG', 5, 5, 14, 15, 2, 'dimer'),
    ('Micah Cruz', 'Lockdown Wing', 5, 6, 16, 7, 2, 'lockdown'),
    ('Harrison Hill', '3&D Wing', 5, 11, 16, 5, 3, 'quick_release'),
    ('Mark Adams', 'Stretch 4', 5, 16, 16, 6, 2, 'soft_touch'),
    ('Justin Long', 'Point Forward', 5, 9, 12, 15, 4, 'tempo_control'),
    ('Enzo Mack', 'Screening Big', 5, 3, 16, 8, 6, 'rim_protector'),
    ('Mark Kemp', 'Combo Guard', 5, 15, 11, 10, 5, 'iso_threat'),
    ('Jacoby Pike', 'Sharpshooter', 5, 16, 13, 7, 4, 'deadeye'),
    ('Tyler Pike', 'Two-Way Forward', 5, 7, 16, 5, 7, 'pickpocket'),
    ('Ben Campbell', 'Stretch Center', 5, 15, 16, 7, 6, 'deadeye'),
    ('Silas Wells', 'Post Scorer', 5, 7, 14, 5, 12, 'rim_protector'),
    ('Jacoby Johnson', 'Defensive Anchor', 5, 2, 16, 5, 4, 'shot_blocker'),
    # --- Tier 6 ---
    ('Juju Shaw', 'Scoring PG', 6, 17, 10, 11, 4, 'handles'),
    ('Alec Ferguson', 'Slashing SF', 6, 7, 18, 7, 14, 'soft_touch'),
    ('Terry Morgan', 'Shooting SF', 6, 18, 16, 8, 4, 'quick_release'),
    ('Ronnie Moore', 'Rim-Run Big', 6, 4, 18, 4, 16, 'putback'),
    ('Greg Sullivan', 'Pass-First PG', 6, 6, 18, 19, 4, 'tempo_control'),
    ('Avery Davis', 'Lockdown Wing', 6, 5, 20, 7, 2, 'pickpocket'),
    ('Henry Lamonet', 'Lockdown Wing', 6, 5, 20, 7, 2, 'lockdown'),
    ('Ben Stone', '3&D Wing', 6, 11, 20, 7, 4, 'deadeye'),
    ('Travis Powell', 'Stretch 4', 6, 17, 17, 7, 2, 'catch_shoot'),
    ('Enzo Thompson', 'Point Forward', 6, 9, 15, 15, 6, 'tempo_control'),
    ('Chris Graham', 'Screening Big', 6, 3, 20, 7, 7, 'ball_stopper'),
    ('Andre Moore', 'Combo Guard', 6, 15, 13, 12, 4, 'iso_threat'),
    ('Rell Perry', 'Sharpshooter', 6, 20, 16, 7, 2, 'deadeye'),
    ('Aaron Scott', 'Two-Way Forward', 6, 7, 20, 7, 10, 'eurostep'),
    ('Kai Fields', 'Stretch Center', 6, 16, 18, 7, 4, 'catch_shoot'),
    # --- Tier 7 ---
    ('Alec Howard', 'Scoring PG', 7, 20, 12, 12, 5, 'soft_touch'),
    ('Emmanuel Sims', 'Slashing SF', 7, 9, 19, 8, 15, 'eurostep'),
    ('Quincy Woods', 'Shooting SF', 7, 21, 19, 9, 4, 'deadeye'),
    ('Otis Ingram', 'Rim-Run Big', 7, 5, 21, 6, 18, 'soft_touch'),
    ('Jerry Sims', 'Pass-First PG', 7, 5, 20, 21, 4, 'tempo_control'),
    ('Jabari Perry', 'Lockdown Wing', 7, 6, 25, 7, 2, 'interceptor'),
    ('Jalen Ward', '3&D Wing', 7, 13, 25, 7, 3, 'corner_spec'),
    ('Rell Lewis', 'Stretch 4', 7, 21, 18, 8, 2, 'catch_shoot'),
    ('Nash Jenkins', 'Point Forward', 7, 12, 14, 18, 5, 'floor_general'),
    ('Dalton Greer', 'Screening Big', 7, 2, 25, 8, 10, 'rim_protector'),
]
POOL = [{"name": n, "archetype": a, "tier": t, "sht": sh, "dfn": d,
         "plm": pl, "ath": at, "ability": ab}
        for (n, a, t, sh, d, pl, at, ab) in _POOL_RAW]


# ---------------------------------------------------------------------------
# COMMENTARY — randomized basketball phrasing for the play-by-play
# ---------------------------------------------------------------------------
PASS_VERBS = ["dishes to", "kicks it out to", "finds", "swings it to", "feeds",
              "threads it to", "drops it off to", "hits", "lobs it to"]
STEAL_LINES = ["PICKED OFF by {d}!", "{d} jumps the lane for the STEAL!",
               "{d} reads it and takes it away!", "Stolen by {d}!",
               "{d} pickpockets him!", "{d} deflects and recovers it for a turnover!"]
MADE = {
    "layup": ["throws it DOWN!", "finishes at the rim", "lays it in off the glass",
              "slices to the cup for the bucket", "strong finish through contact",
              "rises up and flushes it", "scoops it in"],
    "midrange": ["knocks down the jumper", "pull-up is GOOD", "drains the mid-range",
                 "cashes the elbow jumper", "rises and fires for the money jumper"],
    "three": ["from way downtown, BANG!", "splashes the triple", "buries it from deep",
              "wet from beyond the arc", "drills the three", "lets it fly and GETS IT"],
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
                  "rises but {d} contests it, no good", "shoots over {d} and off the iron"]
BLOCK_LINES = ["is REJECTED by {d}!", "gets it SWATTED by {d}!",
               "has it sent back by {d}!", "is denied at the rim by {d}!",
               "{d} says NOT IN MY HOUSE — blocked!", "is pinned to the glass by {d}!"]
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
        "tenure": 0,                 # rounds played on your roster (drives Mentor)
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
        # opponents are a touch stronger now: a bit more likely to be leveled,
        # with the odd L3 star deep in the run (slightly-better CPU teams).
        roll = random.random()
        lvl = 2 if roll < 0.12 + 0.04 * round_no else 1
        if round_no >= 9 and roll < 0.12:
            lvl = 3
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


def live_defense(offense, mapping, off_pos, doubles=None, screen_lag=None):
    """Man-to-man defenders track their man's live (dribbled) spot; any doubling
    defender sits next to the player he traps so he counts as help. A defender in
    `screen_lag` is hung up on a screen and stays at that spot. id -> (x, y)."""
    pos = {}
    screen_lag = screen_lag or {}
    for o in offense:
        d = mapping.get(o["id"])
        if d:
            if d["id"] in screen_lag:          # caught on the pick — trailing the play
                pos[d["id"]] = screen_lag[d["id"]]
            else:
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


def _make_bonuses(offense):
    """Per-shooter make-% deltas from team chemistry abilities. Mentor lifts each
    teammate's accuracy, scaled by how long the two have shared the roster (the
    overlap of their tenures), capped by MENTOR_CAP. id -> make-% delta."""
    bonus = {p["id"]: 0.0 for p in offense}
    for m in offense:
        if m.get("ability") != "mentor":
            continue
        for q in offense:
            if q["id"] == m["id"]:
                continue
            together = min(m.get("tenure", 0), q.get("tenure", 0))
            bonus[q["id"]] = min(MENTOR_CAP, bonus[q["id"]] + MENTOR_PER * together)
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
            contrib = (d.get("d_steal", d["dfn"] * 0.5) / 10.0) * STEAL_LANE * (1 - sd / LANE_RANGE) * grab
            lane += contrib
            if contrib > worst:
                worst, culprit = contrib, d
    # the farther the pass travels, the easier it is to jump (steeper distance term)
    p = TO_BASE + TO_DIST * pd + lane - 0.02 * (passer["plm"] - 5)
    if passer.get("ability") == "handles":         # secure handle
        p *= 0.65
    if receiver.get("ability") == "turnover_prone": # risky to feed
        p *= 1.4
    p *= to_mult                                    # team-wide (e.g. Tempo Control)
    return _clamp(p, 0.02, TO_CAP), culprit


def _evaluate(shooter, defense, mapping, off_pos, def_pos,
              passer=None, off_pass=False, off_bonus=None, make_bonus=None):
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
    # Corner Specialist: deadly from the corners specifically (low + near a sideline)
    if (sab == "corner_spec" and shot == "three"
            and sp[1] <= CORNER_Y and abs(sp[0] - 50.0) >= (50.0 - CORNER_X)):
        bonus += CORNER_BONUS
    # Heat Check: while hot (back-to-back makes) his shot falls more often
    if sab == "heat_check" and shooter.get("_streak", 0) >= HEAT_STREAK:
        bonus += HEAT_BONUS
    # Streaky: nudged toward repeating his last outcome (hot stays hot, cold stays cold)
    if sab == "streaky" and shooter.get("_last_made") is not None:
        bonus += STREAK_SWING if shooter["_last_made"] else -STREAK_SWING

    off_adj = (off_bonus or {}).get(shooter["id"], 0)
    mentor_adj = (make_bonus or {}).get(shooter["id"], 0.0)   # tenure-scaled Mentor lift
    prob = _clamp(base + ZONE_COEFF * (zone_rating + off_adj - SCORE_REF) + bonus
                  + mentor_adj - contest - help_d - deep, 0.05, 0.96)
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


def _open_role_spot(p):
    """An off-ball teammate in the pass chain works to his role (anchor) spot to be
    an outlet — i.e. moves to GET the ball, not at random."""
    a = p["anchors"][0]
    return (a["x"], a["y"])


def _spacing_target(p, cur, ball_xy):
    """Floor spacing with purpose: if a player is crowding the ball-handler he
    slides AWAY from the ball toward open floor (biased to his role spot); if he is
    already well spaced he holds his spot (settling to his anchor only if he has
    drifted). No motion for motion's sake."""
    x, y = cur[p["id"]]
    ax, ay = p["anchors"][0]["x"], p["anchors"][0]["y"]
    if _dist((x, y), ball_xy) < CROWD_DIST:                 # too close to the ball
        dx, dy = x - ball_xy[0], y - ball_xy[1]
        d = math.hypot(dx, dy) or 1.0
        ox, oy = x + dx / d * SPACE_STEP, y + dy / d * SPACE_STEP   # step off the ball
        return ((ox + ax) / 2.0, (oy + ay) / 2.0)                  # ...toward open space
    if _dist((x, y), (ax, ay)) > 6.0:
        return (ax, ay)                                            # settle back to his spot
    return (x, y)                                                  # well spaced — stand still


def _pick_screener(offense, shooter, initiator):
    """The off-ball big who sets the screen: prefer true screen/roll bigs, else the
    biggest body; never the shooter or the ball-handler. None if nobody fits."""
    cands = [p for p in offense if p["id"] not in (shooter["id"], initiator["id"])
             and (p["behavior"] in SCREEN_BEHAVIORS or _reb(p) >= 7)]
    if not cands:
        return None
    cands.sort(key=lambda p: (p["behavior"] in SCREEN_BEHAVIORS, _reb(p)), reverse=True)
    return cands[0]


def _screen_spot(ox, oy):
    """Where the screener stands to set a CLEAN pick: just to one side of the
    defender (a distinct body beside the man, never stacked on top of him). The
    man he screens stays his own defender — exactly one screener per defender."""
    dx, dy = _defender_spot_xy(ox, oy)
    bx, by = BASKET
    vx, vy = dx - bx, dy - by
    d = math.hypot(vx, vy) or 1.0
    px, py = -vy / d, vx / d                       # unit perpendicular to basket->man
    side = 1.0 if dx >= 50.0 else -1.0             # lean toward the near sideline
    return (_clamp(dx + px * side * SCREEN_SIDE, 4, 96),
            _clamp(dy + py * side * SCREEN_SIDE, 4, 96))


def _trail_spot(sx, sy, px, py, gap):
    """A point `gap` units BEHIND the shooter, back toward where the screen was
    (px,py) — i.e. where his beaten defender trails as he bursts off the pick."""
    dx, dy = px - sx, py - sy
    d = math.hypot(dx, dy) or 1.0
    return (_clamp(sx + dx / d * gap, 4, 96), _clamp(sy + dy / d * gap, 4, 96))


def _relocate_off_screen(shot_spot, pick_spot):
    """The freed shooter relocates LATERALLY off the pick — same shot distance, but
    he runs to open space on the side away from the screen, so he is visibly moving
    when his man trails. Keeps his shot zone (a three stays a three)."""
    sx, sy = shot_spot
    bx, by = BASKET
    vx, vy = sx - bx, sy - by
    d = math.hypot(vx, vy) or 1.0
    px, py = -vy / d, vx / d                       # unit perpendicular (along the arc)
    kx, ky = pick_spot[0] - sx, pick_spot[1] - sy  # which lateral side the screen is on
    side = 1.0 if (kx * px + ky * py) > 0 else -1.0   # relocate TOWARD the screen
    return (_clamp(sx + px * side * SCREEN_RELOCATE, 6, 94),
            _clamp(sy + py * side * SCREEN_RELOCATE, 6, 94))


def _screener_step(p, cur, roles, screen_state):
    """Screener path by phase: APPROACH = hustle beside the shooter's defender;
    HOLD = stay planted on the pick (don't move); ROLL = roll to the rim (or pop to
    the arc if a stretch big)."""
    phase = screen_state.get("phase", "approach")
    if phase == "approach":
        sp = _screen_spot(*cur[roles["screen_target"]])
        return (sp[0], sp[1], MOVE_STEP * SCREEN_APPROACH)   # hustle to the pick
    if phase == "hold":
        return (cur[p["id"]][0], cur[p["id"]][1], 0.0)       # plant — hold the screen
    if p["behavior"] == "spot_up" or "Stretch" in p["archetype"]:
        tx, ty = _shot_target("spot_up", *cur[p["id"]])      # pop to the arc
    else:
        tx, ty = BASKET[0], BASKET[1] + 8                    # roll to the rim
    return (tx, ty, MOVE_STEP)


def _advance(offense, cur, roles, screen_state):
    """One frame of PURPOSEFUL motion. Each player moves toward an intent: the
    shooter curls to his shot spot; a screener goes to set the pick then rolls/pops;
    chain passers work to an outlet spot; everyone else spaces the floor (slides off
    the ball or stands still). Returns id -> (x, y)."""
    ball_xy = cur[roles["handler"]]
    nxt = {}
    for p in offense:
        pid = p["id"]
        if pid == roles["shooter"]:
            if roles["screener"] and not screen_state.get("set"):
                tx, ty, step = (cur[pid][0], cur[pid][1], 0.0)   # wait to use the screen
            else:                                                # burst off the screen
                burst = SHOOTER_BURST if roles["screener"] else 1.0
                tx, ty, step = (*roles["shot_spot"], MOVE_STEP * burst)
        elif roles["screener"] and pid == roles["screener"]:
            tx, ty, step = _screener_step(p, cur, roles, screen_state)
        elif pid in roles["chain"]:
            tx, ty, step = (*_open_role_spot(p), MOVE_STEP * 0.7)
        else:
            tx, ty, step = (*_spacing_target(p, cur, ball_xy), MOVE_STEP * 0.8)
        nxt[pid] = _step_toward(cur[pid][0], cur[pid][1], tx, ty, step)
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


# --- shot-diet calibration (wires ARCHETYPE_ZONE_MIX into shot selection) -----
# Each candidate shooter's selection EV is biased by how characteristic his shot
# ZONE is for his archetype (ARCHETYPE_ZONE_MIX, from 2015-16 tracking). Because
# ZONE_MIX is OCCUPANCY (where players stand), not attempts, ZONE_CAL corrects it
# to the real league ATTEMPT mix (2015-16 ~33% three / paint-heavy). SHOT_FUNNEL
# replaces the old ev**4 over-funnel — softer so the shot diet, not raw EV, leads.
ZONE_IDX = {"layup": 0, "midrange": 1, "three": 2}
ZONE_CAL = (2.0, 2.0, 0.40)   # rim, mid, three attempt multipliers (tuned to ~33% 3PA)
SHOT_FUNNEL = 3


def _predicted_zone(player, setup_pos):
    """The zone the player would actually shoot from after working to his spot
    (spot-ups step out behind the arc, cutters/rollers drive in)."""
    sx, sy = setup_pos
    tx, ty = _shot_target(player["behavior"], sx, sy)
    spot = _step_toward(sx, sy, tx, ty, SHOT_STEP)
    return shot_from_distance(_dist(spot, BASKET))[0]


def _shot_blocker(shooter, look, defense, mapping, off_pos, def_pos):
    """Does a Shot Blocker swat this attempt? Only rim (and, rarely, midrange) shots
    can be blocked. The shooter's man counts if he has the ability; so does any
    Shot Blocker helping within HELP_RANGE. Returns the blocking defender or None."""
    shot = look["shot"]
    if shot == "three":
        return None
    sp = off_pos[shooter["id"]]
    man = look.get("man")
    cands = []
    if man and man.get("ability") == "shot_blocker" and man["id"] in def_pos:
        cands.append(man)
    for od in defense:
        if od.get("ability") != "shot_blocker" or od["id"] not in def_pos:
            continue
        if man and od["id"] == man["id"]:
            continue
        if _dist(def_pos[od["id"]], sp) < HELP_RANGE:
            cands.append(od)
    best = None
    for d in cands:
        chance = (d.get("d_block", d["dfn"] * 0.5)) * BLOCK_SCALE
        if shot == "midrange":
            chance *= BLOCK_MID
        if random.random() < _clamp(chance, 0.0, 0.6):
            best = d
            break
    return best


def run_possession(offense, defense, mapping, doubles=None, off_bonus=None, to_mult=1.0,
                   make_bonus=None):
    """One possession: players drift into the play (setup), the team picks the
    best developing look, then that action is executed with justified movement —
    the shooter moves to get the shot, the passer steps in to deliver it.
    `off_bonus`/`to_mult`/`make_bonus` carry team-wide ability effects. Returns
    (points, events, setup_layout, shot_layout)."""
    events = []
    if not offense:
        miss = [{"kind": "miss", "text": "Empty lineup, no shot.",
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
                         passer=initiator, off_pass=passing_opt, off_bonus=off_bonus,
                         make_bonus=make_bonus)
        to_p, culprit = (0.0, None)
        if passing_opt:
            to_p, culprit = _pass_risk(initiator, s, defense, setup, def_setup, to_mult)
        # data-derived shot diet: bias by how characteristic this shot zone is for
        # the archetype (ARCHETYPE_ZONE_MIX), calibrated to real attempts (ZONE_CAL).
        zone = _predicted_zone(s, setup[s["id"]])
        zmix = ARCHETYPE_ZONE_MIX.get(s["archetype"])
        zfreq = max(0.02, zmix[ZONE_IDX[zone]] if zmix else 0.33) * ZONE_CAL[ZONE_IDX[zone]]
        # Heat Check: when he's hot, the offense looks for him far more often
        heat = (HEAT_SELECT if s.get("ability") == "heat_check"
                and s.get("_streak", 0) >= HEAT_STREAK else 1.0)
        # favor the open man + the archetype's shooting tendency + shot diet
        ev = (look["prob"] * look["pts"] * (1 - to_p)
              * _open_factor(s, look, mapping) * _tend(s, "shoot") * zfreq * heat)
        options.append((s, ev))
    weights = [max(0.0001, ev) ** SHOT_FUNNEL for _, ev in options]
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

    # --- decide a screen: a big frees the shooter with a pick (fairly common) ---
    screener = (_pick_screener(offense, shooter, initiator)
                if random.random() < SCREEN_CHANCE else None)
    man = mapping.get(shooter["id"])
    if screener and man:                           # the freed man relocates off the pick
        shot_spot = _relocate_off_screen(shot_spot, _screen_spot(*setup[shooter["id"]]))
    roles = {
        "shooter": shooter["id"], "shot_spot": shot_spot,
        "screener": screener["id"] if screener else None,
        "screen_target": shooter["id"],            # the pick frees the shooter
        "chain": {p["id"] for p in chain[:-1]},    # the passers (not the shooter)
        "handler": initiator["id"],
    }
    screen_state = {"set": False, "phase": "approach", "pick": None}
    screen_lag = {}                                # the one hung-up defender -> his spot
    cur = dict(setup)
    screened = False

    def _frame(kind="move", **extra):
        """Emit one motion frame (smooth intermediate position) + optional event."""
        cur_def = live_defense(offense, mapping, cur, doubles, screen_lag)
        ev = {"kind": kind, "actor": None, "target": None, "points": 0,
              "layout": possession_layout(offense, defense, cur, cur_def), "text": None}
        ev.update(extra)
        events.append(ev)
        return cur_def

    def _trail():
        """Once the screen is set, the beaten defender TRAILS behind the bursting
        shooter (he fell behind coming off the pick) instead of tracking him."""
        if screened and man:
            screen_lag[man["id"]] = _trail_spot(*cur[shooter["id"]],
                                                *screen_state["pick"], TRAIL_GAP)

    # 1) develop the play — everyone moves with purpose (a screened shooter waits)
    for _ in range(DEVELOP_FRAMES):
        cur = _advance(offense, cur, roles, screen_state)
        _frame("move")

    # 2) the big hustles beside the pick; the screen is "set" only once he ACTUALLY
    #    reaches the shooter's defender. Exactly ONE screener screens ONE defender.
    if screener and man:
        for _ in range(SCREEN_MAX_FRAMES):
            cur = _advance(offense, cur, roles, screen_state)
            if _dist(cur[screener["id"]], _screen_spot(*cur[shooter["id"]])) <= SCREEN_SET_DIST:
                break
            _frame("move")
        # SET the pick: the shooter runs his man INTO the screener, who hangs him up
        screened = True
        screen_state["set"] = True
        screen_state["phase"] = "hold"
        screen_state["pick"] = tuple(cur[screener["id"]])    # the screen location
        screen_lag[man["id"]] = tuple(cur[screener["id"]])   # the man runs into the screen
        _frame("screen", actor=screener["id"], target=shooter["id"],
               text=f"   {screener['name']} sets a screen for {shooter['name']}")
        # 2b) HOLD: the big stays planted; the shooter bursts; the man falls behind
        for _ in range(SCREEN_HOLD_FRAMES):
            cur = _advance(offense, cur, roles, screen_state)
            _trail()
            _frame("move")
        screen_state["phase"] = "roll"             # now the big can roll or pop

    # 3) swing the ball through the chain (a settle frame before each pass)
    for i in range(len(chain) - 1):
        frm, to = chain[i], chain[i + 1]
        roles["handler"] = frm["id"]
        for _ in range(PASS_FRAMES):
            cur = _advance(offense, cur, roles, screen_state)
            _trail()
            _frame("move")
        _trail()
        cur_def = live_defense(offense, mapping, cur, doubles, screen_lag)
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
        roles["handler"] = to["id"]

    # 4) the shooter curls to his spot (the screen frees him) — smooth frames
    roles["handler"] = shooter["id"]
    for _ in range(PRESHOT_FRAMES):
        cur = _advance(offense, cur, roles, screen_state)
        _trail()
        _frame("move")
    cur[shooter["id"]] = shot_spot
    _trail()
    cur_def = live_defense(offense, mapping, cur, doubles, screen_lag)
    shot_layout = possession_layout(offense, defense, cur, cur_def)
    look = _evaluate(shooter, defense, mapping, cur, cur_def,
                     passer=(chain[-2] if passing else None), off_pass=passing,
                     off_bonus=off_bonus, make_bonus=make_bonus)
    if screened:                                   # a clean screen = a cleaner look
        look["prob"] = _clamp(look["prob"] + SCREEN_OPEN, 0.05, 0.97)
    contest_def = look["man"]["id"] if look["man"] else None
    made = random.random() < look["prob"]

    # --- Shot Blocker: a nearby rim protector with the ability can SWAT it -------
    blocker = _shot_blocker(shooter, look, defense, mapping, cur, cur_def)
    if blocker is not None and made:
        made = False
    if blocker is not None:
        contest_def = blocker["id"]
        text = f"{shooter['name']} " + random.choice(BLOCK_LINES).format(d=blocker["name"])
    else:
        text = _shot_text(shooter, look["shot"], made, look["man"],
                          look["pressure"], look["pts"])
    pts = look["pts"] if made else 0
    # Heat Check / Streaky bookkeeping: the shooter's running outcome state
    if made:
        shooter["_streak"] = shooter.get("_streak", 0) + 1
    else:
        shooter["_streak"] = 0
    shooter["_last_made"] = made
    events.append({
        "kind": "made" if made else "miss", "actor": shooter["id"],
        "target": contest_def, "points": pts, "shot": look["shot"],
        "blocked": blocker is not None, "layout": shot_layout, "text": text,
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
    make_bonus = _make_bonuses(offense)
    to_mult = 0.85 if any(p.get("ability") == "tempo_control" for p in offense) else 1.0
    poss_list, total = [], 0
    for _ in range(possessions):
        pts, evs, setup_layout, shot_layout, handler = run_possession(
            offense, defense, mapping, doubles, off_bonus, to_mult, make_bonus)
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
                    # assist: the last real pass before a make (skip motion frames)
                    j = i - 1
                    while j >= 0 and evs[j]["kind"] in ("move", "screen"):
                        j -= 1
                    if j >= 0 and evs[j]["kind"] == "pass" and evs[j].get("target") == a:
                        pa = evs[j].get("actor")
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
    you_mb, opp_mb = _make_bonuses(you), _make_bonuses(opp)
    you_to = 0.85 if any(p.get("ability") == "tempo_control" for p in you) else 1.0
    opp_to = 0.85 if any(p.get("ability") == "tempo_control" for p in opp) else 1.0

    def trip(off, dfn, mp, db, ob, to, mb):
        pts, evs, sl, shl, h = run_possession(off, dfn, mp, db, ob, to, mb)
        return pts, {"points": pts, "events": evs, "handler": h,
                     "layout": sl, "shot_layout": shl, "ot": True}

    yposs, oposs = [], []
    order = ["you", "opp"] if you_first else ["opp", "you"]
    for _ in range(20):                       # cap guards against an endless tie
        for side in order:
            if side == "you":
                pts, poss = trip(you, opp, you_map, you_dbl, you_ob, you_to, you_mb)
                yposs.append(poss)
                if pts > 0:
                    return "win", yposs, oposs
            else:
                pts, poss = trip(opp, you, opp_map, opp_dbl, opp_ob, opp_to, opp_mb)
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
TIER_SELL = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4}


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
