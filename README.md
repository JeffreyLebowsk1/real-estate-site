# real-estate-site
mdilworth.com real estate site — Bootstrap static site hosted on Cloudflare Pages

## homes.mdilworth.com subdomain (Jetson Orin Nano / self-hosted)

The `homes.mdilworth.com` subdomain is served from a local Jetson Orin Nano 8G
through the **cccc-notes** Cloudflare tunnel.  Cloudflare's orange-cloud proxy
provides free SSL termination; the server only needs to run plain HTTP.

```
Browser ──HTTPS──► Cloudflare (orange cloud)
                         │  cccc-notes tunnel
                         ▼
               Jetson Orin Nano 8G
               Caddy :8080 (HTTP)
               ├── static files   /opt/real-estate-site
               └── /api/*  ──►  Gunicorn :5000 (Flask)
```

### Update the server with the latest code from `main`

SSH into the Jetson and run these commands to pull the latest `main` branch and
restart all services:

```bash
# 1. Pull latest code from main
#    WARNING: git reset --hard will discard any uncommitted local changes on the
#    server (e.g. manual edits). Your .env file is not tracked by git and is safe.
cd /opt/real-estate-site
sudo git fetch origin main
sudo git reset --hard origin/main

# 2. Update Python dependencies (if requirements changed)
sudo /opt/real-estate-site/backend/venv/bin/pip install -q --upgrade \
    -r /opt/real-estate-site/backend/requirements.txt

# 3. Restart the API and web server
sudo systemctl restart mdilworth-api
sudo systemctl restart caddy

# 4. Verify both services are running
sudo systemctl status mdilworth-api --no-pager
sudo systemctl status caddy --no-pager

# 5. Quick health check
curl -sf http://127.0.0.1:5000/api/health && echo " API OK" || echo " API FAILED"
```

### Quick setup (Jetson Orin Nano)

```bash
# 1. Authenticate cloudflared (once)
cloudflared tunnel login
cloudflared tunnel create cccc-notes   # skip if tunnel already exists

# 2. Run the setup script
sudo bash setup-jetson.sh

# 3. Edit /opt/real-estate-site/backend/.env  (SMTP credentials etc.)

# 4. In Cloudflare DNS add:
#    homes.mdilworth.com  CNAME  <tunnel-uuid>.cfargotunnel.com  [proxied ✓]

# 5. Restart services
sudo systemctl restart cloudflared mdilworth-api caddy
```

### Continuous deployment (GitHub Actions)

Every push to `main` automatically deploys to the Jetson via the
`.github/workflows/deploy.yml` workflow.  The workflow calls the Jetson's
`/webhook/deploy` endpoint over HTTPS.  Add the following secrets to the
repository (**Settings → Secrets and variables → Actions**):

| Secret | Description |
|---|---|
| `JETSON_WEBHOOK_SECRET` | HMAC signing secret — must match `GITHUB_WEBHOOK_SECRET` in `backend/.env` on the Jetson |
| `JETSON_WEBHOOK_URL` | Webhook endpoint URL — `https://homes.mdilworth.com/webhook/deploy` |

#### One-time setup — applying this update on an existing Jetson

SSH into the Jetson and run the following commands **once** to activate
webhook-based continuous deployment.  They pull the new code, wire up the
sudoers rule that lets the Flask process trigger `git pull` + service restarts,
generate the shared HMAC secret, and tell you exactly what to paste into GitHub.

```bash
# ── Step 1: pull the latest code (includes webhook-deploy.sh + updated app.py) ──
cd /opt/real-estate-site
sudo git fetch origin main
sudo git reset --hard origin/main

# ── Step 2: update Python dependencies ───────────────────────────────────────
sudo /opt/real-estate-site/backend/venv/bin/pip install -q --upgrade \
    -r /opt/real-estate-site/backend/requirements.txt

# ── Step 3: make the deploy script executable ─────────────────────────────────
sudo chmod +x /opt/real-estate-site/backend/webhook-deploy.sh

# ── Step 4: install the sudoers rule (allows www-data to run the script as root)
echo "www-data ALL=(ALL) NOPASSWD: /opt/real-estate-site/backend/webhook-deploy.sh" \
    | sudo tee /etc/sudoers.d/mdilworth-webhook
sudo chmod 440 /etc/sudoers.d/mdilworth-webhook

# ── Step 5: add GITHUB_WEBHOOK_SECRET to .env (skip if it already exists) ────
if sudo grep -q '^GITHUB_WEBHOOK_SECRET=' /opt/real-estate-site/backend/.env 2>/dev/null; then
    echo "GITHUB_WEBHOOK_SECRET already set — no change needed."
else
    NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "GITHUB_WEBHOOK_SECRET=$NEW_SECRET" \
        | sudo tee -a /opt/real-estate-site/backend/.env
    echo "Generated GITHUB_WEBHOOK_SECRET."
fi

# ── Step 6: restart the API to pick up the new .env value and webhook route ───
sudo systemctl restart mdilworth-api
sleep 2
curl -sf http://127.0.0.1:5000/api/health && echo " API OK" || echo " API FAILED"

# ── Step 7: print the two values you need to add to GitHub ───────────────────
echo ""
echo "===== GitHub repo secrets to add ====="
echo "JETSON_WEBHOOK_SECRET ="
sudo grep '^GITHUB_WEBHOOK_SECRET=' /opt/real-estate-site/backend/.env | cut -d= -f2-
echo "JETSON_WEBHOOK_URL    = https://homes.mdilworth.com/webhook/deploy"
echo "======================================="
```

Then open **GitHub → Settings → Secrets and variables → Actions → New repository secret**
and add both values printed above.

#### How to re-read the secret later (if you need to re-add it to GitHub)

```bash
sudo grep '^GITHUB_WEBHOOK_SECRET=' /opt/real-estate-site/backend/.env
```

### Key files

| File | Purpose |
|---|---|
| `Caddyfile` | Caddy config — HTTP-only on `:8080`, serves static files + proxies `/api/*` |
| `cloudflared/config.yml` | Cloudflare tunnel config — routes `homes.mdilworth.com` → Caddy |
| `caddy.service` | systemd unit for Caddy |
| `backend/mdilworth-api.service` | systemd unit for Flask/Gunicorn API |
| `backend/webhook-deploy.sh` | Root-level deploy script invoked by `/webhook/deploy` — runs `git pull`, restarts services |
| `setup-jetson.sh` | One-shot bootstrap script for Jetson Orin Nano 8G |
| `.github/workflows/deploy.yml` | GitHub Actions workflow — auto-deploys to Jetson on push to `main` |

