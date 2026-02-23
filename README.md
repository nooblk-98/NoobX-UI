# Xray Server Web UI

Run Xray with a built-in web UI that edits `config.json`, restarts the server, and shows status.

## Quick start

1. Edit `docker-compose.yml` and set your domain:
```yaml
environment:
  - UI_PORT=8088
  - XRAY_DOMAIN=yourdomain.com
```

2. Start the server:
```bash
docker compose up -d --build
```

Open the UI at:

- **HTTP:** `http://localhost:8088`
- **HTTPS:** `https://localhost:8089` (self-signed cert)

## What you get

- Web UI to edit the full Xray JSON config
- Status page showing running state and last config update
- Self-signed TLS certs generated on first run in `/data/certs`

## Data persistence

A Docker volume named `xray-data` stores:

- `/data/config.json`
- `/data/certs/`
- `/data/logs/`

## Configuration

Edit these in `docker-compose.yml` under `environment`:

- `XRAY_DOMAIN` - Your domain name (default: `example.com`)
- `UI_PORT` - Web UI port (default: `8088`)

The web UI runs on two ports:
- Port 8088: HTTP (unencrypted)
- Port 8089: HTTPS (with self-signed certificate)

## Notes

- Ports `80`, `443`, `8080`, `8443` are mapped by default. Adjust `docker-compose.yml` if you need different ports.
- Replace the self-signed certs in `/data/certs` for production use.