#!/usr/bin/env bash
# Runs on Jetson: sets DB password, updates .env, installs deps, creates tables, restarts services
set -e

DEPLOY_DIR="/opt/real-estate-site"
VENV="$DEPLOY_DIR/backend/venv"
PYTHON="$VENV/bin/python3"
PIP="$VENV/bin/pip"

echo "==> Set postgres password"
DB_PASS=$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')
sudo -u postgres psql -c "ALTER USER mdilworth PASSWORD '$DB_PASS';" > /dev/null
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mdilworth TO mdilworth;" > /dev/null
echo "    DB_PASS generated"

echo "==> Pull latest code into $DEPLOY_DIR"
git -C "$DEPLOY_DIR" pull --ff-only
echo "    Pull done"

echo "==> Install Python packages"
sudo -u www-data "$PIP" install -q --upgrade -r "$DEPLOY_DIR/backend/requirements.txt"
echo "    Packages installed"

echo "==> Generate Flask secret key"
APP_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

echo "==> Read existing SMTP settings from .env"
SMTP_HOST=$(grep '^SMTP_HOST=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "smtp.gmail.com")
SMTP_PORT=$(grep '^SMTP_PORT=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "587")
SMTP_USER=$(grep '^SMTP_USER=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")
SMTP_PASS=$(grep '^SMTP_PASS=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")
NOTIFY_EMAIL=$(grep '^NOTIFY_EMAIL=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "matt@mdilworth.com")
ADMIN_HASH=$(grep '^ADMIN_PASSWORD_HASH=' "$DEPLOY_DIR/backend/.env" 2>/dev/null | cut -d= -f2- || echo "")

DB_URL="postgresql://mdilworth:${DB_PASS}@localhost/mdilworth"

echo "==> Write new .env"
sudo tee "$DEPLOY_DIR/backend/.env" > /dev/null << ENVEOF
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
echo "    .env written"

echo "==> Create DB tables"
sudo -u www-data bash -c "cd '$DEPLOY_DIR/backend' && '$PYTHON' -c \"
import sys; sys.path.insert(0, '.')
from app import app, db
with app.app_context():
    db.create_all()
    print('    Tables OK')
\""

echo "==> Migrate old SQLite data"
OLD_DB="$HOME/real-estate-site/backend/leads.db"
if [ -f "$OLD_DB" ]; then
  sudo cp "$OLD_DB" "$DEPLOY_DIR/backend/leads.db"
  sudo chown www-data:www-data "$DEPLOY_DIR/backend/leads.db"
  sudo -u www-data bash -c "cd '$DEPLOY_DIR/backend' && DB_PATH='$DEPLOY_DIR/backend/leads.db' '$PYTHON' migrate_sqlite.py"
else
  echo "    No leads.db found, skipping migration"
fi

echo "==> Restart services"
sudo systemctl restart mdilworth-api
sudo systemctl restart caddy
sleep 3

echo "==> Health checks"
curl -sf http://127.0.0.1:5000/api/health && echo " Flask OK" || echo " Flask FAILED"
curl -sf http://127.0.0.1:8081/api/health && echo " Caddy OK" || echo " Caddy FAILED"
curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/admin/login && echo " Admin login OK" || echo " Admin login FAILED"

echo ""
echo "==> Done!"
echo "    Admin panel: https://homes.mdilworth.com/admin"
echo "    Set ADMIN_PASSWORD_HASH in $DEPLOY_DIR/backend/.env to log in."
echo "    Generate: python3 -c \"from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))\""
