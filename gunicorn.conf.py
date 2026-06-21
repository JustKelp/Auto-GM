# Gunicorn config for the Oracle VM deploy (behind nginx on its own port).
# Render uses the Procfile instead; this file is what the systemd service runs.
workers = 2
worker_class = "sync"          # plain Flask, no websockets
bind = "127.0.0.1:5053"
timeout = 120
keepalive = 5
accesslog = "/var/log/auto-gm/access.log"
errorlog = "/var/log/auto-gm/error.log"
