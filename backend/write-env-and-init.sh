#!/usr/bin/env bash
# Write .env and create tables. Run as madmatter on Jetson.
set -e

DEPLOY_DIR="/opt/real-estate-site"
VENV="$DEPLOY_DIR/backend/venv"
PYTHON="$VENV/bin/python3"

# Preserve SMTP if present
SMTP_HOST=$(sudo grep '^SMTP_HOST=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "smtp.gmail.com")
SMTP_PORT=$(sudo grep '^SMTP_PORT=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "587")
SMTP_USER=$(sudo grep '^SMTP_USER=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")
SMTP_PASS=$(sudo grep '^SMTP_PASS=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")

APP_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
WEBHOOK_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Preserve existing admin password hash, or generate a new random password
EXISTING_HASH=$(sudo grep '^ADMIN_PASSWORD_HASH=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")
if [ -n "$EXISTING_HASH" ] && [ "$EXISTING_HASH" != "PLACEHOLDER_ADMIN_HASH" ]; then
  ADMIN_HASH="$EXISTING_HASH"
  ADMIN_PW_DISPLAY="(preserved from existing .env)"
else
  ADMIN_PW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')
  ADMIN_HASH=$(sudo -u www-data env ADMIN_PW_INPUT="$ADMIN_PW" "$PYTHON" -c \
    "import os; from werkzeug.security import generate_password_hash; print(generate_password_hash(os.environ['ADMIN_PW_INPUT']))") \
    || { echo "ERROR: Failed to generate admin password hash. Is the venv installed?"; exit 1; }
  if [ -z "$ADMIN_HASH" ]; then
    echo "ERROR: Admin password hash generation returned empty string."
    exit 1
  fi
  ADMIN_PW_DISPLAY="$ADMIN_PW"
fi

# Write .env
sudo tee "$DEPLOY_DIR/backend/.env" > /dev/null << 'ENVEOF'
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
NOTIFY_EMAIL=matt@mdilworth.com
DATABASE_URL=postgresql://mdilworth:mdilworth-db-2026@localhost/mdilworth
SECRET_KEY=PLACEHOLDER_SECRET
ADMIN_PASSWORD_HASH=PLACEHOLDER_ADMIN_HASH
SPAM_THRESHOLD=5
PORT=5000
GITHUB_WEBHOOK_SECRET=PLACEHOLDER_WEBHOOK_SECRET
ENVEOF

# Replace the placeholder secrets with real ones
sudo sed -i "s|PLACEHOLDER_SECRET|$APP_SECRET|" "$DEPLOY_DIR/backend/.env"
sudo sed -i "s|PLACEHOLDER_WEBHOOK_SECRET|$WEBHOOK_SECRET|" "$DEPLOY_DIR/backend/.env"
sudo sed -i "s|PLACEHOLDER_ADMIN_HASH|$ADMIN_HASH|" "$DEPLOY_DIR/backend/.env"
sudo chown www-data:www-data "$DEPLOY_DIR/backend/.env"
sudo chmod 600 "$DEPLOY_DIR/backend/.env"
echo ".env written"
sudo cat "$DEPLOY_DIR/backend/.env" | grep -v PASS | grep -v SECRET
echo ""
echo "IMPORTANT — add the following to GitHub repo secrets"
echo "  (Settings → Secrets and variables → Actions):"
echo "  JETSON_WEBHOOK_SECRET = $WEBHOOK_SECRET"
echo "  JETSON_WEBHOOK_URL    = https://homes.mdilworth.com/webhook/deploy"
echo ""
if [ "$ADMIN_PW_DISPLAY" = "(preserved from existing .env)" ]; then
  echo "Admin password: $ADMIN_PW_DISPLAY"
else
  echo "IMPORTANT — Admin panel password (save this now, it is not stored in plaintext):"
  echo "  $ADMIN_PW_DISPLAY"
  echo "  Login at: https://homes.mdilworth.com/admin"
fi

echo "Creating DB tables..."
sudo -u www-data bash -c "cd '$DEPLOY_DIR/backend' && '$PYTHON' -c '
import sys; sys.path.insert(0, \".\")
from app import app, db
with app.app_context():
    db.create_all()
    print(\"Tables OK\")
'"

echo "Restarting services..."
sudo systemctl restart mdilworth-api
sudo systemctl restart caddy
sleep 3

echo "Health checks:"
curl -sf http://127.0.0.1:5000/api/health && echo " Flask OK" || echo " Flask FAILED"
curl -sf http://127.0.0.1:8081/api/health && echo " Caddy OK" || echo " Caddy FAILED"
STATUS=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/admin/login 2>/dev/null || echo "000")
echo " Admin login HTTP $STATUS"
