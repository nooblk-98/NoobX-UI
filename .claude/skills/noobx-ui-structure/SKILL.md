---
name: noobx-ui-structure
description: >
  Enforces the canonical folder and file structure for the NoobX-UI project (Flask + Xray proxy panel).
  Use this skill whenever working in the NoobX-UI repo — adding files, creating scripts, restructuring
  directories, writing or cleaning the Dockerfile, adding docker-compose files, or placing any new Python
  module. Trigger on phrases like "add a new route", "where should this file go", "create a script",
  "clean up the Dockerfile", "add docker-compose", "restructure the project", "move this file", or any
  time code is being placed inside the NoobX-UI repository. Apply this structure automatically even if
  the user doesn't explicitly ask about structure — if they're building something in NoobX-UI, follow
  these conventions.
---

# NoobX-UI Project Structure

NoobX-UI is a Flask web panel that manages an Xray proxy core. The goal of this structure is to keep
Docker build layers cache-friendly, separate app source from infrastructure config, and make local dev
easy with a single `docker-compose.dev.yml` override.

## Directory map

```
NoobX-UI/
├── Dockerfile                   # Production image (multi-stage friendly)
├── docker-compose.yml           # Production deployment
├── docker-compose.dev.yml       # Dev override — bind-mounts app/, hot reload
├── .dockerignore                # Exclude __pycache__, .git, *.pyc, .env
├── .env.example                 # Document all env vars with safe defaults
├── requirements.txt             # All pip deps — never inline in Dockerfile
│
├── config.default.json          # Default Xray config template
├── xray-versions.json           # Available Xray versions manifest
│
├── scripts/                     # Standalone utility scripts (not imported by app)
│   └── download_xray_versions.py
│
└── app/                         # All application source (was: web/)
    ├── app.py                   # Entry point — calls bootstrap() then app.run()
    │
    ├── ui/                      # Flask application package
    │   ├── __init__.py
    │   ├── main.py              # bootstrap() and get_app() factory
    │   ├── routes.py            # All Flask route definitions via create_app()
    │   ├── constants.py         # Paths, defaults, env-sourced constants
    │   ├── store.py             # JSON config persistence (load/save/build)
    │   ├── auth.py              # Login/logout routes and @login_required
    │   ├── backup.py            # Export/import backup helpers
    │   ├── log_reader.py        # Tail and stream Xray log files
    │   ├── stats.py             # System stats, net speed, Xray traffic stats
    │   ├── system.py            # Dir setup, cert generation, cert path saving
    │   ├── validator.py         # Run `xray -test` against a config dict
    │   ├── watchdog.py          # Background thread to restart Xray if it dies
    │   └── xray_core.py        # Download, switch, start, stop Xray binary
    │
    ├── templates/               # Jinja2 HTML templates
    │   ├── base.html
    │   ├── index.html
    │   └── partials/            # Reusable template fragments
    │
    └── static/                  # CSS, JS, images served directly
        ├── css/
        ├── js/
        └── images/
```

---

## Decision rules — where does this file go?

**Is it a Flask route, page render, or API endpoint?**
→ Add it to `app/ui/routes.py`. For large route groups, create `app/ui/routes/` and split by concern.

**Is it a helper called only by routes (auth check, backup, stats)?**
→ Put it in `app/ui/` as its own module (e.g., `stats.py`, `backup.py`). Import from `routes.py`.

**Is it a one-off CLI utility, build-time script, or download helper?**
→ Put it in `scripts/`. These are never imported by the Flask app.

**Is it an HTML template?**
→ `app/templates/`. Shared fragments go in `app/templates/partials/`.

**Is it a static asset (CSS, JS, image)?**
→ `app/static/`, organized by type (`css/`, `js/`, `images/`).

**Is it a pip dependency?**
→ Add to `requirements.txt` at the repo root. Never inline `pip install` in the Dockerfile.

**Is it an environment variable?**
→ Document it in `.env.example` with a safe default. Read it in `app/ui/constants.py`.

---

## Dockerfile rules

Keep build layers ordered from least-to-most frequently changed so Docker cache is maximally reused:

1. Base image + system packages (changes rarely)
2. `COPY requirements.txt` + `pip install` (changes when deps change)
3. `COPY config.default.json`, `xray-versions.json`, `scripts/` (changes occasionally)
4. Run Xray download script (depends on versions.json)
5. Symlink default Xray binary (read version dynamically, never hardcode)
6. `COPY app/` (changes most often — always last)

The symlink must derive the version from `versions.json` at build time, not be hardcoded:

```dockerfile
RUN XRAY_VER=$(python3 -c "import json; d=json.load(open('/opt/xray/versions.json')); \
    print(d[0]['version'] if isinstance(d, list) else list(d.values())[0]['version'])") \
    && ln -sf /opt/xray/versions/${XRAY_VER}/xray /usr/local/bin/xray \
    && chmod +x /usr/local/bin/xray
```

Always set these ENV vars for cleaner Python in Docker:
```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
```

---

## docker-compose.dev.yml pattern

The dev compose file overrides only what needs to change for local development — it does not duplicate
the full service definition. It bind-mounts `app/` so Flask sees code changes without rebuilding:

```yaml
# docker-compose.dev.yml
services:
  proxyboard:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./app:/opt/xray-web        # live code reload
      - proxyboard-data:/data
    environment:
      - FLASK_DEBUG=1
      - UI_PORT=8088
```

Run dev mode with:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## .dockerignore essentials

Always exclude these to keep the build context lean:

```
__pycache__/
**/__pycache__/
*.pyc
*.pyo
.git/
.env
.env.*
!.env.example
*.egg-info/
.venv/
```

---

## Constants and env vars

All runtime configuration is read once in `app/ui/constants.py` using `os.getenv()` with safe defaults.
No other module should call `os.getenv()` directly — import from `constants.py` instead.

```python
# app/ui/constants.py  (pattern)
import os
from pathlib import Path

UI_PORT     = int(os.getenv("UI_PORT", 8088))
XRAY_BIN    = Path(os.getenv("XRAY_BIN", "/usr/local/bin/xray"))
DATA_DIR    = Path(os.getenv("XRAY_DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "config.json"
```

---

## What NOT to do

- Don't put pip deps inside the Dockerfile — use `requirements.txt`
- Don't hardcode Xray version strings anywhere (Dockerfile symlink, constants, scripts) — read from `versions.json`
- Don't create new top-level directories without a clear reason — fit new code into the existing layout
- Don't call `os.getenv()` outside `constants.py`
- Don't put utility scripts that are never imported by Flask inside `app/ui/` — use `scripts/` instead
- Don't duplicate service config between `docker-compose.yml` and `docker-compose.dev.yml` — dev file should only override what changes
