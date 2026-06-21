# Auto-GM (HARDWOOD) — Deploy Checklist

Target: the Oracle Cloud VM that already runs StatCheck (5000), RatingsCheck (5050),
StatGolf (5052). Auto-GM gets port **5054** and **autogm.statcheckgame.com**, behind the
same nginx. It's plain Flask — no websockets, no database, no secrets — so it's the
simplest of the four to add.

---

## 1. DNS — one record (at your registrar for statcheckgame.com)
```
Type  Name     Value
A     autogm   <VM public IP>      # the same IP your other apps use
```

## 2. Clone on the VM
```bash
ssh statcheck                      # your existing SSH alias
cd /home/ubuntu
git clone https://github.com/JustKelp/Auto-GM.git auto-gm
cd auto-gm
```

## 3. One-shot setup (venv, deps, systemd, nginx, smoke test)
```bash
bash deploy/setup.sh
```
Binds gunicorn to `127.0.0.1:5054`, installs the `auto-gm` systemd service (auto-starts
on boot, restarts on crash), wires the nginx vhost, and prints `OK` when the app answers
on 5054.

## 4. SSL (after the DNS A record resolves)
```bash
sudo certbot --nginx -d autogm.statcheckgame.com
```
Then visit **https://autogm.statcheckgame.com** — done.

---

## Updating later (after pushing changes to GitHub)
```bash
ssh statcheck "cd /home/ubuntu/auto-gm && git pull && sudo systemctl restart auto-gm"
```

## Handy
```bash
sudo systemctl status auto-gm          # is it running?
journalctl -u auto-gm -n 50 --no-pager # recent logs
tail -f /var/log/auto-gm/error.log     # gunicorn errors
```

## Notes
- **Firewall:** 80/443 are already open in the Oracle security list for the sibling apps — nothing to change.
- **Port:** 5054 was chosen to avoid 5000/5050/5052. If it's taken, change it in `gunicorn.conf.py` and `deploy/auto-gm.nginx`, then re-run `setup.sh`.
- **State:** `teams.json` (snapshot opponents) is created at runtime in the app dir and is gitignored.
- The repo's `Procfile` / `render.yaml` are for Render and are simply unused on this path.
