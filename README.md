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
`.github/workflows/deploy.yml` workflow.  The SSH host is hard-coded to
`jetson.mdilworth.com`.  Add the following secrets to the repository
(**Settings → Secrets and variables → Actions**):

| Secret | Description |
|---|---|
| `JETSON_USER` | SSH username on the Jetson (e.g. `jetson`) |
| `JETSON_SSH_KEY` | Private SSH key whose public half is in `~/.ssh/authorized_keys` on the Jetson |
| `JETSON_PORT` | *(optional)* SSH port — defaults to `22` |

The workflow pulls the latest code into `~/real-estate-site` on the Jetson and
then runs `backend/deploy.sh` to sync files to `/opt/real-estate-site` and
restart the services.

### Key files

| File | Purpose |
|---|---|
| `Caddyfile` | Caddy config — HTTP-only on `:8080`, serves static files + proxies `/api/*` |
| `cloudflared/config.yml` | Cloudflare tunnel config — routes `homes.mdilworth.com` → Caddy |
| `caddy.service` | systemd unit for Caddy |
| `backend/mdilworth-api.service` | systemd unit for Flask/Gunicorn API |
| `setup-jetson.sh` | One-shot bootstrap script for Jetson Orin Nano 8G |
| `.github/workflows/deploy.yml` | GitHub Actions workflow — auto-deploys to Jetson on push to `main` |

