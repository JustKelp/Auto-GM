"use strict";
const body = document.body;
const LINEUP_SIZE = +body.dataset.lineupSize;
const WINS_GOAL = +body.dataset.wins || 12;     // wins to clinch the Finals
const LOSS_LIMIT = +body.dataset.losses || 4;   // losses that eliminate you
const STEP_MS = 1150;          // playback pace (higher = slower)
const PASS_PAUSE = 430;        // beat held after a pass (shorter = snappier ball movement)
const MIN_SEP = 11;            // must match sim.MIN_SEP (overlap threshold)

const POS_LABELS = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"};
const TIER_UNLOCK = JSON.parse(body.dataset.tiers || "{}");   // {tier: winsNeeded}
const MAX_TIER = +body.dataset.maxTier || 4;
const MAX_LEVEL = 3;
const XP_FOR_LEVEL = {2: 2, 3: 5};        // copies absorbed to reach each level (SAP)
const XP_START = {1: 0, 2: 2, 3: 5};      // xp at the start of each level
const CHEM = JSON.parse(body.dataset.chem || "[]");   // archetype duos/trios
const GEM = {1: "Bronze", 2: "Emerald", 3: "Sapphire", 4: "Amethyst", 5: "Ruby", 6: "Diamond"};

// which chemistry combos a team currently fields (mirrors sim._match_combo)
function computeChem(team) {
  const active = [];
  for (const c of CHEM) {
    const used = new Set();
    let ok = true;
    for (const a of c.archetypes) {
      const pick = team.find((p) => p.archetype === a && !used.has(p.id));
      if (!pick) { ok = false; break; }
      used.add(pick.id);
    }
    if (ok) active.push(c);
  }
  return active;
}
function chemHTML(team) {
  const act = computeChem(team);
  if (!act.length)
    return `<div class="chem-empty">No synergy yet — pair archetypes for +1 all stats.</div>`;
  return act.map((c) =>
    `<div class="chem ${c.kind}" title="${c.desc}  (+1 all stats to members)">`
    + `<span class="ck">${c.kind === "trio" ? "TRIO" : "DUO"}</span>`
    + `<span class="cn">${c.name}</span>`
    + `<span class="cd">${c.archetypes.length}</span></div>`).join("");
}

// id -> { duo:bool, trio:bool, names:[...] } for active combos on this team
function chemMemberMap(team) {
  const map = {};
  for (const c of CHEM) {
    const used = new Set();
    const members = [];
    let ok = true;
    for (const a of c.archetypes) {
      const pick = team.find((p) => p.archetype === a && !used.has(p.id));
      if (!pick) { ok = false; break; }
      used.add(pick.id); members.push(pick.id);
    }
    if (ok) for (const id of members) {
      const m = map[id] || (map[id] = {duo: false, trio: false, names: []});
      m[c.kind] = true; m.names.push(c.name);
    }
  }
  return map;
}
let chemMap = {};   // merged member map for whatever teams are on screen
function buildChemMap(...teams) {
  chemMap = {};
  for (const t of teams) Object.assign(chemMap, chemMemberMap(t));
}
// small ◆ duo / ▲ trio badges for a player id
function chemMark(id) {
  const m = chemMap[id];
  if (!m) return "";
  const tip = m.names.join(" · ");
  return (m.duo ? `<span class="cmark duo" title="${tip}">◆</span>` : "")
    + (m.trio ? `<span class="cmark trio" title="${tip}">▲</span>` : "");
}

// clear level badge for the team panel ("L2", gold pill, progress in the tooltip)
function levelBadge(p) {
  const lvl = p.level || 1;
  const max = lvl >= MAX_LEVEL;
  let tip = `Level ${lvl}`;
  if (max) {
    tip += " (max)";
  } else {
    const need = XP_FOR_LEVEL[lvl + 1] - (p.xp || 0);
    tip += ` — ${need} more cop${need === 1 ? "y" : "ies"} to L${lvl + 1}`;
  }
  return `<span class="lvl-badge${max ? " max" : ""}" title="${tip}">L${lvl}</span>`;
}

// visual level bar for a player card: a filling bar at the top + level pip
function levelBar(p) {
  const lvl = p.level || 1;
  if (lvl >= MAX_LEVEL) {
    return `<div class="lvlbar max" title="Max level (L${MAX_LEVEL})">`
      + `<i style="width:100%"></i><span class="lp">L${lvl}</span></div>`;
  }
  const start = XP_START[lvl], need = XP_FOR_LEVEL[lvl + 1];
  const pct = Math.max(0, Math.min(100, ((p.xp || 0) - start) / (need - start) * 100));
  const left = need - (p.xp || 0);
  return `<div class="lvlbar" title="L${lvl} — ${left} more to L${lvl + 1}">`
    + `<i style="width:${pct}%"></i><span class="lp">L${lvl}</span></div>`;
}

let state = null;
let busy = false;
let pendingResult = null;      // last game's result, held while the box score is up
let conflicts = new Set();     // ids of overlapping players (block the round)
let draggedShop = null;        // shop index currently being dragged
let draggedLineup = null;      // id of a signed player being re-slotted
let playersById = {};          // id -> player (for rendering during playback)

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload || {}),
  });
  return res.json();
}

// --------------------------------------------------------------- token render
function makeToken(player, x, y, mine, draggable) {
  const el = document.createElement("div");
  el.className = "token " + (mine ? "mine" : "opp");
  el.dataset.id = player.id;
  el.style.left = x + "%";
  el.style.top = y + "%";
  const posLabel = POS_LABELS[player.slot] || player.abbr;
  const parts = player.name.split(" ");          // show the SHORTER of first / last name
  const last = parts[parts.length - 1];
  const courtName = (parts[0].length <= last.length ? parts[0] : last).toUpperCase();
  el.innerHTML =
    `<div class="disc">${posLabel}<span class="lvl">${player.level}</span></div>
     <div class="nm">${courtName}${chemMark(player.id)}</div>`;
  el.title = `${player.name} — ${player.archetype} (${posLabel})\n`
    + `SHT ${player.sht}  DEF ${player.dfn}  PLM ${player.plm}  ATH ${player.ath}`
    + (player.ability_name ? `\n✦ ${player.ability_name}` : "");
  if (draggable) enableDrag(el, player);
  return el;
}

function clearTokens() {
  $("court").querySelectorAll(".token").forEach((t) => t.remove());
}

// build phase: your lineup at their chosen spots, draggable
function renderBuild() {
  clearTokens();
  hideBall();
  const court = $("court");
  state.lineup.forEach((p) => {
    court.appendChild(makeToken(p, p.pos.x, p.pos.y, true, true));
  });
  validate();
}

// flag overlapping players red and block the round until they're separated
function validate() {
  conflicts = new Set();
  const L = state.lineup;
  for (let i = 0; i < L.length; i++) {
    for (let j = i + 1; j < L.length; j++) {
      const d = Math.hypot(L[i].pos.x - L[j].pos.x, L[i].pos.y - L[j].pos.y);
      if (d < MIN_SEP) { conflicts.add(L[i].id); conflicts.add(L[j].id); }
    }
  }
  document.querySelectorAll("#court .token.mine").forEach((el) => {
    el.classList.toggle("conflict", conflicts.has(el.dataset.id));
  });
  const sn = $("spacing-note");
  if (sn) sn.textContent = conflicts.size ? "⚠ players are stacked" : "";
  updatePlayButton();
}

function updatePlayButton() {
  $("play").disabled = busy || conflicts.size > 0 || state.phase === "over";
}

// playback: create all ten tokens once at their placed spots, then move them
function spawnPlaybackTokens() {
  clearTokens();
  const court = $("court");
  const myIds = new Set(state.lineup.map((p) => p.id));
  Object.values(playersById).forEach((p) => {
    const x = p.pos ? p.pos.x : 50, y = p.pos ? p.pos.y : 50;
    court.appendChild(makeToken(p, x, y, myIds.has(p.id), false));
  });
}

// glide existing tokens to a possession's positions (the dribble)
function moveTokens(layout) {
  [...layout.offense, ...layout.defense].forEach((e) => {
    const el = document.querySelector(`#court .token[data-id="${e.id}"]`);
    if (el) { el.style.left = e.x + "%"; el.style.top = e.y + "%"; }
  });
}

function posLookup(layout) {
  const m = {};
  [...layout.offense, ...layout.defense].forEach((e) => m[e.id] = {x: e.x, y: e.y});
  return m;
}

function getBall() {
  let b = document.getElementById("ball");
  if (!b) { b = document.createElement("div"); b.id = "ball"; b.className = "ball";
            $("court").appendChild(b); }
  return b;
}
function ballTo(p, opts = {}) {
  const b = getBall();
  if (!p) { b.style.display = "none"; return; }
  b.style.display = "block";
  if (opts.instant) b.style.transition = "none";
  b.style.left = p.x + "%"; b.style.top = p.y + "%";
  b.classList.toggle("shot", !!opts.shot);
  b.classList.toggle("made", !!opts.made);
  if (opts.instant) { void b.offsetWidth; b.style.transition = ""; }
}
function hideBall() { const b = document.getElementById("ball"); if (b) b.style.display = "none"; }
function flashHoop() {
  const h = $("hoop");
  if (!h) return;
  h.classList.add("score");
  setTimeout(() => h.classList.remove("score"), 650);
}

function spacingNote() {
  const L = state.lineup;
  if (L.length < 2) return "";
  let total = 0;
  for (const a of L) {
    let near = Infinity;
    for (const b of L) if (a !== b) {
      const d = Math.hypot(a.pos.x - b.pos.x, a.pos.y - b.pos.y);
      if (d < near) near = d;
    }
    total += near;
  }
  const avg = total / L.length;
  const tag = avg > 22 ? "great" : avg > 14 ? "okay" : "cramped";
  return `· spacing: ${tag} (spread out to beat help defense)`;
}

// ------------------------------------------------------------------- drag
function enableDrag(el, player) {
  let moved = false, sx = 0, sy = 0;
  el.addEventListener("pointerdown", (e) => {
    if (busy) return;
    e.preventDefault();
    moved = false; sx = e.clientX; sy = e.clientY;
    el.setPointerCapture(e.pointerId);
    el.classList.add("dragging");
  });
  const offCourt = (e) => {            // is the pointer outside the court?
    const r = $("court").getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right
        || e.clientY < r.top || e.clientY > r.bottom;
  };
  el.addEventListener("pointermove", (e) => {
    if (!el.classList.contains("dragging")) return;
    if (Math.abs(e.clientX - sx) > 3 || Math.abs(e.clientY - sy) > 3) moved = true;
    const r = $("court").getBoundingClientRect();
    const x = clamp(((e.clientX - r.left) / r.width) * 100, 4, 96);
    const y = clamp(((e.clientY - r.top) / r.height) * 100, 4, 96);
    el.style.left = x + "%"; el.style.top = y + "%";
    player.pos = {x, y};        // free placement — drop anywhere on the court
    el.classList.toggle("release-zone", offCourt(e));  // cue: drop here = release
    validate();                 // live red glow if it overlaps a teammate
  });
  el.addEventListener("pointerup", async (e) => {
    if (!el.classList.contains("dragging")) return;
    el.classList.remove("dragging", "release-zone");
    // dragged OFF the court = release; a plain click does nothing now
    if (moved && offCourt(e)) { sell(player.id); return; }
    if (!moved) return;
    validate();
    await api("/api/reorder", {state, lineup: state.lineup});  // persist positions
  });
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// ---------------------------------------------------------------------------
// Unified pointer drag (MOUSE + TOUCH) for shop cards & lineup rows onto the
// YOUR-TEAM slots. Replaces HTML5 drag-and-drop, which mobile browsers don't
// fire on touch. A "ghost" follows the finger; the slot under it highlights;
// releasing over a valid slot runs the action. A no-move release is a tap.
// ---------------------------------------------------------------------------
let pdrag = null;

function makeGhost(text) {
  const g = document.createElement("div");
  g.className = "drag-ghost";
  g.textContent = text;
  document.body.appendChild(g);
  return g;
}
function slotAtPoint(x, y) {
  const el = document.elementFromPoint(x, y);
  const slot = el && el.closest("#posbar .slot");
  return slot ? +slot.dataset.slot : null;
}
function setSlotOver(s, on) {
  if (s == null) return;
  const el = document.querySelector(`#posbar .slot[data-slot="${s}"]`);
  if (el) el.classList.toggle("over", on);
}

let pdragScroll = null;          // auto-scroll timer while dragging near an edge

// recompute which slot is under the finger and update the highlight
function pdragUpdateOver() {
  if (!pdrag || !pdrag.moved) return;
  const raw = slotAtPoint(pdrag.lastX, pdrag.lastY);
  const valid = (raw != null && pdrag.cfg.canDrop(raw)) ? raw : null;
  if (valid !== pdrag.over) {
    setSlotOver(pdrag.over, false);
    setSlotOver(valid, true);
    pdrag.over = valid;
  }
}
// while dragging near the top/bottom of the screen, scroll the page (mobile:
// lets you drag a shop card up to the team even when they're far apart)
function pdragAutoScroll() {
  if (!pdrag || !pdrag.moved) return;
  const y = pdrag.lastY, h = window.innerHeight, edge = 72;
  let dy = 0;
  if (y < edge) dy = -Math.ceil((edge - y) / 5) - 2;
  else if (y > h - edge) dy = Math.ceil((y - (h - edge)) / 5) + 2;
  if (dy) { window.scrollBy(0, dy); pdragUpdateOver(); }
}

// cfg: { label, begin(), end(), canDrop(slot), onDrop(slot), onTap?() }
function attachPointerDrag(el, cfg) {
  el.addEventListener("pointerdown", (e) => {
    if (busy || (e.pointerType === "mouse" && e.button !== 0)) return;
    if (e.target.closest("button")) return;          // buttons keep their own tap
    pdrag = {pid: e.pointerId, sx: e.clientX, sy: e.clientY,
             lastX: e.clientX, lastY: e.clientY,
             moved: false, ghost: null, over: null, cfg, el};
    try { el.setPointerCapture(e.pointerId); } catch (_) {}
  });
  el.addEventListener("pointermove", (e) => {
    if (!pdrag || pdrag.pid !== e.pointerId) return;
    if (!pdrag.moved) {
      const dx = e.clientX - pdrag.sx, dy = e.clientY - pdrag.sy;
      if (Math.hypot(dx, dy) < 6) return;
      // vLock (shop cards): a sideways swipe scrolls the row instead of dragging;
      // only a clearly vertical drag picks the card up to sign it.
      if (cfg.vLock && Math.abs(dx) > Math.abs(dy)) {
        try { el.releasePointerCapture(pdrag.pid); } catch (_) {}
        pdrag = null;
        return;
      }
      pdrag.moved = true;
      cfg.begin();
      pdrag.ghost = makeGhost(cfg.label);
      el.classList.add("drag-src");
      pdragScroll = setInterval(pdragAutoScroll, 16);
    }
    e.preventDefault();
    pdrag.lastX = e.clientX; pdrag.lastY = e.clientY;
    pdrag.ghost.style.left = e.clientX + "px";
    pdrag.ghost.style.top = e.clientY + "px";
    pdragUpdateOver();
  });
  const finish = (e) => {
    if (!pdrag || pdrag.pid !== e.pointerId) return;
    const d = pdrag; pdrag = null;
    if (pdragScroll) { clearInterval(pdragScroll); pdragScroll = null; }
    try { d.el.releasePointerCapture(e.pointerId); } catch (_) {}
    d.el.classList.remove("drag-src");
    if (d.ghost) d.ghost.remove();
    setSlotOver(d.over, false);
    if (!d.moved) { if (cfg.onTap) cfg.onTap(); return; }
    cfg.end();
    if (d.over != null) cfg.onDrop(d.over);
  };
  el.addEventListener("pointerup", finish);
  el.addEventListener("pointercancel", finish);
}

// ------------------------------------------------------------------- panels
function render() {
  $("record").textContent = `${state.wins}W – ${state.losses}L`;
  $("cap").textContent = state.cap;
  $("round-label").textContent = state.finals ? "🏆 FINALS" : `Round ${state.round}`;
  $("phase-label").textContent = state.phase === "over" ? "Run over"
    : state.finals ? "FINALS — build your champion" : "Build phase";
  showFinalsLogo(!!state.finals);
  showClock(false);               // clock only runs during a game
  buildChemMap(state.lineup);     // duo/trio membership for indicators
  renderBuild();
  renderPosbar();
  renderShop();
  renderUnlockNote();
  hideOppPanel();          // opponent roster only shows during a game
}

// market header hint: which tier unlocks next, by GAMES PLAYED
function renderUnlockNote() {
  const el = $("unlock-note");
  if (!el) return;
  const games = state.games != null ? state.games : (state.wins + state.losses);
  let nextT = null, need = 0;
  for (let t = 1; t <= MAX_TIER; t++) {
    if (games < TIER_UNLOCK[t]) { nextT = t; need = TIER_UNLOCK[t]; break; }
  }
  el.textContent = nextT
    ? `· Tier ${nextT} unlocks at ${need} games (${need - games} more)`
    : "· all tiers unlocked";
}

const usedSlots = () => new Set(state.lineup.map((p) => p.slot));

// colour-coded attributes (OFF red · DEF blue · PAS green · STL gold)
function statHTML(p) {
  return `<span class="st sht">SHT <b>${p.sht}</b></span>`
    + `<span class="st def">DEF <b>${p.dfn}</b></span>`
    + `<span class="st plm">PLM <b>${p.plm}</b></span>`
    + `<span class="st ath">ATH <b>${p.ath}</b></span>`;
}
function totalsHTML(team) {
  const s = (k) => team.reduce((a, p) => a + p[k], 0);
  return `<span class="st sht">SHT <b>${s("sht")}</b></span>`
    + `<span class="st def">DEF <b>${s("dfn")}</b></span>`
    + `<span class="st plm">PLM <b>${s("plm")}</b></span>`
    + `<span class="st ath">ATH <b>${s("ath")}</b></span>`;
}

// returns "sign" (empty eligible slot), "merge" (same-archetype occupant), or null
function slotAction(slot) {
  if (draggedShop == null) return null;
  const p = state.shop[draggedShop];
  if (!p) return null;
  const occ = state.lineup.find((pl) => pl.slot === slot);
  if (occ) return (occ.archetype === p.archetype && occ.level < MAX_LEVEL) ? "merge" : null;
  return p.positions.includes(slot) ? "sign" : null;
}
function canDrop(slot) { return slotAction(slot) != null; }

// can the player currently dragged FROM the lineup drop on this slot?
// (empty eligible = move · same archetype = combine · else swap if both eligible)
function lineupDrop(slot) {
  if (draggedLineup == null) return false;
  const src = state.lineup.find((p) => p.id === draggedLineup);
  if (!src || src.slot === slot) return false;
  if (!src.positions.includes(slot)) return false;
  const occ = state.lineup.find((p) => p.slot === slot && p.id !== src.id);
  if (!occ) return true;
  if (occ.archetype === src.archetype) return occ.level < MAX_LEVEL;   // combine
  return occ.positions.includes(src.slot);                            // swap
}
async function moveLineup(id, slot) {
  const r = await api("/api/move", {state, id, slot});
  state = r.state; render(); logLines(r.log);
}
function highlightLineup(player, on) {
  document.querySelectorAll("#posbar .slot").forEach((el) => {
    const s = +el.dataset.slot;
    if (!on || !lineupDrop(s)) { el.classList.remove("eligible", "mergeable"); return; }
    const occ = state.lineup.find((q) => q.slot === s && q.id !== player.id);
    el.classList.toggle("mergeable", !!occ && occ.archetype === player.archetype);
    el.classList.toggle("eligible", !occ || occ.archetype !== player.archetype);
  });
}

// the side bar: your team — positions 1-5 with archetype + stats, drop targets,
// and a team-totals footer. Stays visible the whole time.
function renderPosbar() {
  const bar = $("posbar");
  bar.innerHTML = '<div class="panel-head">YOUR TEAM</div>';
  for (let s = 1; s <= 5; s++) {
    const slot = document.createElement("div");
    slot.className = "slot";
    slot.dataset.slot = s;
    const p = state.lineup.find((pl) => pl.slot === s);
    slot.className = "slot" + (p ? " t" + (p.tier || 1) : "");
    slot.innerHTML = (p ? levelBar(p) : "")
      + `<div class="pos">${s} · ${POS_LABELS[s]}`
      + (p ? ` <span class="tier t${p.tier || 1}" title="Tier ${p.tier || 1} (${GEM[p.tier]})">T${p.tier || 1}</span>` : "")
      + `</div>` + (p
      ? `<div class="filled">
           <div class="who"><b>${p.name} ${chemMark(p.id)}</b>
             <span class="arch">${levelBadge(p)} ${p.archetype}</span>
             <span class="abil">✦ ${p.ability_name || "—"}</span></div>
           <button class="x" title="release">✕</button></div>
         <div class="statline">${statHTML(p)}</div>`
      : `<div class="empty">drop a ${POS_LABELS[s]} here</div>`);
    if (p) {
      slot.querySelector(".x").onclick = () => !busy && sell(p.id);
      const filled = slot.querySelector(".filled");      // drag a signed player to re-slot/combine
      attachPointerDrag(filled, {
        label: p.name,
        begin: () => { draggedLineup = p.id; highlightLineup(p, true); },
        end:   () => { draggedLineup = null; highlightLineup(p, false); },
        canDrop: (sl) => lineupDrop(sl),
        onDrop: (sl) => moveLineup(p.id, sl),
      });
    }
    bar.appendChild(slot);
  }
  const tot = document.createElement("div");
  tot.className = "team-tot";
  tot.innerHTML = totalsHTML(state.lineup);
  bar.appendChild(tot);

  const chem = document.createElement("div");
  chem.className = "chem-box";
  chem.innerHTML = `<div class="panel-head">CHEMISTRY</div>${chemHTML(state.lineup)}`;
  bar.appendChild(chem);
}

// opponent roster on the other side, shown during a game
function renderOppPanel(opponent, source) {
  const el = $("opp-panel");
  const rows = [...opponent].sort((a, b) => a.slot - b.slot).map((p) =>
    `<div class="orow">
       <div class="oinfo">
         <b>${POS_LABELS[p.slot]} · ${p.name} ${chemMark(p.id)}</b>
         <span class="osub">${p.archetype}${p.level > 1 ? " ·L" + p.level : ""} · ✦ ${p.ability_name || "—"}</span>
       </div>
       <div class="statline">${statHTML(p)}</div>
     </div>`).join("");
  el.innerHTML = `<h3>OPPONENT</h3>${rows}`
    + `<div class="chem-box">${chemHTML(opponent)}</div>`;
  el.classList.remove("hidden");
}
function hideOppPanel() { $("opp-panel").classList.add("hidden"); }

function highlightSlots(on) {
  document.querySelectorAll("#posbar .slot").forEach((el) => {
    const a = on ? slotAction(+el.dataset.slot) : null;
    el.classList.toggle("eligible", a === "sign");
    el.classList.toggle("mergeable", a === "merge");
  });
}

function renderShop() {
  const shop = $("shop");
  shop.innerHTML = "";
  state.shop.forEach((p, i) => {
    const card = document.createElement("div");
    if (!p) { card.className = "card sold"; card.innerHTML = "<i>signed ✓</i>"; }
    else {
      card.className = "card t" + (p.tier || 1) + (p.frozen ? " frozen" : "");
      const pos = p.positions.map((s) => POS_LABELS[s]).join("/");
      const zone = {distribute: "up top", pull_up: "midrange", cut: "the rim",
        roll: "the rim", screen: "the rim", spot_up: "the arc"}[p.behavior];
      card.innerHTML =
        `<div class="chead">
           <div class="cmeta"><b class="nm">${p.name}</b>
             <span class="sub">${pos} · ${p.archetype}</span></div>
           <button class="freeze" title="Freeze — hold through reroll &amp; the next round">❄</button>
           <span class="tier t${p.tier || 1}" title="Tier ${p.tier || 1} (${GEM[p.tier]})">T${p.tier || 1}</span>
         </div>
         <div class="statline">${statHTML(p)}</div>
         <div class="cfoot"><span class="abil">✦ ${p.ability_name || "—"}</span>
           <span class="cost" title="cap cost">$${p.cost}</span></div>
         <div class="zone">best at ${zone}</div>`;
      attachPointerDrag(card, {                  // swipe to scroll · drag up to a slot · tap to sign
        label: p.name,
        vLock: true,                             // horizontal swipe scrolls the shop row
        begin: () => { draggedShop = i; highlightSlots(true); },
        end:   () => { draggedShop = null; highlightSlots(false); },
        canDrop: (s) => canDrop(s),
        onDrop: (s) => buy(i, s),
        onTap: () => !busy && buy(i),            // tap = sign to first open slot
      });
      card.querySelector(".freeze").onclick = (e) => {  // toggle hold (no reroll)
        e.stopPropagation();
        if (busy) return;
        p.frozen = !p.frozen;
        renderShop();
      };
    }
    shop.appendChild(card);
  });
}

function logLines(lines, cls) {
  const feed = $("feed");
  (lines || []).forEach((t) => {
    const d = document.createElement("div");
    d.className = "ev " + (cls || "");
    d.textContent = t;
    feed.appendChild(d);
  });
  feed.scrollTop = feed.scrollHeight;
}

// ------------------------------------------------------------------- actions
async function buy(i, slot) {
  const p = state.shop[i];
  if (!p) return;
  if (slot == null) {                          // click: open slot, else merge a twin
    const used = usedSlots();
    slot = p.positions.find((s) => !used.has(s));
    if (slot == null) {
      const twin = state.lineup.find((pl) => pl.archetype === p.archetype);
      if (twin) slot = twin.slot;              // no open slot — level up a same archetype
    }
    if (slot == null) {
      logLines([`No open ${p.positions.map((s) => POS_LABELS[s]).join("/")} slot.`]);
      return;
    }
  }
  const r = await api("/api/buy", {state, index: i, slot});
  state = r.state; render(); logLines(r.log);
}
async function sell(id) {
  const idx = state.lineup.findIndex((p) => p.id === id);
  if (idx < 0) return;
  const r = await api("/api/sell", {state, index: idx});
  state = r.state; render(); logLines(r.log);
}

// --- playbook trails: dashed pass line + shot crosshair (SVG overlay) -------
function trailLine(from, to, cls) {
  const svg = $("trails");
  if (!svg || !from || !to) return;
  const ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
  ln.setAttribute("x1", from.x); ln.setAttribute("y1", from.y);
  ln.setAttribute("x2", to.x); ln.setAttribute("y2", to.y);
  ln.setAttribute("class", "trail " + (cls || ""));
  svg.appendChild(ln);
  setTimeout(() => ln.remove(), STEP_MS + 200);
}
function clearTrails() { const s = $("trails"); if (s) s.innerHTML = ""; }

// ------------------------------------------------------------------- playback
function flash(id, scoring, shot) {
  const el = document.querySelector(`#court .token[data-id="${id}"]`);
  if (!el) return;
  el.classList.add("act");
  if (scoring) el.classList.add("score");
  setTimeout(() => el.classList.remove("act", "score"), STEP_MS - 250);
}

// game clock: maps possessions remaining to a 12:00 quarter that ticks to 0:00
function fmtClock(left, total) {
  const secs = total ? Math.round((left / total) * 720) : 0;
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}
function setClock(possLeft, total, youLeft, oppLeft) {
  $("clock-time").textContent = fmtClock(possLeft, total);
  $("you-poss").textContent = youLeft + " poss left";
  $("opp-poss").textContent = oppLeft + " poss left";
}
function showClock(on) {
  $("clock").classList.toggle("hidden", !on);
  if (!on) { $("you-poss").textContent = ""; $("opp-poss").textContent = ""; }
}

async function animate(result) {
  busy = true;
  setButtons(false);
  $("feed").innerHTML = "";
  $("you-score").textContent = "0";
  $("opp-score").textContent = "0";
  playersById = {};
  state.lineup.forEach((p) => playersById[p.id] = p);
  result.opponent.forEach((p) => playersById[p.id] = p);
  renderOppPanel(result.opponent, result.opp_source);  // reveal opponent roster

  let you = 0, opp = 0;
  buildChemMap(state.lineup, result.opponent); // duo/trio marks for both teams
  spawnPlaybackTokens();                      // all ten on court at placed spots
  showFinalsLogo(!!result.is_finals);         // championship floor logo
  if (result.is_finals)
    logLines(["🏆 THE FINALS — winner takes the title."], "head");
  if (result.chem_you && result.chem_you.length)
    logLines([`Your chemistry: ${result.chem_you.map((c) => c.name).join(", ")}`], "you-ev");
  if (result.chem_opp && result.chem_opp.length)
    logLines([`Opponent chemistry: ${result.chem_opp.map((c) => c.name).join(", ")}`], "opp-ev");
  await sleep(500);

  const playPossession = async (poss, who, addScore) => {
    const holder = poss.handler;             // the initiator starts with the ball
    let cur = posLookup(poss.layout);
    moveTokens(poss.layout);                 // drift into the play
    ballTo(holder ? cur[holder] : null, {instant: true});
    await sleep(500);
    for (const ev of poss.events) {
      if (ev.layout) {                       // players keep MOVING during the play
        cur = posLookup(ev.layout);
        moveTokens(ev.layout);
        await sleep(360);
      }
      if (ev.kind === "pass") {
        logLines([ev.text], who + " pass");
        if (ev.actor) flash(ev.actor, false);
        trailLine(cur[ev.actor], cur[ev.target], "pass");          // playbook dashed pass
        ballTo(cur[ev.target]);              // swing the ball to the next handler
        await sleep(PASS_PAUSE);             // brief beat, then move on
      } else if (ev.kind === "steal") {      // intercepted IN THE LANE, before the target
        logLines([ev.text], who + " steal");
        if (ev.actor) { flash(ev.actor, false); ballTo(cur[ev.actor]); }
        await sleep(STEP_MS);
      } else if (ev.kind === "rebound") {    // crashed the offensive glass
        logLines([ev.text], who + " reb");
        if (ev.actor) { flash(ev.actor, false); ballTo(cur[ev.actor]); }
        await sleep(STEP_MS - 250);
      } else {                               // made / miss — shoot from the spot
        if (ev.actor) ballTo(cur[ev.actor]);
        await sleep(180);
        if (ev.actor) trailLine(cur[ev.actor], {x: 50, y: 7}, "shot");
        ballTo({x: 50, y: 7}, {shot: true});
        await sleep(340);
        logLines([ev.text], who + " " + ev.kind);
        if (ev.actor) flash(ev.actor, ev.kind === "made", ev.shot);
        if (ev.target) flash(ev.target, false);
        addScore(ev.points);
        if (ev.kind === "made") { ballTo({x: 50, y: 7}, {made: true}); flashHoop(); }
        else ballTo({x: 50 + (Math.random() * 16 - 8), y: 14});   // caroms off the rim
        await sleep(STEP_MS);
      }
    }
    clearTrails();
  };

  // ALTERNATING possessions; the higher-offense team gets the ball first
  const addYou = (p) => { you += p; $("you-score").textContent = you; };
  const addOpp = (p) => { opp += p; $("opp-score").textContent = opp; };
  const yp = result.you_possessions, op = result.opp_possessions;
  const youSide = {poss: yp, who: "you-ev", add: addYou, label: "YOUR BALL", phase: "Your ball", key: "you"};
  const oppSide = {poss: op, who: "opp-ev", add: addOpp, label: "OPPONENT BALL", phase: "Opponent ball", key: "opp"};
  const order = result.you_first === false ? [oppSide, youSide] : [youSide, oppSide];
  if (result.you_first === false)
    logLines(["Opponent wins the tip (higher offense)."], "opp-ev");
  else
    logLines(["You win the tip (higher offense)."], "you-ev");

  // possession clock: counts down as each possession plays
  const total = yp.length + op.length;
  let possLeft = total, youLeft = yp.length, oppLeft = op.length;
  showClock(true);
  setClock(possLeft, total, youLeft, oppLeft);

  const rounds = Math.max(yp.length, op.length);
  for (let i = 0; i < rounds; i++) {
    for (const side of order) {
      if (i < side.poss.length) {
        $("phase-label").textContent = `${side.phase} (${i + 1})`;
        logLines([`${side.label} · poss ${i + 1}`], "head");
        await playPossession(side.poss[i], side.who, side.add);
        possLeft--;
        if (side.key === "you") youLeft--; else oppLeft--;
        setClock(possLeft, total, youLeft, oppLeft);
      }
    }
  }

  if (result.ot) logLines(["🏀 OVERTIME — sudden death, first bucket wins!"], "head");
  const verdict = {win: "WIN", loss: "LOSS", push: "PUSH (no record change)"}[result.verdict];
  logLines([`FINAL: You ${you} – ${opp} Opponent  →  ${verdict}`], "head");
  if (result.unlocked_tier) {
    logLines([`🔓 TIER ${result.unlocked_tier} UNLOCKED — new free agents in the market!`], "head");
  }
  if (result.made_finals) {
    logLines(["🏆 You've reached the FINALS! One title game stands between you and the ring."], "head");
  }
  await sleep(1400);
  hideBall();
  clearTrails();
  showClock(false);
  busy = false;
}

async function play() {
  if (busy || conflicts.size) return;
  if (state.lineup.length === 0) { logLines(["Sign at least one player first."]); return; }
  const r = await api("/api/play", {state});
  if (r.error) { state = r.state; render(); logLines(r.log); return; }  // overlap backstop
  state = r.state;
  await animate(r.result);
  showPostgame(r.result);                 // box score; "Continue" resumes the run
}

// resume from the post-game box score → back to building, or end the run
function resumePostgame() {
  $("postgame").classList.add("hidden");
  const result = pendingResult;
  pendingResult = null;
  render();
  if (result && result.game_over) showOverlay(result.outcome);
  else setButtons(true);
}

function setButtons(on) {
  ["reroll", "newgame"].forEach((id) => $(id).disabled = !on);
  updatePlayButton();
}

function showFinalsLogo(on) {
  const el = $("finals-logo");
  if (el) el.classList.toggle("hidden", !on);
}

// ------------------------------------------------- post-game TEAM aggregate stats
function teamAgg(box) {
  const t = (k) => box.reduce((a, b) => a + b[k], 0);
  return {pts: t("pts"), reb: t("reb"), ast: t("ast"), fgm: t("fgm"), fga: t("fga"),
          pct: t("fga") ? Math.round((t("fgm") / t("fga")) * 100) : 0};
}

function showPostgame(result) {
  const v = {win: "WIN", loss: "LOSS", push: "PUSH"}[result.verdict];
  $("pg-title").textContent = (result.is_finals ? "🏆 THE FINALS — " : "FINAL — ")
    + `You ${result.you_pts} – ${result.opp_pts} Opponent  ·  ${v}`
    + (result.ot ? "  (OT)" : "");
  $("pg-sub").textContent = result.made_finals
    ? "You clinched a Finals berth! Build your champion, then play for the title."
    : result.is_finals
      ? (result.verdict === "win" ? "Champions." : "Fell at the final hurdle.")
      : "Team totals — watch the game, read the numbers after.";
  const y = teamAgg(result.you_box), o = teamAgg(result.opp_box);
  const row = (label, yd, od, yc, oc) =>
    `<tr><td class="yv ${yc > oc ? "lead" : ""}">${yd}</td>`
    + `<td class="lbl">${label}</td>`
    + `<td class="ov ${oc > yc ? "lead" : ""}">${od}</td></tr>`;
  $("pg-tables").innerHTML = `<table class="agg">
    <thead><tr><th class="you">YOU</th><th></th><th class="opp">OPP</th></tr></thead>
    <tbody>
      ${row("Points", y.pts, o.pts, y.pts, o.pts)}
      ${row("Rebounds", y.reb, o.reb, y.reb, o.reb)}
      ${row("Assists", y.ast, o.ast, y.ast, o.ast)}
      ${row("Field Goals", `${y.fgm}-${y.fga}`, `${o.fgm}-${o.fga}`, y.fgm, o.fgm)}
      ${row("FG%", `${y.pct}%`, `${o.pct}%`, y.pct, o.pct)}
    </tbody></table>`;
  pendingResult = result;
  $("postgame").classList.remove("hidden");
}

function showOverlay(outcome) {
  const map = {
    champion:    ["🏆 CHAMPIONS!", " You won it all."],
    "runner-up": ["Runner-up", " You fell in the Finals."],
    busted:      ["Eliminated", " Your championship run is over."],
  };
  const [title, extra] = map[outcome] || ["Run over", ""];
  $("overlay-title").textContent = title;
  $("overlay-body").textContent =
    `Final record: ${state.wins}W – ${state.losses}L.` + extra;
  $("overlay").classList.remove("hidden");
}

// ------------------------------------------------------------------- boot
async function newGame() {
  const r = await api("/api/start", {});
  state = r.state;
  $("overlay").classList.add("hidden");
  $("postgame").classList.add("hidden");
  showFinalsLogo(false);
  $("you-score").textContent = "0";
  $("opp-score").textContent = "0";
  $("feed").innerHTML = "";
  setButtons(true);
  render();
  logLines(r.log);
}

$("play").onclick = play;
$("newgame").onclick = newGame;
$("overlay-btn").onclick = newGame;
$("pg-btn").onclick = resumePostgame;
$("reroll").onclick = async () => {
  if (busy) return;
  const r = await api("/api/reroll", {state});
  state = r.state; render(); logLines(r.log);
};

newGame();
