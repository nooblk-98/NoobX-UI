import json
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, url_for

try:
    import qrcode
except Exception:
    qrcode = None

from datetime import datetime

from .constants import CONFIG_PATH, DATA_DIR, DEFAULTS, DOMAIN, PID_PATH, XRAY_BIN
from .stats import get_active_ports, get_net_speed, get_sys_info, get_xray_stats
from .store import (
    _coerce_int,
    _find_config,
    _load_store,
    _save_store,
    _summary,
    build_config,
    write_config,
)
from .system import ensure_certs, ensure_dirs
from .xray_core import (
    _current_xray_key,
    _now_iso,
    get_xray_version,
    is_xray_running,
    list_xray_versions,
    maybe_install_and_switch,
    start_xray,
)


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
        "xray_bin": str(XRAY_BIN),
        "sys_info": get_sys_info(),
        "up_speed": speeds["up_str"],
        "down_speed": speeds["down_str"],
        "up_raw": speeds["up_raw"],
        "down_raw": speeds["down_raw"],
        "active_ports": active_ports,
        "xray_stats": xray_stats,
    }


def create_app() -> Flask:
    # Get the parent directory of the ui module (which is web/)
    web_dir = Path(__file__).parent.parent
    app = Flask(__name__,
                template_folder=str(web_dir / 'templates'),
                static_folder=str(web_dir / 'static'))

    @app.route("/")
    def index():
        status = get_status()
        xray_versions = list_xray_versions()
        xray_current_key = _current_xray_key(xray_versions)
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
            xray_versions=xray_versions,
            xray_current_key=xray_current_key,
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

        for other_config in store.get("configs", []):
            if other_config.get("id") == form["id"]:
                continue
            if form["ws_enabled"] and other_config.get("ws_enabled"):
                if form["ws_port"] == other_config.get("ws_port"):
                    return redirect(url_for("index", error=f"Port {form['ws_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
            if form["tls_enabled"] and other_config.get("tls_enabled"):
                if form["tls_port"] == other_config.get("tls_port"):
                    return redirect(url_for("index", error=f"Port {form['tls_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
            if form["ws_enabled"] and other_config.get("tls_enabled"):
                if form["ws_port"] == other_config.get("tls_port"):
                    return redirect(url_for("index", error=f"Port {form['ws_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
            if form["tls_enabled"] and other_config.get("ws_enabled"):
                if form["tls_port"] == other_config.get("ws_port"):
                    return redirect(url_for("index", error=f"Port {form['tls_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))

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

        if original_len <= 1:
            return redirect(url_for("index", error="Cannot delete the last configuration. At least one config must exist.") + "#configs")

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

    @app.route("/xray/switch", methods=["POST"])
    def switch_xray():
        version_key = request.form.get("xray_version", "").strip()
        if not version_key:
            return redirect(url_for("index", error="Select an Xray core version.") + "#settings")
        ok, msg = maybe_install_and_switch(version_key)
        if ok:
            return redirect(url_for("index", message=msg) + "#settings")
        return redirect(url_for("index", error=msg) + "#settings")

    @app.route("/status")
    def status():
        return jsonify(get_status())

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True, "time": _now_iso()})

    return app
