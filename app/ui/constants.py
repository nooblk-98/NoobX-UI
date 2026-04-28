import os
from pathlib import Path
from uuid import uuid4

DATA_DIR = Path(os.environ.get("XRAY_DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "config.json"
CONFIGS_PATH = DATA_DIR / "configs.json"
CERT_DIR = DATA_DIR / "certs"
LOG_DIR = DATA_DIR / "logs"
PID_PATH = DATA_DIR / "xray.pid"
XRAY_BIN = Path(os.environ.get("XRAY_BIN", "/usr/local/bin/xray"))
XRAY_VERSIONS_DIR = Path(os.environ.get("XRAY_VERSIONS_DIR", "/data/xray/versions"))
XRAY_VERSION_FILE = DATA_DIR / "xray.version"
XRAY_STABLE_VERSIONS = os.environ.get("XRAY_STABLE_VERSIONS", "").strip()
XRAY_VERSIONS_CONFIG = Path(os.environ.get("XRAY_VERSIONS_CONFIG", "/opt/xray/versions.json"))
XRAY_RELEASE_BASE = "https://github.com/XTLS/Xray-core/releases/download"
UI_PORT = int(os.environ.get("UI_PORT", "8088"))
DOMAIN = os.environ.get("XRAY_DOMAIN", "example.com")

DEFAULTS = {
    "name": "Default Config",
    "domain": DOMAIN,
    "protocol": "vless",
    "ws_enabled": False,
    "ws_port": 80,
    "ws_path": "/ws",
    "ws_uuid": str(uuid4()),
    "ws_email": "client80@example.com",
    "ws_host": DOMAIN,
    "tls_enabled": True,
    "tls_port": 443,
    "tls_path": "/wstls",
    "tls_uuid": str(uuid4()),
    "tls_email": "client443@example.com",
    "tls_cert": "/data/certs/cert.pem",
    "tls_key": "/data/certs/key.pem",
    "tls_host": DOMAIN,
    "dns": "1.1.1.1",
    "fingerprint": "randomized",
    "alpn": "h2,h3,http/1.1",
    "socks5_enabled": False,
    "socks5_port": 1080,
    "socks5_username": "socks5user",
    "socks5_password": "",
}
