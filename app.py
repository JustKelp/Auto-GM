"""
Basketball Auto-Battler — web prototype (Flask host).

The server is the rules authority; the browser is a pure view. Run state
(lineup, cap, record, shop) is a plain JSON dict that travels with each
request, so the server stays stateless — same shape as the other projects
here. All game logic lives in sim.py.

Run:
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000
"""

import copy
import json
import os
import random
import uuid


import sim
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# SAVED TEAMS — every round a player's lineup (with positions) is saved keyed by
# round number, and future opponents are drawn from these real past teams in the
# SAME round (SAP-style async snapshots). This is how the pool "learns" where to
# put players: opponents reuse real human placements. Persisted to teams.json.
# ---------------------------------------------------------------------------
SNAP_FILE = os.path.join(os.path.dirname(__file__), "teams.json")
SNAP_MAX_PER_ROUND = 40         # keep the most recent N teams per round
SNAPSHOT_CHANCE = 0.6           # chance to face a saved team when one exists


def _load_snaps():
    try:
        with open(SNAP_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


SNAPSHOTS = _load_snaps()       # {"<round>": [{"lineup": [...]}, ...]}


def _save_snaps():
    try:
        with open(SNAP_FILE, "w", encoding="utf-8") as f:
            json.dump(SNAPSHOTS, f)
    except Exception:
        pass


def save_team(round_no, lineup):
    """Stash a snapshot of the lineup (positions included) for this round."""
    if len([p for p in lineup if p]) < 4:      # only save worthwhile teams
        return
    lst = SNAPSHOTS.setdefault(str(round_no), [])
    lst.append({"lineup": copy.deepcopy(lineup)})
    del lst[:-SNAP_MAX_PER_ROUND]
    _save_snaps()


def pick_opponent(round_no):
    """Face a saved human team from the same round when available, else a bot.
    Returns (opponent_lineup, source)."""
    pool = SNAPSHOTS.get(str(round_no)) or []
    if pool and random.random() < SNAPSHOT_CHANCE:
        opp = copy.deepcopy(random.choice(pool)["lineup"])
        for p in opp:
            p["id"] = uuid.uuid4().hex[:8]     # fresh ids to avoid collisions
        return opp, "past team"
    return sim.random_team(round_no), "bot"


def fresh_state():
    return {
        "lineup": [],
        "cap": sim.STARTING_CAP,
        "wins": 0,
        "losses": 0,
        "pushes": 0,
        "games": 0,          # games played (drives tier unlocks); pushes count
        "round": 1,
        "shop": sim.make_shop(0),
        "phase": "build",
        "finals": False,        # True once you've qualified — next game is the Finals
    }


@app.route("/")
def index():
    return render_template("index.html",
                           lineup_size=sim.LINEUP_SIZE,
                           wins_to_finish=sim.WINS_TO_FINISH,
                           losses_to_bust=sim.LOSSES_TO_BUST,
                           reroll_cost=sim.REROLL_COST,
                           tier_unlock=sim.TIER_UNLOCK_GAMES,
                           max_tier=sim.MAX_TIER,
                           chemistry=sim.CHEMISTRY)


@app.route("/api/start", methods=["POST"])
def start():
    return jsonify({"state": fresh_state(), "log": ["New run. Build your lineup."]})


@app.route("/api/buy", methods=["POST"])
def buy():
    data = request.get_json(force=True)
    state, idx = data["state"], data["index"]
    slot = data.get("slot")
    shop = state["shop"]
    if not (0 <= idx < len(shop)) or shop[idx] is None:
        return jsonify({"state": state, "log": ["Nothing to sign there."]})
    player = shop[idx]
    if slot not in player["positions"]:
        lbls = "/".join(sim.POSITION_LABELS[s] for s in player["positions"])
        return jsonify({"state": state,
                        "log": [f"{player['archetype']} can only play {lbls}."]})

    occupant = next((p for p in state["lineup"] if p.get("slot") == slot), None)
    if occupant:
        # SAP leveling: same archetype merges to level up; otherwise the slot's full
        if occupant["archetype"] != player["archetype"]:
            return jsonify({"state": state,
                            "log": [f"The {sim.POSITION_LABELS[slot]} slot is filled "
                                    f"(only a {occupant['archetype']} can merge here)."]})
        if occupant["level"] >= sim.MAX_LEVEL:
            return jsonify({"state": state,
                            "log": [f"{occupant['name']} is already max level (L{sim.MAX_LEVEL})."]})
        if player["cost"] > state["cap"]:
            return jsonify({"state": state, "log": ["Not enough cap space."]})
        state["cap"] -= player["cost"]
        _, leveled = sim.level_up(occupant, player)
        if leveled:
            # SAP-style reward: this slot rolls a card from the next tier you
            # have NOT unlocked yet (an early look at higher-tier talent)
            games = state.get("games", state["wins"] + state["losses"])
            nxt = sim.next_unlock(games)
            tier = nxt[0] if nxt else sim.MAX_TIER
            shop[idx] = sim.roll_from_tier(tier)
            extra = shop[idx]
            msg = (f"Leveled up {occupant['name']} to L{occupant['level']}!"
                   + (f" A locked Tier {extra['tier']} free agent appears!" if extra else ""))
        else:
            shop[idx] = None
            need = sim.xp_to_next(occupant)
            msg = (f"{occupant['name']} absorbs {player['name']} "
                   f"— {need} more to L{occupant['level'] + 1}.")
        return jsonify({"state": state, "log": [msg]})

    if player["cost"] > state["cap"]:
        return jsonify({"state": state, "log": ["Not enough cap space."]})
    state["cap"] -= player["cost"]
    player["slot"] = slot
    state["lineup"].append(player)
    shop[idx] = None
    sim.ensure_positions(state["lineup"])
    return jsonify({"state": state,
                    "log": [f"Signed {player['name']} at "
                            f"{sim.POSITION_LABELS[slot]}."]})


@app.route("/api/sell", methods=["POST"])
def sell():
    data = request.get_json(force=True)
    state, idx = data["state"], data["index"]
    if not (0 <= idx < len(state["lineup"])):
        return jsonify({"state": state, "log": ["No such player."]})
    p = state["lineup"].pop(idx)
    refund = sim.sell_refund(p)
    state["cap"] += refund
    return jsonify({"state": state, "log": [f"Released {p['name']} (+{refund} cap)."]})


@app.route("/api/move", methods=["POST"])
def move():
    """Re-slot a player already in the lineup. Dropping onto an empty eligible
    slot moves them; onto a SAME-archetype teammate combines (that teammate
    absorbs this one for XP/level); onto a different teammate swaps slots if both
    are eligible for the other's position."""
    data = request.get_json(force=True)
    state, pid, slot = data["state"], data["id"], data["slot"]
    lineup = state["lineup"]
    src = next((p for p in lineup if p["id"] == pid), None)
    if src is None:
        return jsonify({"state": state, "log": ["No such player."]})
    if slot not in src["positions"]:
        lbls = "/".join(sim.POSITION_LABELS[s] for s in src["positions"])
        return jsonify({"state": state, "log": [f"{src['archetype']} can only play {lbls}."]})

    occ = next((p for p in lineup if p.get("slot") == slot and p["id"] != pid), None)
    if occ is None:                                     # move into an empty slot
        src["slot"] = slot
        msg = f"Moved {src['name']} to {sim.POSITION_LABELS[slot]}."
    elif occ["archetype"] == src["archetype"]:          # combine to level up
        if occ["level"] >= sim.MAX_LEVEL:
            return jsonify({"state": state,
                            "log": [f"{occ['name']} is already max level (L{sim.MAX_LEVEL})."]})
        _, leveled = sim.level_up(occ, src)
        lineup.remove(src)
        msg = (f"Combined {src['name']} into {occ['name']} — leveled up to L{occ['level']}!"
               if leveled else
               f"{occ['name']} absorbs {src['name']} — {sim.xp_to_next(occ)} more to L{occ['level'] + 1}.")
    elif src.get("slot") in occ["positions"]:           # swap two players' slots
        occ["slot"], src["slot"] = src.get("slot"), slot
        msg = f"Swapped {src['name']} and {occ['name']}."
    else:
        return jsonify({"state": state,
                        "log": [f"{occ['archetype']} can't play {sim.POSITION_LABELS[src.get('slot')]}."]})
    sim.ensure_positions(lineup)
    return jsonify({"state": state, "log": [msg]})


@app.route("/api/reorder", methods=["POST"])
def reorder():
    """Frontend sends the lineup in a new slot order; we just accept it."""
    data = request.get_json(force=True)
    state = data["state"]
    state["lineup"] = data["lineup"]
    return jsonify({"state": state, "log": []})


@app.route("/api/reroll", methods=["POST"])
def reroll():
    data = request.get_json(force=True)
    state = data["state"]
    if state["cap"] < sim.REROLL_COST:
        return jsonify({"state": state, "log": ["Not enough cap to reroll."]})
    state["cap"] -= sim.REROLL_COST
    games = state["wins"] + state["losses"]
    state["shop"] = sim.refresh_shop(state["shop"], games)
    return jsonify({"state": state, "log": [f"Rerolled market (-{sim.REROLL_COST})."]})


@app.route("/api/play", methods=["POST"])
def play():
    data = request.get_json(force=True)
    state = data["state"]
    clash = sim.overlapping_ids(state["lineup"])
    if clash:
        return jsonify({"state": state, "error": "overlap", "conflicts": clash,
                        "log": ["Players are stacked — separate them before tip-off."]})
    played_round = state["round"]
    is_finals = bool(state.get("finals"))
    if is_finals:
        opponent, opp_source = sim.finals_opponent(), "finals"
    else:
        opponent, opp_source = pick_opponent(played_round)
    result = sim.play_round(state["lineup"], opponent, finals=is_finals)
    result["opponent"] = opponent
    result["opp_source"] = opp_source
    result["is_finals"] = is_finals

    # save this lineup (with positions) so it can be a future opponent (not the Finals)
    if not is_finals:
        save_team(played_round, state["lineup"])

    games_before = state.get("games", state["wins"] + state["losses"])
    before = set(sim.unlocked_tiers(games_before))
    verdict = result["verdict"]
    if verdict == "win":
        state["wins"] += 1
    elif verdict == "loss":
        state["losses"] += 1
    else:                                   # push — no effect on the record
        state["pushes"] = state.get("pushes", 0) + 1
    state["games"] = games_before + 1       # a push still counts as a game played
    new_tiers = [t for t in sim.unlocked_tiers(state["games"]) if t not in before]
    result["unlocked_tier"] = new_tiers[0] if new_tiers else None

    def _advance_build():
        """Roll into the next build phase: round up, pay cap income + interest,
        refresh the market."""
        state["round"] += 1
        state["cap"] += sim.cap_income(state["lineup"]) + sim.interest(state["cap"])
        state["shop"] = sim.refresh_shop(state["shop"], state["games"])

    if is_finals:
        # the championship game — the run ends crowned or as runner-up
        state["phase"] = "over"
        state["finals"] = False
        result["game_over"] = True
        result["outcome"] = "champion" if verdict == "win" else "runner-up"
    elif state["losses"] >= sim.LOSSES_TO_BUST:
        state["phase"] = "over"
        result["game_over"] = True
        result["outcome"] = "busted"
    elif state["wins"] >= sim.WINS_TO_FINISH:
        # qualified! one more build, then the Finals game
        state["finals"] = True
        result["game_over"] = False
        result["made_finals"] = True
        _advance_build()
    else:
        result["game_over"] = False
        _advance_build()

    return jsonify({"state": state, "result": result})


if __name__ == "__main__":
    # local dev entry point; in production gunicorn serves `app:app` (see Procfile)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=bool(os.environ.get("FLASK_DEBUG")))
