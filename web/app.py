from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, url_for

try:
    import qrcode
except Exception:
    qrcode = None

app = Flask(__name__)

DATA_DIR = Path(os.environ.get("XRAY_DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "config.json"
CONFIGS_PATH = DATA_DIR / "configs.json"
CERT_DIR = DATA_DIR / "certs"
LOG_DIR = DATA_DIR / "logs"
PID_PATH = DATA_DIR / "xray.pid"
XRAY_BIN = "/usr/local/bin/xray"
UI_PORT = int(os.environ.get("UI_PORT", "8088"))
DOMAIN = os.environ.get("XRAY_DOMAIN", "example.com")

_xray_process = None


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
}


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def ensure_certs(domain: str) -> None:
    cert_path = CERT_DIR / "cert.pem"
    key_path = CERT_DIR / "key.pem"
    if cert_path.exists() and key_path.exists():
        return
    subject = f"/C=US/ST=State/L=City/O=Organization/CN={domain}"
    cmd = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-days",
        "365",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-subj",
        subject,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def get_sys_info() -> dict:
    info = {"cpu": "0.00", "mem": "0.0%"}
    import platform
    if platform.system() == "Linux":
        try:
            with open('/proc/loadavg', 'r') as f:
                info["cpu"] = f.read().split()[0]
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                total = available = 0
                for line in lines:
                    if line.startswith('MemTotal:'):
                        total = int(line.split()[1])
                    elif line.startswith('MemAvailable:'):
                        available = int(line.split()[1])
                if total > 0:
                    used = total - available
                    info["mem"] = f"{(used / total) * 100:.1f}%"
        except Exception:
            pass
    return info


_last_net_io = None
_last_net_time = None
_last_speeds = {"up": 0.0, "down": 0.0}

def get_net_speed() -> dict:
    global _last_net_io, _last_net_time, _last_speeds
    up_speed = 0.0
    down_speed = 0.0
    import platform
    import time
    if platform.system() == "Linux":
        try:
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()
            rx_bytes = 0
            tx_bytes = 0
            for line in lines[2:]:
                if "lo:" in line:
                    continue
                parts = line.split(':')
                if len(parts) == 2:
                    ifparts = parts[1].split()
                    rx_bytes += int(ifparts[0])
                    tx_bytes += int(ifparts[8])
            now = time.time()
            if _last_net_time is not None and _last_net_io is not None:
                elapsed = now - _last_net_time
                if elapsed > 0.5:  # Only calculate if at least 0.5 seconds have passed
                    down_speed = (rx_bytes - _last_net_io[0]) / elapsed
                    up_speed = (tx_bytes - _last_net_io[1]) / elapsed
                    # Apply smoothing - average with last reading (0.6 new, 0.4 old)
                    down_speed = (down_speed * 0.6) + (_last_speeds["down"] * 0.4)
                    up_speed = (up_speed * 0.6) + (_last_speeds["up"] * 0.4)
                else:
                    # Use last reading if interval too small
                    down_speed = _last_speeds["down"]
                    up_speed = _last_speeds["up"]
            _last_net_io = (rx_bytes, tx_bytes)
            _last_net_time = now
            _last_speeds["up"] = up_speed
            _last_speeds["down"] = down_speed
        except Exception:
            pass
            
    def format_bytes(b):
        if b < 1024:
            return f"{b:.1f} B"
        elif b < 1024 * 1024:
            return f"{b/1024:.1f} KB"
        elif b < 1024 * 1024 * 1024:
            return f"{b/1024/1024:.1f} MB"
        else:
            return f"{b/1024/1024/1024:.1f} GB"

    def format_speed(b):
        return f"{format_bytes(b)}/s"
            
    return {
        "up_str": format_speed(max(0, up_speed)),
        "down_str": format_speed(max(0, down_speed)),
        "up_raw": max(0, up_speed) / 1024,
        "down_raw": max(0, down_speed) / 1024
    }

def format_bytes_global(b):
    if b < 1024:
        return f"{b:.1f} B"
    elif b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b/1024/1024:.1f} MB"
    else:
        return f"{b/1024/1024/1024:.1f} GB"

def get_active_ports() -> list:
    active_ports = set()
    import platform
    if platform.system() == "Linux":
        for net_file in ["/proc/net/tcp", "/proc/net/tcp6"]:
            try:
                with open(net_file, "r") as f:
                    lines = f.readlines()[1:]
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 4:
                        if parts[3] == "01": # ESTABLISHED
                            local_addr = parts[1]
                            if ":" in local_addr:
                                port_hex = local_addr.split(":")[1]
                                active_ports.add(int(port_hex, 16))
            except Exception:
                pass
    return list(active_ports)

_last_stats = {}
_last_stats_time = 0

def get_xray_stats() -> dict:
    global _last_stats, _last_stats_time
    import time
    now = time.time()
    current_stats = {}
    
    if is_xray_running():
        try:
            res = subprocess.run([XRAY_BIN, "api", "statsquery", "-server=127.0.0.1:10085"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                for item in data.get("stat", []):
                    name = item.get("name", "")
                    value = int(item.get("value", 0))
                    parts = name.split(">>>")
                    if len(parts) == 4 and parts[0] == "user" and parts[2] == "traffic":
                        email = parts[1]
                        direction = parts[3]
                        if email not in current_stats:
                            current_stats[email] = {"up": 0, "down": 0}
                        if direction == "uplink":
                            current_stats[email]["up"] += value
                        elif direction == "downlink":
                            current_stats[email]["down"] += value
        except Exception:
            pass

    elapsed = now - _last_stats_time if _last_stats_time else 0
    output = {}
    for email, traffic in current_stats.items():
        prev = _last_stats.get(email, {"up": 0, "down": 0})
        up_diff = max(0, traffic["up"] - prev["up"])
        down_diff = max(0, traffic["down"] - prev["down"])
        
        up_speed = up_diff / elapsed if elapsed > 0 else 0
        down_speed = down_diff / elapsed if elapsed > 0 else 0
        
        output[email] = {
            "total_str": f"{format_bytes_global(traffic['down'])} \u2193 {format_bytes_global(traffic['up'])} \u2191",
            "speed_str": f"{format_bytes_global(down_speed)}/s \u2193 {format_bytes_global(up_speed)}/s \u2191"
        }
        
    _last_stats = current_stats
    _last_stats_time = now
    return output


def get_xray_version() -> str:
    try:
        res = subprocess.run([XRAY_BIN, "version"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            lines = res.stdout.split('\n')
            if lines:
                m = re.search(r"Xray\s+([\d\.]+)", lines[0])
                if m:
                    return m.group(1)
                return lines[0].strip()
    except Exception:
        pass
    return "Unknown"


def is_xray_running() -> bool:
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except ValueError:
            return False
        return _pid_running(pid)
    return _xray_process is not None and _xray_process.poll() is None


def stop_xray() -> None:
    global _xray_process
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
            if _pid_running(pid):
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
        except Exception:
            pass
        try:
            PID_PATH.unlink(missing_ok=True)
        except Exception:
            pass
    if _xray_process is not None and _xray_process.poll() is None:
        _xray_process.terminate()
        _xray_process = None


def start_xray() -> None:
    global _xray_process
    stop_xray()
    if not CONFIG_PATH.exists():
        return
    _xray_process = subprocess.Popen([XRAY_BIN, "-c", str(CONFIG_PATH)])
    PID_PATH.write_text(str(_xray_process.pid), encoding="utf-8")


def get_status() -> dict:
    config_exists = CONFIG_PATH.exists()
    config_mtime = None
    if config_exists:
        config_mtime = datetime.utcfromtimestamp(CONFIG_PATH.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    running = is_xray_running()
    pid = None
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
            
    speeds = get_net_speed()
    active_ports = get_active_ports()
    xray_stats = get_xray_stats()
    
    return {
        "running": running,
        "pid": pid,
        "config_exists": config_exists,
        "config_mtime": config_mtime,
        "data_dir": str(DATA_DIR),
        "domain": DOMAIN,
        "now": _now_iso(),
        "xray_version": get_xray_version(),
        "sys_info": get_sys_info(),
        "up_speed": speeds["up_str"],
        "down_speed": speeds["down_str"],
        "up_raw": speeds["up_raw"],
        "down_raw": speeds["down_raw"],
        "active_ports": active_ports,
        "xray_stats": xray_stats,
    }


def _read_config() -> dict | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _coerce_int(value: str, field: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a number") from exc
    if number < 1 or number > 65535:
        raise ValueError(f"{field} must be 1-65535")
    return number


def load_form_state() -> dict:
    data = dict(DEFAULTS)
    cfg = _read_config()
    if not cfg:
        return data

    inbounds = cfg.get("inbounds", [])
    for inbound in inbounds:
        stream = inbound.get("streamSettings", {})
        network = stream.get("network")
        security = stream.get("security", "")
        settings = inbound.get("settings", {})
        clients = settings.get("clients", [])
        client = clients[0] if clients else {}
        ws_settings = stream.get("wsSettings", {})

        if network == "ws" and not security:
            data["ws_enabled"] = True
            data["ws_port"] = inbound.get("port", data["ws_port"])
            data["ws_path"] = ws_settings.get("path", data["ws_path"])
            data["ws_uuid"] = client.get("id", data["ws_uuid"])
            data["ws_email"] = client.get("email", data["ws_email"])
            data["protocol"] = inbound.get("protocol", data["protocol"])
            host = ws_settings.get("host")
            if host:
                data["ws_host"] = host

        if network == "ws" and security == "tls":
            data["tls_enabled"] = True
            data["tls_port"] = inbound.get("port", data["tls_port"])
            data["tls_path"] = ws_settings.get("path", data["tls_path"])
            data["tls_uuid"] = client.get("id", data["tls_uuid"])
            data["tls_email"] = client.get("email", data["tls_email"])
            data["protocol"] = inbound.get("protocol", data["protocol"])
            host = ws_settings.get("host")
            if host:
                data["tls_host"] = host
            tls_settings = stream.get("tlsSettings", {})
            certs = tls_settings.get("certificates", [])
            if certs:
                data["tls_cert"] = certs[0].get("certificateFile", data["tls_cert"])
                data["tls_key"] = certs[0].get("keyFile", data["tls_key"])

    return data


def _load_store() -> dict:
    if not CONFIGS_PATH.exists():
        default_item = dict(DEFAULTS)
        default_item["id"] = str(uuid4())
        default_item["enabled"] = True
        store = {"configs": [default_item]}
        CONFIGS_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return store
    try:
        store = json.loads(CONFIGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        default_item = dict(DEFAULTS)
        default_item["id"] = str(uuid4())
        default_item["enabled"] = True
        store = {"configs": [default_item]}
        CONFIGS_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")
        return store
    
    migrated = False
    for c in store.get("configs", []):
        if "enabled" not in c:
            c["enabled"] = (c.get("id") == store.get("active_id", ""))
            migrated = True
    if migrated:
        _save_store(store)
    return store


def _save_store(store: dict) -> None:
    CONFIGS_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _find_config(store: dict, config_id: str) -> dict | None:
    for item in store.get("configs", []):
        if item.get("id") == config_id:
            return item
    return None


def _summary(item: dict) -> str:
    parts = []
    if item.get("ws_enabled"):
        parts.append(f"WS:{item.get('ws_port')}")
    if item.get("tls_enabled"):
        parts.append(f"WS+TLS:{item.get('tls_port')}")
    return " | ".join(parts) if parts else "Disabled"


def build_config(configs: list) -> dict:
    inbounds = []
    for form in configs:
        if not form.get("enabled", True):
            continue

        domain = form["domain"]
        ws_enabled = form.get("ws_enabled", False)
        tls_enabled = form.get("tls_enabled", False)
        ws_host = form.get("ws_host", domain)
        tls_host = form.get("tls_host", domain)
        protocol = form.get("protocol", "vless")
        cid = form.get("id", "")

        if ws_enabled:
            ws_client = {
                "id": form["ws_uuid"],
                "level": 0,
                "email": form["ws_email"],
            }
            if protocol == "vmess":
                ws_client["alterId"] = 0
            inbounds.append(
                {
                    "port": form["ws_port"],
                    "listen": "0.0.0.0",
                    "protocol": protocol,
                    "tag": f"ws-{cid}",
                    "settings": {
                        "clients": [ws_client],
                        **({"decryption": "none"} if protocol == "vless" else {}),
                    },
                    "streamSettings": {
                        "network": "ws",
                        "wsSettings": {
                            "path": form["ws_path"],
                            "host": ws_host,
                        },
                    },
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"],
                        "metadataOnly": False,
                    },
                }
            )

        if tls_enabled:
            tls_client = {
                "id": form["tls_uuid"],
                "level": 0,
                "email": form["tls_email"],
            }
            if protocol == "vmess":
                tls_client["alterId"] = 0
            inbounds.append(
                {
                    "port": form["tls_port"],
                    "listen": "0.0.0.0",
                    "protocol": protocol,
                    "tag": f"ws-tls-{cid}",
                    "settings": {
                        "clients": [tls_client],
                        **({"decryption": "none"} if protocol == "vless" else {}),
                    },
                    "streamSettings": {
                        "network": "ws",
                        "security": "tls",
                        "tlsSettings": {
                            "serverName": tls_host,
                            "certificates": [
                                {
                                    "certificateFile": form["tls_cert"],
                                    "keyFile": form["tls_key"],
                                }
                            ],
                            "minVersion": "1.2",
                            "maxVersion": "1.3",
                            "cipherSuites": "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305:TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256",
                            "fingerprint": form["fingerprint"],
                            "alpn": [s.strip() for s in form["alpn"].split(",")],
                            "allowInsecure": False,
                        },
                        "wsSettings": {
                            "path": form["tls_path"],
                            "host": tls_host,
                        },
                    },
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"],
                        "metadataOnly": False,
                    },
                }
            )

    inbounds.append({
        "listen": "127.0.0.1",
        "port": 10085,
        "protocol": "dokodemo-door",
        "settings": {
            "address": "127.0.0.1"
        },
        "tag": "api"
    })

    return {
        "log": {
            "loglevel": "info",
            "access": "/data/logs/access.log",
            "error": "/data/logs/error.log",
        },
        "api": {
            "tag": "api",
            "services": ["StatsService"]
        },
        "stats": {},
        "policy": {
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True
                }
            },
            "system": {
                "statsInboundUplink": True,
                "statsInboundDownlink": True,
                "statsOutboundUplink": True,
                "statsOutboundDownlink": True
            }
        },
        "inbounds": inbounds,
        "outbounds": [
            {"protocol": "freedom", "settings": {}, "tag": "direct"},
            {"protocol": "blackhole", "settings": {}, "tag": "blocked"},
        ],
        "dns": {
            "servers": [
                {
                    "address": form.get("dns", DEFAULTS["dns"]),
                    "port": 53
                }
            ]
        },
        "routing": {
            "domainStrategy": "IPOnDemand",
            "rules": [
                {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
                {"type": "field", "domain": ["geosite:private"], "outboundTag": "blocked"},
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "blocked"},
            ],
        },
    }


def read_config_text() -> str:
    if not CONFIG_PATH.exists():
        return ""
    return CONFIG_PATH.read_text(encoding="utf-8")


def write_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _vmess_link(name: str, domain: str, port: int, uuid: str, path: str, tls: bool, host: str = "") -> str:
    host = host or domain
    payload = {
        "v": "2",
        "ps": name,
        "add": domain,
        "port": str(port),
        "id": uuid,
        "aid": "0",
        "net": "ws",
        "type": "none",
        "host": host,
        "path": path,
        "tls": "tls" if tls else "",
        "sni": host if tls else "",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = __import__("base64").b64encode(raw).decode("utf-8").rstrip("=")
    return f"vmess://{b64}"


def _vless_link(name: str, domain: str, port: int, uuid: str, path: str, tls: bool, host: str = "") -> str:
    host = host or domain
    base = f"vless://{uuid}@{domain}:{port}"
    if tls:
        return f"{base}?type=ws&path={path}&security=tls&sni={host}&host={host}#{name}"
    return f"{base}?type=ws&path={path}&host={host}#{name}"


def _qr_data(url: str) -> str | None:
    if qrcode is None:
        return None
    qr = qrcode.QRCode(border=2, box_size=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + __import__("base64").b64encode(buf.getvalue()).decode("utf-8")


@app.route("/")
def index():
    status = get_status()
    store = _load_store()
    edit_id = request.args.get("edit")
    
    if edit_id == "new":
        form_state = dict(DEFAULTS)
    elif edit_id:
        found = _find_config(store, edit_id)
        if found:
            form_state = dict(found)
            if "protocol" not in form_state:
                form_state["protocol"] = DEFAULTS["protocol"]
        else:
            form_state = dict(DEFAULTS)
    else:
        form_state = dict(DEFAULTS)

    active_count = 0
    configs = store.get("configs", [])
    for c in configs:
        if c.get("enabled", True):
            active_count += 1
            
        c["links"] = []
        proto = c.get("protocol", "vless")
        name = c.get("name", "Config")
        domain = c.get("domain", DOMAIN)
        ws_host = c.get("ws_host", domain)
        tls_host = c.get("tls_host", domain)
        if c.get("tls_enabled"):
            url = _vless_link(name, domain, c["tls_port"], c["tls_uuid"], c["tls_path"], True, tls_host) if proto == "vless" else _vmess_link(name, domain, c["tls_port"], c["tls_uuid"], c["tls_path"], True, tls_host)
            c["links"].append({"label": "WebSocket + TLS", "url": url, "qr": _qr_data(url)})
        if c.get("ws_enabled"):
            url = _vless_link(name, domain, c["ws_port"], c["ws_uuid"], c["ws_path"], False, ws_host) if proto == "vless" else _vmess_link(name, domain, c["ws_port"], c["ws_uuid"], c["ws_path"], False, ws_host)
            c["links"].append({"label": "WebSocket (No TLS)", "url": url, "qr": _qr_data(url)})

    message = request.args.get("message")
    error = request.args.get("error")
    return render_template(
        "index.html",
        status=status,
        form=form_state,
        store=store,
        active_count=active_count,
        configs=configs,
        edit_id=edit_id,
        summary=_summary,
        message=message,
        error=error,
        DEFAULTS=DEFAULTS,
    )


@app.route("/save", methods=["POST"])
def save():
    store = _load_store()
    edit_id = request.form.get("edit_id")
    if edit_id == "new":
        edit_id = None
        
    form = {
        "id": edit_id or str(uuid4()),
        "name": request.form.get("name", DEFAULTS["name"]).strip() or DEFAULTS["name"],
        "domain": request.form.get("domain", DEFAULTS["domain"]).strip() or DEFAULTS["domain"],
        "protocol": request.form.get("protocol", DEFAULTS["protocol"]).strip() or DEFAULTS["protocol"],
        "ws_enabled": request.form.get("network_security") == "ws",
        "tls_enabled": request.form.get("network_security") == "tls",
        "ws_path": request.form.get("ws_path", DEFAULTS["ws_path"]).strip() or DEFAULTS["ws_path"],
        "tls_path": request.form.get("tls_path", DEFAULTS["tls_path"]).strip() or DEFAULTS["tls_path"],
        "ws_host": request.form.get("ws_host", request.form.get("domain", DEFAULTS["domain"])).strip() or DEFAULTS["domain"],
        "tls_host": request.form.get("tls_host", request.form.get("domain", DEFAULTS["domain"])).strip() or DEFAULTS["domain"],
        "ws_uuid": request.form.get("ws_uuid", "").strip() or str(uuid4()),
        "tls_uuid": request.form.get("tls_uuid", "").strip() or str(uuid4()),
        "ws_email": request.form.get("ws_email", DEFAULTS["ws_email"]).strip(),
        "tls_email": request.form.get("tls_email", DEFAULTS["tls_email"]).strip(),
        "tls_cert": request.form.get("tls_cert", DEFAULTS["tls_cert"]).strip() or DEFAULTS["tls_cert"],
        "tls_key": request.form.get("tls_key", DEFAULTS["tls_key"]).strip() or DEFAULTS["tls_key"],
        "dns": request.form.get("dns", DEFAULTS["dns"]).strip() or DEFAULTS["dns"],
        "fingerprint": request.form.get("fingerprint", DEFAULTS["fingerprint"]).strip() or DEFAULTS["fingerprint"],
        "alpn": request.form.get("alpn", DEFAULTS["alpn"]).strip() or DEFAULTS["alpn"],
    }

    try:
        if form["ws_enabled"]:
            form["ws_port"] = _coerce_int(request.form.get("ws_port", ""), "WS port")
        else:
            form["ws_port"] = DEFAULTS["ws_port"]
        if form["tls_enabled"]:
            form["tls_port"] = _coerce_int(request.form.get("tls_port", ""), "TLS port")
        else:
            form["tls_port"] = DEFAULTS["tls_port"]
    except ValueError as exc:
        return redirect(url_for("index", error=str(exc), edit=edit_id or "new"))

    if not form["ws_enabled"] and not form["tls_enabled"]:
        return redirect(url_for("index", error="Enable at least one inbound.", edit=edit_id or "new"))

    # Check for port conflicts with other configs
    for other_config in store.get("configs", []):
        if other_config.get("id") == form["id"]:
            continue  # Skip self when editing
        
        # Check WS port conflict
        if form["ws_enabled"] and other_config.get("ws_enabled"):
            if form["ws_port"] == other_config.get("ws_port"):
                return redirect(url_for("index", error=f"Port {form['ws_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
        
        # Check TLS port conflict
        if form["tls_enabled"] and other_config.get("tls_enabled"):
            if form["tls_port"] == other_config.get("tls_port"):
                return redirect(url_for("index", error=f"Port {form['tls_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
        
        # Check cross-protocol port conflict (WS vs TLS)
        if form["ws_enabled"] and other_config.get("tls_enabled"):
            if form["ws_port"] == other_config.get("tls_port"):
                return redirect(url_for("index", error=f"Port {form['ws_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
        
        if form["tls_enabled"] and other_config.get("ws_enabled"):
            if form["tls_port"] == other_config.get("ws_port"):
                return redirect(url_for("index", error=f"Port {form['tls_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))

    # preserve enabled state
    existing = _find_config(store, form["id"])
    if existing:
        form["enabled"] = existing.get("enabled", True)
        existing.update(form)
    else:
        form["enabled"] = True
        store.setdefault("configs", []).append(form)

    ensure_dirs()
    ensure_certs(form["domain"])
    config = build_config(store.get("configs", []))
    write_config(config)
    _save_store(store)
    start_xray()
    return redirect(url_for("index", message="Config saved and Xray restarted.") + "#configs")


@app.route("/new")
def new_config():
    return redirect(url_for("index", edit="new"))


@app.route("/delete/<config_id>", methods=["POST"])
def delete_config(config_id: str):
    store = _load_store()
    original_len = len(store.get("configs", []))
    store["configs"] = [c for c in store.get("configs", []) if c.get("id") != config_id]
    if len(store["configs"]) < original_len:
        ensure_dirs()
        config = build_config(store.get("configs", []))
        write_config(config)
        _save_store(store)
        start_xray()
        return redirect(url_for("index", message="Config deleted.") + "#configs")
    return redirect(url_for("index", error="Config not found.") + "#configs")

@app.route("/toggle/<config_id>", methods=["POST"])
def toggle(config_id: str):
    store = _load_store()
    item = _find_config(store, config_id)
    if not item:
        return redirect(url_for("index", error="Config not found.") + "#configs")
    
    item["enabled"] = not item.get("enabled", True)
    ensure_dirs()
    ensure_certs(item["domain"])
    config = build_config(store.get("configs", []))
    write_config(config)
    _save_store(store)
    start_xray()
    return redirect(url_for("index", message=f"Config {'enabled' if item['enabled'] else 'disabled'}.") + "#configs")


@app.route("/restart", methods=["POST"])
def restart():
    start_xray()
    return redirect(url_for("index", message="Xray restarted."))


@app.route("/status")
def status():
    return jsonify(get_status())


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "time": _now_iso()})


def bootstrap() -> None:
    ensure_dirs()
    store = _load_store()
    if not store.get("configs"):
        default_item = dict(DEFAULTS)
        default_item["id"] = str(uuid4())
        default_item["enabled"] = True
        store["configs"] = [default_item]
        _save_store(store)
    
    if not CONFIG_PATH.exists():
        for c in store.get("configs", []):
            ensure_certs(c["domain"])
        write_config(build_config(store.get("configs", [])))
    start_xray()


if __name__ == "__main__":
    bootstrap()
    app.run(host="0.0.0.0", port=UI_PORT, debug=False)
