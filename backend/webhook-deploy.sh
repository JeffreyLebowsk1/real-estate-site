#!/usr/bin/env bash
# webhook-deploy.sh — triggered by the Flask /webhook/deploy endpoint.
#
# Pulls the latest code from main, updates Python deps if needed, and
# restarts only the services whose files changed.
#
# Runs as root via a sudoers rule installed by setup-jetson.sh:
#   www-data ALL=(ALL) NOPASSWD: /opt/real-estate-site/backend/webhook-deploy.sh

set -euo pipefail

# Derive paths from the script's own location so the repo can be installed
# anywhere (not just /opt/real-estate-site).
SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$DEPLOY_DIR/backend/venv"
PIP="$VENV/bin/pip"

echo "==> Fetching latest code from origin/main"
git -C "$DEPLOY_DIR" fetch origin main

BEFORE=$(git -C "$DEPLOY_DIR" rev-parse HEAD)
git -C "$DEPLOY_DIR" reset --hard origin/main
AFTER=$(git -C "$DEPLOY_DIR" rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
    echo "Already up to date — nothing to do."
    exit 0
fi

CHANGED=$(git -C "$DEPLOY_DIR" diff --name-only "$BEFORE" "$AFTER" 2>/dev/null || {
    echo "WARNING: git diff failed — restarting all services to be safe"
    systemctl restart mdilworth-api
    systemctl reload caddy
    exit 0
})
echo "Changed files ($BEFORE -> $AFTER):"
echo "$CHANGED"

# Update Python deps if requirements.txt changed
if echo "$CHANGED" | grep -q '^backend/requirements\.txt'; then
    echo "==> Updating Python dependencies"
    sudo -u www-data "$PIP" install -q --upgrade \
        -r "$DEPLOY_DIR/backend/requirements.txt"
fi

# Restart the Flask API if any backend file changed
if echo "$CHANGED" | grep -q '^backend/'; then
    echo "==> Restarting mdilworth-api"
    systemctl restart mdilworth-api
fi

# Reload Caddy only if the Caddyfile changed
if echo "$CHANGED" | grep -q '^Caddyfile$'; then
    echo "==> Reloading caddy"
    systemctl reload caddy
fi

echo "==> Deploy complete"
