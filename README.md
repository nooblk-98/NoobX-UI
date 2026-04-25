# ProxyBoard — Xray Dashboard

A modern web UI for managing Xray-core VPN configurations with real-time monitoring, live traffic stats, log viewer, and one-command Docker deployment.

---

## Deployment

### Option 1 — Docker Run (single command)

```bash
docker run -d \
  --name proxyboard \
  --restart unless-stopped \
  -p 8088:8088 \
  -v proxyboard-data:/data \
  -e XRAY_DOMAIN=yourdomain.com \
  -e UI_PORT=8088 \
  lahiru98s/proxyboard:latest
```

Open the UI at `http://your-server-ip:8088`

#### With authentication enabled

```bash
docker run -d \
  --name proxyboard \
  --restart unless-stopped \
  -p 8088:8088 \
  -v proxyboard-data:/data \
  -e XRAY_DOMAIN=yourdomain.com \
  -e UI_USERNAME=admin \
  -e UI_PASSWORD=yourpassword \
  lahiru98s/proxyboard:latest
```

#### Using GHCR image

```bash
docker run -d \
  --name proxyboard \
  --restart unless-stopped \
  -p 8088:8088 \
  -v proxyboard-data:/data \
  -e XRAY_DOMAIN=yourdomain.com \
  ghcr.io/nooblk-98/proxyboard:latest
```

---

### Option 2 — Docker Compose

Create a `docker-compose.yml`:

```yaml
services:
  proxyboard:
    image: lahiru98s/proxyboard:latest
    container_name: proxyboard
    restart: unless-stopped
    ports:
      - "8088:8088"
    volumes:
      - proxyboard-data:/data
    environment:
      - XRAY_DOMAIN=yourdomain.com
      - UI_PORT=8088
      # Optional: enable login protection
      # - UI_USERNAME=admin
      # - UI_PASSWORD=yourpassword

volumes:
  proxyboard-data:
```

Then run:

```bash
docker compose up -d
```

Pull latest image and restart:

```bash
docker compose pull && docker compose up -d
```

---

### Option 3 — Production (Nginx + Let's Encrypt SSL)

Use `docker-compose-live.yml` for a fully production-ready setup with automatic HTTPS via Certbot.

**Stack:**
| Service | Role |
|---|---|
| `proxyboard` | App (internal, port 8088) |
| `nginx` | Reverse proxy, HTTP→HTTPS redirect, SSL termination |
| `certbot` | Obtains & auto-renews Let's Encrypt certificate |

**Requirements:**
- Domain DNS A record pointing to your server IP
- Ports **80** and **443** open on your server

**Step 1 — Clone and configure**

```bash
git clone https://github.com/nooblk-98/ProxyBoard.git
cd ProxyBoard
cp .env.example .env
nano .env
```

Set your values in `.env`:

```env
DOMAIN=yourdomain.com
CERTBOT_EMAIL=you@example.com
# Optional login protection
# UI_USERNAME=admin
# UI_PASSWORD=yourpassword
```

**Step 2 — Start**

```bash
docker compose -f docker-compose-live.yml up -d
```

Certbot will automatically obtain a certificate on first start and renew it every 12 hours. The UI will be available at `https://yourdomain.com`.

**Step 3 — Apply Let's Encrypt certs to Xray**

Once Certbot has issued a certificate, set it in ProxyBoard via **Settings → TLS Certificates → Manual Paths**:

| Field | Value |
|---|---|
| Certificate | `/etc/letsencrypt/live/yourdomain.com/fullchain.pem` |
| Private Key | `/etc/letsencrypt/live/yourdomain.com/privkey.pem` |

The certbot volume is mounted read-only into the ProxyBoard container, so these paths are directly accessible.

**Update to latest image:**

```bash
docker compose -f docker-compose-live.yml pull && docker compose -f docker-compose-live.yml up -d
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `XRAY_DOMAIN` | `example.com` | Your domain / SNI for Xray configs |
| `UI_PORT` | `8088` | Web UI port |
| `UI_USERNAME` | `admin` | Login username (auth disabled if `UI_PASSWORD` not set) |
| `UI_PASSWORD` | _(unset)_ | Login password — enables auth when set |
| `UI_PASSWORD_HASH` | _(unset)_ | SHA-256 hash of password (alternative to plain `UI_PASSWORD`) |
| `XRAY_VERSIONS_CONFIG` | `/opt/xray/versions.json` | Path to versions list JSON |
| `XRAY_STABLE_VERSIONS` | _(unset)_ | Comma-separated version list override |

---

## Features

- **Dashboard** — Live CPU, memory, disk, upload/download gauges + traffic history chart
- **Configurations** — Create, edit, enable/disable multiple Xray inbound configs (VLESS/VMESS, WS/TLS)
- **QR Code sharing** — One-click QR and copy for client import URLs
- **Log Viewer** — Live-tail access and error logs with SSE streaming
- **Backup & Restore** — Export/import all configs as JSON
- **Config Validation** — Run Xray's built-in `--test` against active config
- **Version Switcher** — Switch Xray core versions with live download progress bar
- **Auto-restart watchdog** — Automatically restarts Xray if it crashes
- **Auth protection** — Optional username/password login page
- **Light/Dark theme** — Toggle from Settings
- **Docker Healthcheck** — `/healthz` endpoint wired into `HEALTHCHECK`
- **Multi-arch** — `linux/amd64` and `linux/arm64` images

---

## Data & Certificates

All runtime data is stored in `/data` inside the container (mapped to the `proxyboard-data` volume):

```
/data/
  config.json        # Active Xray config
  configs.json       # UI config store
  certs/             # Auto-generated self-signed TLS certs
  logs/              # Xray access and error logs
  xray.pid           # Xray process ID
```

Self-signed certificates are generated automatically on first run. Replace `/data/certs/cert.pem` and `/data/certs/key.pem` with your own for production.

---

## Ports

| Port | Purpose |
|---|---|
| `8088` | Web UI |
| Configured per-inbound | Xray proxy (WS / WS+TLS) |

---

## Developed by [nooblk](https://github.com/nooblk-98)
