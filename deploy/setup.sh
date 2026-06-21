#!/usr/bin/env bash
# Auto-GM (HARDWOOD) one-shot VM setup. Run on the Oracle VM after cloning into
# /home/ubuntu/auto-gm:
#
#   cd /home/ubuntu/auto-gm && bash deploy/setup.sh
#
# Sets up the venv + deps, installs the systemd service + nginx vhost, and starts
# the app on 127.0.0.1:5053. DNS, the firewall (80/443 already open for the
# sibling apps), and certbot stay manual — see DEPLOY.md.
set -euo pipefail
APP_DIR=/home/ubuntu/auto-gm
cd "$APP_DIR"

echo "==> Python venv + deps"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -r requirements.txt

echo "==> Log dir + systemd service"
sudo mkdir -p /var/log/auto-gm && sudo chown ubuntu:ubuntu /var/log/auto-gm
sudo cp deploy/auto-gm.service /etc/systemd/system/auto-gm.service
sudo systemctl daemon-reload
sudo systemctl enable --now auto-gm
sudo systemctl --no-pager --full status auto-gm | head -8

echo "==> nginx vhost"
sudo cp deploy/auto-gm.nginx /etc/nginx/sites-available/auto-gm
sudo ln -sf /etc/nginx/sites-available/auto-gm /etc/nginx/sites-enabled/auto-gm
sudo nginx -t && sudo systemctl reload nginx

echo "==> Local smoke test"
sleep 2
curl -fsS http://127.0.0.1:5053/ >/dev/null && echo "OK: app responding on 5053"

cat <<'NEXT'

Still manual:
  1. DNS: add an A record  autogm.statcheckgame.com -> <this VM public IP>
  2. SSL: sudo certbot --nginx -d autogm.statcheckgame.com
NEXT
