# 🏀 HARDWOOD — Basketball Auto-Battler

A TFT / Super Auto Pets–style auto-battler reskinned as basketball: build a 5-slot
lineup in a free-agency shop phase, place players on a half-court, then watch it
auto-resolve as a **scored game** against another lineup — most points wins, no combat.

It's a **championship run**: rack up **12 wins to clinch a Finals berth** before **4
losses eliminate you**, then win a (twice-as-long, sudden-death-OT) **Finals** for the ring.

## Systems
- **Four ratings** per player — **Shooting · Defense · Playmaking · Athleticism** — backed
  by hidden per-zone stats, so a post big dominates the rim but bricks threes while a
  sharpshooter does the reverse (scoring is split: jumpers ← SHT, rim ← ATH).
- **16 archetypes**, **6 tiers** (unlock by games played), **archetype chemistry** (duos/trios),
  **29 abilities**, **SAP-style leveling** (combine same-archetype players), a **cap economy**
  with tiered prices + interest, a **freeze/reroll** market, and async **snapshot opponents**.
- Pure **CSS/SVG** visuals — no image assets, no generative AI. Players are fully fictional.

## Run locally
```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5000
```

## Deploy
Any Python host that reads a `Procfile` (Render, Railway, Heroku):
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT` (already in the `Procfile`)

## Layout
- `app.py` — Flask host / rules authority (stateless; run-state travels with each request)
- `sim.py` — the importable sim core (all game logic + tuning knobs)
- `templates/index.html`, `static/{app.js,style.css}` — the browser view
