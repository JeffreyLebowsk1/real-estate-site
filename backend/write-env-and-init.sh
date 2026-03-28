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

# Write .env
sudo tee "$DEPLOY_DIR/backend/.env" > /dev/null << 'ENVEOF'
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
NOTIFY_EMAIL=matt@mdilworth.com
DATABASE_URL=postgresql://mdilworth:mdilworth-db-2026@localhost/mdilworth
SECRET_KEY=PLACEHOLDER_SECRET
ADMIN_PASSWORD_HASH=
SPAM_THRESHOLD=5
PORT=5000
ENVEOF

# Replace the placeholder secret with a real one
sudo sed -i "s|PLACEHOLDER_SECRET|$APP_SECRET|" "$DEPLOY_DIR/backend/.env"
sudo chown www-data:www-data "$DEPLOY_DIR/backend/.env"
sudo chmod 600 "$DEPLOY_DIR/backend/.env"
echo ".env written"
sudo cat "$DEPLOY_DIR/backend/.env" | grep -v PASS | grep -v SECRET

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

echo ""
echo "Done! To set admin password:"
echo "  Hash: sudo -u www-data $PYTHON -c \"from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))\""
echo "  Then update ADMIN_PASSWORD_HASH in $DEPLOY_DIR/backend/.env and restart mdilworth-api"
