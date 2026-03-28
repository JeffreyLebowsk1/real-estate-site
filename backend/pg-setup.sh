#!/usr/bin/env bash
# Run as: sudo bash ~/real-estate-site/backend/pg-setup.sh
# Fix postgres role and create tables
set -e

DEPLOY_DIR="/opt/real-estate-site"
VENV="$DEPLOY_DIR/backend/venv"
PYTHON="$VENV/bin/python3"
DB_PASS="mdilworth-db-2026"

echo "=== Fixing postgres role ==="
sudo -u postgres psql -c "ALTER ROLE mdilworth WITH LOGIN PASSWORD '$DB_PASS';"

echo "=== Testing connection ==="
PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U mdilworth -d mdilworth -c "SELECT 1 AS ok;"

echo "=== Creating tables ==="
sudo -u www-data bash -c "cd '$DEPLOY_DIR/backend' && '$PYTHON' -c '
import sys
sys.path.insert(0, \".\")
from app import app, db
with app.app_context():
    db.create_all()
    print(\"Tables created OK\")
'"

echo "=== Restarting services ==="
systemctl restart mdilworth-api
systemctl restart caddy
sleep 3

echo "=== Health check ==="
curl -sf http://127.0.0.1:5000/api/health && echo " Flask OK" || echo " Flask FAILED"
STATUS=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/admin/login 2>/dev/null || echo 000)
echo " Admin login HTTP $STATUS"

echo ""
echo "ALL DONE. To set admin password, run:"
echo "  sudo -u www-data $PYTHON -c \"from werkzeug.security import generate_password_hash as h; print(h('yourpassword'))\""
echo "Then put the hash in ADMIN_PASSWORD_HASH= in $DEPLOY_DIR/backend/.env and:"
echo "  sudo systemctl restart mdilworth-api"
