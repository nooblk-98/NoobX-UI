import json
import os
import re
import shutil
import signal
import subprocess
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from .constants import (
    CONFIG_PATH,
    PID_PATH,
    XRAY_BIN,
    XRAY_RELEASE_BASE,
    XRAY_STABLE_VERSIONS,
    XRAY_VERSIONS_CONFIG,
    XRAY_VERSIONS_DIR,
    XRAY_VERSION_FILE,
)

_xray_process = None


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def get_xray_version() -> str:
    try:
        res = subprocess.run([str(XRAY_BIN), "version"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            lines = res.stdout.split("\n")
            if lines:
                m = re.search(r"Xray\s+([\d\.]+)", lines[0])
                if m:
                    return m.group(1)
                return lines[0].strip()
    except Exception:
        pass
    return "Unknown"


def _version_from_binary(path: Path) -> str:
    try:
        res = subprocess.run([str(path), "version"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            lines = res.stdout.split("\n")
            if lines:
                m = re.search(r"Xray\s+([\d\.]+)", lines[0])
                if m:
                    return m.group(1)
                return lines[0].strip()
    except Exception:
        pass
    return "Unknown"


def _parse_stable_versions() -> list[str]:
    if XRAY_STABLE_VERSIONS:
        values = []
        for item in XRAY_STABLE_VERSIONS.split(","):
            tag = item.strip()
            if tag:
                values.append(tag)
        return values

    if XRAY_VERSIONS_CONFIG.exists():
        try:
            payload = json.loads(XRAY_VERSIONS_CONFIG.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [str(v).strip() for v in payload if str(v).strip()]
            versions = payload.get("versions", [])
            return [str(v).strip() for v in versions if str(v).strip()]
        except Exception:
            return []

    return []


def list_xray_versions() -> list[dict]:
    versions = {}

    if XRAY_VERSIONS_DIR.exists():
        for item in XRAY_VERSIONS_DIR.iterdir():
            if not item.is_dir():
                continue
            candidate = item / "xray"
            if candidate.exists():
                versions[item.name] = candidate

    if XRAY_BIN.parent.exists():
        for item in XRAY_BIN.parent.iterdir():
            if not item.is_file():
                continue
            if item.name.startswith("xray-"):
                key = item.name.replace("xray-", "", 1)
                versions[key] = item

    entries = []
    for key, path in sorted(versions.items()):
        entries.append(
            {
                "key": key,
                "path": str(path),
                "version": _version_from_binary(path),
                "installed": True,
            }
        )

    stable = _parse_stable_versions()
    if stable:
        known_keys = {e["key"] for e in entries}
        for tag in stable:
            if tag in known_keys:
                continue
            entries.append(
                {
                    "key": tag,
                    "path": "",
                    "version": tag,
                    "installed": False,
                }
            )

    return sorted(entries, key=lambda x: x["key"])


def _current_xray_key(versions: list[dict]) -> str | None:
    try:
        current = XRAY_BIN.resolve()
    except Exception:
        current = XRAY_BIN
    for entry in versions:
        try:
            if Path(entry["path"]).resolve() == current:
                return entry["key"]
        except Exception:
            continue
    return None


def _asset_candidates_for_host() -> list[str]:
    import platform
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return [
            "Xray-linux-64.zip",
            "Xray-linux-amd64.zip",
            "Xray-linux-64.zip",
        ]
    if machine in {"aarch64", "arm64"}:
        return [
            "Xray-linux-arm64-v8a.zip",
            "Xray-linux-arm64.zip",
        ]
    if machine.startswith("armv7") or machine.startswith("armv6"):
        return [
            "Xray-linux-arm32-v7a.zip",
            "Xray-linux-armv7.zip",
        ]
    return ["Xray-linux-64.zip"]


def _tag_candidates(tag: str) -> list[str]:
    candidates = [tag]
    if tag.startswith("v"):
        candidates.append(tag[1:])
    else:
        candidates.append(f"v{tag}")
    return candidates


def _download_and_install(version_key: str) -> tuple[bool, str]:
    import json
    asset_names = _asset_candidates_for_host()
    tag_candidates = _tag_candidates(version_key)

    XRAY_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = XRAY_VERSIONS_DIR / version_key
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = XRAY_VERSIONS_DIR / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / f"{version_key}.zip"

    last_error = None
    for tag in tag_candidates:
        for asset_name in asset_names:
            url = f"{XRAY_RELEASE_BASE}/{tag}/{asset_name}"
            try:
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    names = set(zf.namelist())
                    if "xray" not in names:
                        return False, "Downloaded archive does not contain xray binary."
                    zf.extract("xray", path=target_dir)
                    if "geosite.dat" in names:
                        zf.extract("geosite.dat", path=target_dir)
                    if "geoip.dat" in names:
                        zf.extract("geoip.dat", path=target_dir)
                binary = target_dir / "xray"
                binary.chmod(0o755)
                for asset in ("geosite.dat", "geoip.dat"):
                    path = target_dir / asset
                    if path.exists():
                        path.chmod(0o644)
                return True, f"Installed {version_key}."
            except Exception as exc:
                last_error = exc
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass
                continue
    return False, f"Failed to download/install {version_key}: {last_error}"


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
    _xray_process = subprocess.Popen([str(XRAY_BIN), "-c", str(CONFIG_PATH)])
    PID_PATH.write_text(str(_xray_process.pid), encoding="utf-8")


def switch_xray_version(version_key: str) -> tuple[bool, str]:
    versions = {v["key"]: Path(v["path"]) for v in list_xray_versions()}
    if version_key not in versions:
        return False, "Selected version is not available."

    target = versions[version_key]
    if not target or not target.exists():
        return False, "Selected version is not installed on disk."

    if not os.access(target, os.X_OK):
        try:
            target.chmod(0o755)
        except Exception:
            return False, "Selected version is not executable."

    stop_xray()
    try:
        if XRAY_BIN.exists() or XRAY_BIN.is_symlink():
            XRAY_BIN.unlink()
    except Exception:
        pass

    try:
        XRAY_BIN.symlink_to(target)
    except Exception:
        try:
            shutil.copy2(target, XRAY_BIN)
            XRAY_BIN.chmod(0o755)
        except Exception as exc:
            return False, f"Failed to switch core: {exc}"

    XRAY_VERSION_FILE.write_text(version_key, encoding="utf-8")
    start_xray()
    return True, f"Switched Xray core to {version_key}."


def maybe_install_and_switch(version_key: str) -> tuple[bool, str]:
    versions = {v["key"]: v for v in list_xray_versions()}
    entry = versions.get(version_key)
    if not entry:
        return False, "Selected version is not available."

    if not entry.get("installed"):
        ok, msg = _download_and_install(version_key)
        if not ok:
            return False, msg

    return switch_xray_version(version_key)
