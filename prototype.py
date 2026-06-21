"""
Basketball Auto-Battler - throwaway prototype (text play-by-play).

Purpose: test ONE thing - is "build a lineup, then watch it score" fun and
self-diagnosing? No art, no animation, no real economy depth. Everything here
is meant to be thrown away; the numbers are all tunable knobs at the top.

Run:  python prototype.py
"""

import random
import sys

# ---------------------------------------------------------------------------
# TUNABLE KNOBS  (all of this will change - that's the point)
# ---------------------------------------------------------------------------
POSSESSIONS_PER_SIDE = 5     # per round, each team gets this many possessions
LINEUP_SIZE = 5             # court slots
SHOP_SIZE = 5               # players offered each build phase
STARTING_CAP = 20           # "cap space" budget you start with
CAP_PER_ROUND = 6           # cap gained each round to spend
WINS_TO_FINISH = 10         # race to this many wins...
LOSSES_TO_BUST = 3          # ...eliminated at this many losses
SCALE_PER_ROUND = 0.04      # opponent strength creep per round
SEED = None                 # set an int for reproducible runs

# Shot base make-chance before ratings/contest/openness modifiers
BASE_LAYUP = 0.55
BASE_THREE = 0.36
BASE_MIDRANGE = 0.42

# ---------------------------------------------------------------------------
# ARCHETYPES - each carries a behavior policy, not just stats.
#   off / def / pass / steal  : ratings 1-10 (tunable per generated player)
#   behavior                  : what this player TRIES to do on offense
# ---------------------------------------------------------------------------
ARCHETYPES = {
    "Pass-First PG": dict(cost=3, spacing=1, behavior="distribute",
                          base=dict(off=4, dfn=4, pas=8, stl=5)),
    "Scoring PG":    dict(cost=3, spacing=1, behavior="pull_up",
                          base=dict(off=6, dfn=3, pas=5, stl=4)),
    "Slashing SF":   dict(cost=3, spacing=0, behavior="cut",
                          base=dict(off=6, dfn=5, pas=4, stl=4)),
    "Shooting SF":   dict(cost=3, spacing=2, behavior="spot_up",
                          base=dict(off=6, dfn=4, pas=3, stl=3)),
    "Stretch 4":     dict(cost=3, spacing=2, behavior="spot_up",
                          base=dict(off=5, dfn=4, pas=3, stl=2)),
    "Screening Big": dict(cost=3, spacing=0, behavior="screen",
                          base=dict(off=4, dfn=7, pas=4, stl=2)),
    "Rim-Run Big":   dict(cost=3, spacing=0, behavior="roll",
                          base=dict(off=6, dfn=6, pas=2, stl=2)),
    "Lockdown Wing": dict(cost=3, spacing=1, behavior="spot_up",
                          base=dict(off=4, dfn=8, pas=3, stl=7)),
}

NAMES_FIRST = ["Ace", "Bryce", "Cam", "Dre", "Eli", "Finn", "Gabe", "Hank",
               "Iggy", "Jax", "Kobe-ish", "Lonzo-ish", "Marv", "Nash", "Omar"]
NAMES_LAST = ["Quicks", "Rivera", "Stone", "Tate", "Underwood", "Vance",
              "Webb", "Xiong", "York", "Zane", "Booker", "Cross", "Dunn"]


class Player:
    def __init__(self, archetype, level=1):
        a = ARCHETYPES[archetype]
        self.archetype = archetype
        self.behavior = a["behavior"]
        self.spacing = a["spacing"]
        self.cost = a["cost"]
        self.level = level
        # small random spread + level bump so duplicates feel meaningfully better
        self.off = self._roll(a["base"]["off"])
        self.dfn = self._roll(a["base"]["dfn"])
        self.pas = self._roll(a["base"]["pas"])
        self.stl = self._roll(a["base"]["stl"])
        self.name = f"{random.choice(NAMES_FIRST)} {random.choice(NAMES_LAST)}"

    def _roll(self, base):
        return min(10, base + random.randint(-1, 1) + (self.level - 1) * 2)

    def scaled(self, mult):
        """Return a copy with ratings scaled (for opponent difficulty creep)."""
        p = Player.__new__(Player)
        p.__dict__.update(self.__dict__)
        p.off = min(12, round(self.off * mult))
        p.dfn = min(12, round(self.dfn * mult))
        p.pas = min(12, round(self.pas * mult))
        p.stl = min(12, round(self.stl * mult))
        return p

    def short(self):
        return (f"{self.name:<16} L{self.level} {self.archetype:<14} "
                f"off{self.off} def{self.dfn} pas{self.pas} stl{self.stl}")


# ---------------------------------------------------------------------------
# SIM
# ---------------------------------------------------------------------------
def team_spacing(team):
    """Floor spacing from shooters/stretch - opens driving lanes for everyone."""
    return sum(p.spacing for p in team)


def pick_defender(offense_player, defense):
    """Crude positional matchup: best remaining defender guards the threat."""
    return max(defense, key=lambda d: d.dfn)


def run_possession(offense, defense, log):
    """Resolve one possession. Returns points scored. Appends play-by-play."""
    spacing = team_spacing(offense)
    openness = min(0.18, 0.03 * spacing)  # more spacing = more open looks

    # Who initiates? Prefer a true PG, else best passer.
    initiator = max(offense, key=lambda p: p.pas)
    defender = pick_defender(initiator, defense)

    # Did a screen get set this possession? (screener present + a cutter/roller)
    screener = next((p for p in offense if p.behavior == "screen"), None)
    cutter = next((p for p in offense if p.behavior in ("cut", "roll")), None)
    screen_freed = False
    if screener and cutter and random.random() < 0.6:
        screen_freed = True
        log.append(f"    {screener.name} sets a screen - {cutter.name} slips free!")

    # Turnover check on the initiating pass (pass-first PGs feed others a lot)
    if initiator.behavior == "distribute":
        steal_chance = max(0.04, 0.05 + 0.03 * (defender.stl - initiator.pas))
        if random.random() < steal_chance:
            log.append(f"    {initiator.name}'s pass is STOLEN by {defender.name}! Turnover.")
            return 0

    # Decide the shot taker + shot type from behaviors
    shooters = [p for p in offense if p.behavior == "spot_up"]
    if screen_freed:
        taker, shot, why = cutter, "layup", f"off the screen"
    elif initiator.behavior == "distribute" and shooters:
        taker, shot, why = random.choice(shooters), "three", f"fed by {initiator.name}"
    elif initiator.behavior == "pull_up":
        taker, shot, why = initiator, "midrange", "pulls up"
    else:
        slasher = next((p for p in offense if p.behavior == "cut"), None)
        if slasher:
            taker, shot, why = slasher, "layup", "drives the lane"
        elif shooters:
            taker, shot, why = random.choice(shooters), "three", "spot-up look"
        else:
            taker, shot, why = initiator, "midrange", "settles for a jumper"

    contest = pick_defender(taker, defense)
    base = {"layup": BASE_LAYUP, "three": BASE_THREE, "midrange": BASE_MIDRANGE}[shot]
    make = base + 0.03 * (taker.off - contest.dfn) + openness
    make = max(0.05, min(0.92, make))

    pts = 3 if shot == "three" else 2
    if random.random() < make:
        log.append(f"    {taker.name} {why} - {'3PT' if pts==3 else '2PT'} GOOD ({pts})")
        return pts
    else:
        log.append(f"    {taker.name} {why} - MISS (contested by {contest.name})")
        return 0


def play_round(player_team, opp_team, round_no):
    print(f"\n{'='*60}\n  ROUND {round_no} - TIP-OFF\n{'='*60}")
    you_log, opp_log = [], []
    you_pts = sum(run_possession(player_team, opp_team, you_log)
                  for _ in range(POSSESSIONS_PER_SIDE))
    opp_pts = sum(run_possession(opp_team, player_team, opp_log)
                  for _ in range(POSSESSIONS_PER_SIDE))

    print("\n  >> YOUR POSSESSIONS")
    print("\n".join(you_log))
    print("\n  >> OPPONENT POSSESSIONS")
    print("\n".join(opp_log))

    print(f"\n  FINAL: You {you_pts} - {opp_pts} Opponent")
    if you_pts == opp_pts:  # tiebreak: defense wins
        you_d = sum(p.dfn for p in player_team)
        opp_d = sum(p.dfn for p in opp_team)
        print(f"  Tie! Defense breaks it ({you_d} vs {opp_d}).")
        return you_d >= opp_d
    return you_pts > opp_pts


def random_team(round_no):
    mult = 1.0 + SCALE_PER_ROUND * round_no
    keys = list(ARCHETYPES)
    team = [Player(random.choice(keys),
                   level=1 + (1 if random.random() < 0.15 + 0.03 * round_no else 0))
            for _ in range(LINEUP_SIZE)]
    return [p.scaled(mult) for p in team]


# ---------------------------------------------------------------------------
# BUILD PHASE  (deliberately minimal - just enough to make a lineup)
# ---------------------------------------------------------------------------
def build_phase(lineup, cap, round_no):
    print(f"\n{'#'*60}\n  BUILD PHASE - Round {round_no}   Cap space: {cap}\n{'#'*60}")
    if lineup:
        print("\n  Your lineup:")
        for i, p in enumerate(lineup):
            print(f"    [{i}] {p.short()}")
        print(f"  Floor spacing: {team_spacing(lineup)}  (more = more open looks)")

    shop = [Player(random.choice(list(ARCHETYPES))) for _ in range(SHOP_SIZE)]
    print("\n  MARKET (buy with cap space):")
    for i, p in enumerate(shop):
        print(f"    ({i}) cost {p.cost}  {p.short()}")

    print("\n  Commands: buy <shop#> | sell <lineup#> | done")
    while True:
        try:
            raw = input("  > ").strip().lower()
        except EOFError:
            return lineup, cap
        if raw in ("done", "d", ""):
            if len(lineup) <= LINEUP_SIZE:
                break
            print(f"  Too many players - sell down to {LINEUP_SIZE}.")
            continue
        parts = raw.split()
        if parts[0] == "buy" and len(parts) == 2 and parts[1].isdigit():
            i = int(parts[1])
            if 0 <= i < len(shop) and shop[i] is not None:
                if len(lineup) >= LINEUP_SIZE:
                    print("  Lineup full - sell someone first.")
                elif shop[i].cost > cap:
                    print("  Not enough cap.")
                else:
                    cap -= shop[i].cost
                    # auto-merge: 3 of same archetype+level => level up
                    lineup.append(shop[i])
                    lineup = try_merge(lineup)
                    shop[i] = None
                    print(f"  Bought. Cap left: {cap}")
            else:
                print("  Bad shop index.")
        elif parts[0] == "sell" and len(parts) == 2 and parts[1].isdigit():
            i = int(parts[1])
            if 0 <= i < len(lineup):
                cap += max(1, lineup[i].cost - 1)
                print(f"  Sold {lineup[i].name}. Cap: {cap}")
                lineup.pop(i)
            else:
                print("  Bad lineup index.")
        else:
            print("  ?  use: buy <#> | sell <#> | done")
    return lineup, cap


def try_merge(lineup):
    """3 same archetype + same level -> 1 of next level (TFT-style)."""
    from collections import defaultdict
    groups = defaultdict(list)
    for p in lineup:
        groups[(p.archetype, p.level)].append(p)
    for (arch, lvl), members in groups.items():
        if len(members) >= 3:
            for m in members[:3]:
                lineup.remove(m)
            leveled = Player(arch, level=lvl + 1)
            lineup.append(leveled)
            print(f"  *** MERGE! {arch} leveled up to L{lvl+1}: {leveled.name}")
            return try_merge(lineup)
    return lineup


# ---------------------------------------------------------------------------
# RUN LOOP
# ---------------------------------------------------------------------------
def main():
    if SEED is not None:
        random.seed(SEED)
    print("BASKETBALL AUTO-BATTLER - prototype")
    print(f"Race to {WINS_TO_FINISH} wins. Eliminated at {LOSSES_TO_BUST} losses.\n")

    lineup, cap = [], STARTING_CAP
    wins = losses = 0
    round_no = 1
    while wins < WINS_TO_FINISH and losses < LOSSES_TO_BUST:
        cap += CAP_PER_ROUND if round_no > 1 else 0
        lineup, cap = build_phase(lineup, cap, round_no)
        if len(lineup) < LINEUP_SIZE:
            print(f"\n  (You have {len(lineup)}/{LINEUP_SIZE} players - "
                  f"empty slots hurt your spacing & matchups.)")
        opp = random_team(round_no)
        won = play_round(lineup, opp, round_no)
        if won:
            wins += 1
            print(f"  [WIN]  WIN.  Record: {wins}W-{losses}L")
        else:
            losses += 1
            print(f"  [LOSS] LOSS. Record: {wins}W-{losses}L")
        round_no += 1

    print(f"\n{'='*60}")
    if wins >= WINS_TO_FINISH:
        print(f"  >>> YOU MADE THE FINALS with {wins}W-{losses}L! (finals = TODO)")
    else:
        print(f"  Run over. Busted at {wins}W-{losses}L.")
    print('='*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
