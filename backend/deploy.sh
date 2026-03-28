#!/usr/bin/env bash
# deploy.sh — run on Jetson to install PostgreSQL, set up DB, install packages,
# generate a password hash, update .env, and restart services.
# Usage: bash /opt/real-estate-site/backend/deploy.sh
set -e

DEPLOY_DIR="/opt/real-estate-site"
VENV="$DEPLOY_DIR/backend/venv"
PYTHON="$VENV/bin/python3"
PIP="$VENV/bin/pip"

echo "==> 1. Install PostgreSQL"
sudo apt-get install -y postgresql postgresql-contrib

echo "==> 2. Create DB and user"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='mdilworth'" \
  | grep -q 1 || sudo -u postgres createuser mdilworth

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='mdilworth'" \
  | grep -q 1 || sudo -u postgres createdb -O mdilworth mdilworth

# Read current DB password from .env (if set) so we don't overwrite it twice
DB_PASS=$(grep '^DATABASE_URL=' "$DEPLOY_DIR/backend/.env" 2>/dev/null \
          | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|' || true)
if [ -z "$DB_PASS" ] || [ "$DB_PASS" = "changeme" ]; then
  DB_PASS=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
  echo "  Generated DB password."
fi

sudo -u postgres psql -c "ALTER USER mdilworth PASSWORD '$DB_PASS';" > /dev/null
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mdilworth TO mdilworth;" > /dev/null

echo "==> 3. Pull latest code into $DEPLOY_DIR"
git -C "$DEPLOY_DIR" pull --ff-only

echo "==> 4. Install Python packages"
sudo -u www-data "$PIP" install -q --upgrade -r "$DEPLOY_DIR/backend/requirements.txt"

echo "==> 5. Update .env"
# Ensure SECRET_KEY exists
APP_SECRET=$(grep '^SECRET_KEY=' "$DEPLOY_DIR/backend/.env" 2>/dev/null \
             | cut -d= -f2- || true)
if [ -z "$APP_SECRET" ] || [ "$APP_SECRET" = "change-this-to-a-random-secret" ]; then
  APP_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
fi

# Generate admin password hash if ADMIN_PASSWORD is set in env (for automation)
ADMIN_PW="${ADMIN_PASSWORD:-}"
ADMIN_HASH=""
if [ -n "$ADMIN_PW" ]; then
  ADMIN_HASH=$(sudo -u www-data "$PYTHON" -c \
    "from werkzeug.security import generate_password_hash; print(generate_password_hash('$ADMIN_PW'))")
else
  ADMIN_HASH=$(grep '^ADMIN_PASSWORD_HASH=' "$DEPLOY_DIR/backend/.env" 2>/dev/null \
               | cut -d= -f2- || true)
fi

DB_URL="postgresql://mdilworth:${DB_PASS}@localhost/mdilworth"

# Write new .env (preserves SMTP settings if present)
SMTP_HOST=$(grep '^SMTP_HOST=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "smtp.gmail.com")
SMTP_PORT=$(grep '^SMTP_PORT=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "587")
SMTP_USER=$(grep '^SMTP_USER=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")
SMTP_PASS=$(grep '^SMTP_PASS=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")
NOTIFY_EMAIL=$(grep '^NOTIFY_EMAIL=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "matt@mdilworth.com")

sudo tee "$DEPLOY_DIR/backend/.env" > /dev/null <<ENVEOF
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASS=$SMTP_PASS
NOTIFY_EMAIL=$NOTIFY_EMAIL
DATABASE_URL=$DB_URL
SECRET_KEY=$APP_SECRET
ADMIN_PASSWORD_HASH=$ADMIN_HASH
SPAM_THRESHOLD=5
PORT=5000
ENVEOF
sudo chown www-data:www-data "$DEPLOY_DIR/backend/.env"
sudo chmod 600 "$DEPLOY_DIR/backend/.env"

echo "==> 6. Run DB migrations (create tables)"
cd "$DEPLOY_DIR/backend"
sudo -u www-data "$PYTHON" -c "
import sys; sys.path.insert(0, '.')
from app import app, db
with app.app_context():
    db.create_all()
    print('Tables OK')
"

echo "==> 7. Migrate old SQLite data (if any)"
OLD_DB="$HOME/real-estate-site/backend/leads.db"
if [ -f "$OLD_DB" ]; then
  sudo cp "$OLD_DB" "$DEPLOY_DIR/backend/leads.db"
  sudo chown www-data:www-data "$DEPLOY_DIR/backend/leads.db"
  sudo -u www-data DB_PATH="$DEPLOY_DIR/backend/leads.db" "$PYTHON" migrate_sqlite.py
else
  echo "  No leads.db found — skipping migration."
fi

echo "==> 8. Restart services"
sudo systemctl restart mdilworth-api
sudo systemctl restart caddy

echo ""
echo "==> 9. Health check"
sleep 2
curl -sf http://127.0.0.1:5000/api/health && echo " API OK" || echo " API FAILED"
curl -sf http://127.0.0.1:8081/api/health && echo " Caddy OK" || echo " Caddy FAILED"

echo ""
echo "Done! Admin panel: https://homes.mdilworth.com/admin"
if [ -z "$ADMIN_PW" ]; then
  echo "IMPORTANT: Set ADMIN_PASSWORD env var before running, or manually set"
  echo "  ADMIN_PASSWORD_HASH in $DEPLOY_DIR/backend/.env"
  echo "  Generate hash: python3 -c \"from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))\""
fi
