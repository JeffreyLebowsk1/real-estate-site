#!/usr/bin/env bash
# setup-jetson.sh — bootstraps the real-estate-site stack on a Jetson Orin Nano 8G
#
# What it does:
#   1. Installs system packages (python3, pip, caddy, cloudflared)
#   2. Deploys repo files to /opt/real-estate-site
#   3. Creates a Python venv and installs backend dependencies
#   4. Installs and enables three systemd services:
#        caddy            — HTTP server on :8080  (TLS via Cloudflare)
#        cloudflared      — cccc-notes tunnel → homes.mdilworth.com
#        mdilworth-api    — Flask/Gunicorn API on 127.0.0.1:5000
#
# Usage (run as root or with sudo):
#   sudo bash setup-jetson.sh
#
# Before running this script you must:
#   a) Authenticate cloudflared with your Cloudflare account:
#        cloudflared tunnel login
#   b) Ensure the cccc-notes tunnel exists (or let the script create it):
#        cloudflared tunnel create cccc-notes
#   c) Copy the tunnel credentials JSON that was created in ~/.cloudflared/
#      to /etc/cloudflared/cccc-notes.json  (or run this script — it will
#      attempt to find and copy it automatically).
#   d) In the Cloudflare dashboard, add a CNAME for homes.mdilworth.com pointing
#      to <TUNNEL-UUID>.cfargotunnel.com with the proxy (orange cloud) enabled.

set -euo pipefail

# ─── colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ─── must run as root ────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root.  Try: sudo bash $0"
    exit 1
fi

# ─── locate the repo ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
INSTALL_DIR="/opt/real-estate-site"

info "Repo source : $REPO_DIR"
info "Install dir : $INSTALL_DIR"

# ─── 1. System packages ──────────────────────────────────────────────────────
info "Updating package lists…"
apt-get update -qq

info "Installing base dependencies…"
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    debian-keyring debian-archive-keyring apt-transport-https \
    curl gnupg lsb-release

# ── Caddy (official arm64 repository) ────────────────────────────────────────
if ! command -v caddy &>/dev/null; then
    info "Adding Caddy stable repository…"
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
    info "Caddy installed: $(caddy version)"
else
    info "Caddy already installed: $(caddy version)"
fi

# ── cloudflared (arm64 .deb from GitHub releases) ────────────────────────────
if ! command -v cloudflared &>/dev/null; then
    info "Downloading cloudflared for arm64…"
    CF_DEB="/tmp/cloudflared-linux-arm64.deb"
    curl -L \
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb" \
        -o "$CF_DEB"
    dpkg -i "$CF_DEB"
    rm -f "$CF_DEB"
    info "cloudflared installed: $(cloudflared --version)"
else
    info "cloudflared already installed: $(cloudflared --version)"
fi

# ─── 2. Deploy repo files ────────────────────────────────────────────────────
info "Deploying site files to $INSTALL_DIR…"
mkdir -p "$INSTALL_DIR"
# Sync everything except .git and node_modules
rsync -a --exclude='.git' --exclude='node_modules' "$REPO_DIR/" "$INSTALL_DIR/"

# www-data owns the site files; the API backend writes leads.db there
chown -R www-data:www-data "$INSTALL_DIR"

# ─── 3. Python virtual-env + backend dependencies ───────────────────────────
VENV_DIR="$INSTALL_DIR/backend/venv"
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating Python venv at $VENV_DIR…"
    python3 -m venv "$VENV_DIR"
fi

info "Installing Python dependencies…"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/backend/requirements.txt"
chown -R www-data:www-data "$VENV_DIR"

# ─── 4. Backend .env ─────────────────────────────────────────────────────────
ENV_FILE="$INSTALL_DIR/backend/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found — copying .env.example; edit $ENV_FILE before starting services."
    cp "$INSTALL_DIR/backend/.env.example" "$ENV_FILE"
    chown www-data:www-data "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# ─── 5. cloudflared credentials & config ─────────────────────────────────────
CF_CONFIG_DIR="/etc/cloudflared"
mkdir -p "$CF_CONFIG_DIR"

CF_CREDS="$CF_CONFIG_DIR/cccc-notes.json"
if [[ ! -f "$CF_CREDS" ]]; then
    # Try to find the credentials in the home directories of all users
    FOUND=""
    for dir in /root /home/*; do
        [[ -d "$dir" ]] || continue
        CF_JSON=$(find "$dir/.cloudflared" -name '*.json' 2>/dev/null | head -1 || true)
        if [[ -n "$CF_JSON" ]]; then
            FOUND="$CF_JSON"
            break
        fi
    done

    if [[ -n "$FOUND" ]]; then
        info "Found tunnel credentials at $FOUND — copying to $CF_CREDS"
        cp "$FOUND" "$CF_CREDS"
        chmod 600 "$CF_CREDS"
    else
        warn "Tunnel credentials not found."
        warn "After authenticating (cloudflared tunnel login && cloudflared tunnel create cccc-notes)"
        warn "copy the resulting JSON to: $CF_CREDS"
    fi
fi

# Deploy cloudflared config
info "Installing cloudflared config…"
cp "$INSTALL_DIR/cloudflared/config.yml" "$CF_CONFIG_DIR/config.yml"

# ─── 6. systemd services ─────────────────────────────────────────────────────
info "Installing systemd service files…"

install_service() {
    local src="$1" name="$2"
    cp "$src" "/etc/systemd/system/$name"
    info "  installed $name"
}

install_service "$INSTALL_DIR/caddy.service"                  "caddy.service"
install_service "$INSTALL_DIR/backend/mdilworth-api.service"  "mdilworth-api.service"

# Install the official cloudflared system service (creates its own unit file)
if ! systemctl list-unit-files cloudflared.service 2>/dev/null | grep -q cloudflared; then
    info "Registering cloudflared as a system service…"
    cloudflared service install || warn "cloudflared service install failed — you may need to run it manually after adding credentials."
fi

systemctl daemon-reload

info "Enabling services…"
systemctl enable caddy mdilworth-api cloudflared

# ─── 7. Start / restart services ─────────────────────────────────────────────
info "Starting services…"
for svc in caddy mdilworth-api cloudflared; do
    if systemctl is-active --quiet "$svc"; then
        systemctl restart "$svc" && info "  $svc restarted"
    else
        systemctl start "$svc" && info "  $svc started"
    fi
done

# ─── 8. Health check ─────────────────────────────────────────────────────────
sleep 2
info "Running quick health checks…"

check_http() {
    local url="$1" label="$2"
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" || echo "000")
    if [[ "$code" == "200" ]]; then
        info "  ✓ $label ($url) → HTTP $code"
    else
        warn "  ✗ $label ($url) → HTTP $code (service may still be starting)"
    fi
}

check_http "http://localhost:8080/"            "Caddy static site"
check_http "http://localhost:8080/api/health"  "Flask API /health"

# ─── done ─────────────────────────────────────────────────────────────────────
echo ""
info "Setup complete!"
echo ""
echo "  Static site  → http://localhost:8080  (via Caddy)"
echo "  API backend  → http://localhost:5000  (via Gunicorn)"
echo "  Public URL   → https://homes.mdilworth.com  (Cloudflare tunnel + orange cloud)"
echo ""
echo "  Next steps if you haven't already:"
echo "    1. Edit $ENV_FILE  (SMTP credentials, etc.)"
echo "    2. Place the cccc-notes tunnel credentials at $CF_CREDS"
echo "    3. In Cloudflare DNS, add:"
echo "         homes.mdilworth.com  CNAME  <tunnel-uuid>.cfargotunnel.com  [proxied ✓]"
echo "    4. sudo systemctl restart cloudflared mdilworth-api caddy"
echo ""
