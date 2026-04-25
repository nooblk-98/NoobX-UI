import base64
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for

try:
    import qrcode
except Exception:
    qrcode = None

import io

from .auth import AUTH_ENABLED, login_required, register_auth_routes
from .backup import export_backup, import_backup
from .constants import CONFIG_PATH, DATA_DIR, DEFAULTS, DOMAIN, PID_PATH, XRAY_BIN
from .log_reader import ACCESS_LOG, ERROR_LOG, stream_log, tail_file
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
from .system import ensure_certs, ensure_dirs, regenerate_self_signed, save_manual_cert_paths
from .validator import validate_config
from .xray_core import (
    _current_xray_key,
    _now_iso,
    download_with_progress,
    get_xray_version,
    is_xray_running,
    list_xray_versions,
    maybe_install_and_switch,
    start_xray,
    switch_xray_version,
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
    b64 = base64.b64encode(raw).decode("utf-8").rstrip("=")
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
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")


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


def _prepare_configs_data():
    """Helper function to prepare configuration data"""
    store = _load_store()
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
    
    return store, configs, active_count


def create_app() -> Flask:
    web_dir = Path(__file__).parent.parent
    app = Flask(__name__,
                template_folder=str(web_dir / 'templates'),
                static_folder=str(web_dir / 'static'))

    register_auth_routes(app)

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    @app.before_request
    def suppress_status_logs():
        if request.path in ['/status', '/healthz']:
            logging.getLogger('werkzeug').setLevel(logging.ERROR)
        else:
            logging.getLogger('werkzeug').setLevel(logging.INFO)

    @app.context_processor
    def inject_auth():
        return {"auth_enabled": AUTH_ENABLED}

    @app.route("/")
    def index():
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        status = get_status()
        xray_versions = list_xray_versions()
        xray_current_key = _current_xray_key(xray_versions)
        store, configs, active_count = _prepare_configs_data()
        message = request.args.get("message")
        error = request.args.get("error")
        return render_template(
            "index.html",
            page="dashboard",
            status=status,
            xray_versions=xray_versions,
            xray_current_key=xray_current_key,
            form=dict(DEFAULTS),
            store=store,
            active_count=active_count,
            configs=configs,
            edit_id=None,
            summary=_summary,
            message=message,
            error=error,
            DEFAULTS=DEFAULTS,
        )

    @app.route("/configurations")
    @login_required
    def configurations():
        status = get_status()
        xray_versions = list_xray_versions()
        xray_current_key = _current_xray_key(xray_versions)
        store, configs, active_count = _prepare_configs_data()
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

        message = request.args.get("message")
        error = request.args.get("error")
        return render_template(
            "index.html",
            page="configurations",
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

    @app.route("/settings")
    @login_required
    def settings():
        status = get_status()
        xray_versions = list_xray_versions()
        xray_current_key = _current_xray_key(xray_versions)
        store, configs, active_count = _prepare_configs_data()
        message = request.args.get("message")
        error = request.args.get("error")
        return render_template(
            "index.html",
            page="settings",
            status=status,
            xray_versions=xray_versions,
            xray_current_key=xray_current_key,
            form=dict(DEFAULTS),
            store=store,
            active_count=active_count,
            configs=configs,
            edit_id=None,
            summary=_summary,
            message=message,
            error=error,
            DEFAULTS=DEFAULTS,
        )

    @app.route("/save", methods=["POST"])
    @login_required
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
            return redirect(url_for("configurations", error=str(exc), edit=edit_id or "new"))

        if not form["ws_enabled"] and not form["tls_enabled"]:
            return redirect(url_for("configurations", error="Enable at least one inbound.", edit=edit_id or "new"))

        for other_config in store.get("configs", []):
            if other_config.get("id") == form["id"]:
                continue
            if form["ws_enabled"] and other_config.get("ws_enabled"):
                if form["ws_port"] == other_config.get("ws_port"):
                    return redirect(url_for("configurations", error=f"Port {form['ws_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
            if form["tls_enabled"] and other_config.get("tls_enabled"):
                if form["tls_port"] == other_config.get("tls_port"):
                    return redirect(url_for("configurations", error=f"Port {form['tls_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
            if form["ws_enabled"] and other_config.get("tls_enabled"):
                if form["ws_port"] == other_config.get("tls_port"):
                    return redirect(url_for("configurations", error=f"Port {form['ws_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))
            if form["tls_enabled"] and other_config.get("ws_enabled"):
                if form["tls_port"] == other_config.get("ws_port"):
                    return redirect(url_for("configurations", error=f"Port {form['tls_port']} is already used by '{other_config.get('name')}'", edit=edit_id or "new"))

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
        return redirect(url_for("configurations", message="Config saved and Xray restarted."))

    @app.route("/new")
    @login_required
    def new_config():
        return redirect(url_for("configurations", edit="new"))

    @app.route("/delete/<config_id>", methods=["POST"])
    @login_required
    def delete_config(config_id: str):
        store = _load_store()
        original_len = len(store.get("configs", []))

        if original_len <= 1:
            return redirect(url_for("configurations", error="Cannot delete the last configuration. At least one config must exist."))

        store["configs"] = [c for c in store.get("configs", []) if c.get("id") != config_id]
        if len(store["configs"]) < original_len:
            ensure_dirs()
            config = build_config(store.get("configs", []))
            write_config(config)
            _save_store(store)
            start_xray()
            return redirect(url_for("configurations", message="Config deleted."))
        return redirect(url_for("configurations", error="Config not found."))

    @app.route("/toggle/<config_id>", methods=["POST"])
    @login_required
    def toggle(config_id: str):
        store = _load_store()
        item = _find_config(store, config_id)
        if not item:
            return redirect(url_for("configurations", error="Config not found."))

        item["enabled"] = not item.get("enabled", True)
        ensure_dirs()
        ensure_certs(item["domain"])
        config = build_config(store.get("configs", []))
        write_config(config)
        _save_store(store)
        start_xray()
        return redirect(url_for("configurations", message=f"Config {'enabled' if item['enabled'] else 'disabled'}."))

    @app.route("/restart", methods=["POST"])
    @login_required
    def restart():
        start_xray()
        return redirect(url_for("dashboard", message="Xray restarted."))

    @app.route("/xray/switch", methods=["POST"])
    @login_required
    def switch_xray():
        version_key = request.form.get("xray_version", "").strip()
        if not version_key:
            return redirect(url_for("settings", error="Select an Xray core version."))
        ok, msg = maybe_install_and_switch(version_key)
        if ok:
            return redirect(url_for("settings", message=msg))
        return redirect(url_for("settings", error=msg))

    @app.route("/xray/install-stream/<version_key>")
    @login_required
    def install_stream(version_key: str):
        import json as _json
        import queue
        import threading

        versions = {v["key"]: v for v in list_xray_versions()}
        entry = versions.get(version_key)

        def generate():
            if not entry:
                yield f"data: {_json.dumps({'type': 'error', 'msg': 'Version not found.'})}\n\n"
                return

            if entry.get("installed"):
                yield f"data: {_json.dumps({'type': 'status', 'msg': 'Already installed, switching...'})}\n\n"
                ok, msg = switch_xray_version(version_key)
                yield f"data: {_json.dumps({'type': 'done' if ok else 'error', 'msg': msg})}\n\n"
                return

            q: queue.Queue = queue.Queue()

            def _run():
                def _cb(pct: int, status: str):
                    q.put({"type": "progress", "pct": pct, "msg": status})
                r = download_with_progress(version_key, _cb)
                q.put({"done": True, "ok": r[0], "msg": r[1]})

            threading.Thread(target=_run, daemon=True).start()

            while True:
                item = q.get()
                if item.get("done"):
                    if item["ok"]:
                        ok2, msg2 = switch_xray_version(version_key)
                        yield f"data: {_json.dumps({'type': 'done' if ok2 else 'error', 'msg': msg2, 'pct': 100})}\n\n"
                    else:
                        yield f"data: {_json.dumps({'type': 'error', 'msg': item['msg']})}\n\n"
                    break
                yield f"data: {_json.dumps(item)}\n\n"

        return Response(generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.route("/logs")
    @login_required
    def logs():
        status = get_status()
        xray_versions = list_xray_versions()
        xray_current_key = _current_xray_key(xray_versions)
        store, configs, active_count = _prepare_configs_data()
        access_lines = tail_file(ACCESS_LOG)
        error_lines = tail_file(ERROR_LOG)
        return render_template(
            "index.html",
            page="logs",
            status=status,
            xray_versions=xray_versions,
            xray_current_key=xray_current_key,
            form=dict(DEFAULTS),
            store=store,
            active_count=active_count,
            configs=configs,
            edit_id=None,
            summary=_summary,
            message=None,
            error=None,
            DEFAULTS=DEFAULTS,
            access_lines=access_lines,
            error_lines=error_lines,
        )

    @app.route("/logs/stream/<log_type>")
    @login_required
    def log_stream(log_type: str):
        path = ACCESS_LOG if log_type == "access" else ERROR_LOG
        return Response(stream_log(path), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.route("/backup/export")
    @login_required
    def backup_export():
        data, filename = export_backup()
        buf = io.BytesIO(data.encode("utf-8"))
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/json")

    @app.route("/backup/import", methods=["POST"])
    @login_required
    def backup_import():
        f = request.files.get("backup_file")
        if not f:
            return redirect(url_for("settings", error="No file uploaded."))
        try:
            raw = f.read().decode("utf-8")
        except Exception:
            return redirect(url_for("settings", error="Could not read uploaded file."))
        ok, msg = import_backup(raw)
        if not ok:
            return redirect(url_for("settings", error=msg))
        store = _load_store()
        config = build_config(store.get("configs", []))
        write_config(config)
        start_xray()
        return redirect(url_for("configurations", message=msg))

    @app.route("/cert/self-signed", methods=["POST"])
    @login_required
    def cert_self_signed():
        store = _load_store()
        domain = store.get("domain", DOMAIN)
        ok, msg = regenerate_self_signed(domain)
        if ok:
            return redirect(url_for("settings", message=msg))
        return redirect(url_for("settings", error=msg))

    @app.route("/cert/manual", methods=["POST"])
    @login_required
    def cert_manual():
        cert_src = request.form.get("cert_path", "").strip()
        key_src = request.form.get("key_path", "").strip()
        if not cert_src or not key_src:
            return redirect(url_for("settings", error="Both certificate and key paths are required."))
        ok, msg = save_manual_cert_paths(cert_src, key_src)
        if ok:
            return redirect(url_for("settings", message=msg))
        return redirect(url_for("settings", error=msg))

    @app.route("/config/validate", methods=["POST"])
    @login_required
    def config_validate():
        store = _load_store()
        config = build_config(store.get("configs", []))
        ok, msg = validate_config(config)
        return jsonify({"ok": ok, "msg": msg})

    @app.route("/status")
    def status():
        return jsonify(get_status())

    @app.route("/healthz")
    def healthz():
        running = is_xray_running()
        code = 200 if running else 503
        return jsonify({"ok": running, "time": _now_iso()}), code

    return app
