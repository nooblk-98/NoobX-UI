import json
import subprocess
import time

from .constants import XRAY_BIN
from .xray_core import is_xray_running

_last_net_io = None
_last_net_time = None
_last_speeds = {"up": 0.0, "down": 0.0}
_last_stats = {}
_last_stats_time = 0.0


def get_sys_info() -> dict:
    info = {"cpu": "0.00", "mem": "0.0%"}
    import platform
    if platform.system() == "Linux":
        try:
            with open("/proc/loadavg", "r") as f:
                info["cpu"] = f.read().split()[0]
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
                total = available = 0
                for line in lines:
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        available = int(line.split()[1])
                if total > 0:
                    used = total - available
                    info["mem"] = f"{(used / total) * 100:.1f}%"
        except Exception:
            pass
    return info


def get_net_speed() -> dict:
    global _last_net_io, _last_net_time, _last_speeds
    up_speed = 0.0
    down_speed = 0.0
    import platform
    if platform.system() == "Linux":
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()
            rx_bytes = 0
            tx_bytes = 0
            for line in lines[2:]:
                if "lo:" in line:
                    continue
                parts = line.split(":")
                if len(parts) == 2:
                    ifparts = parts[1].split()
                    rx_bytes += int(ifparts[0])
                    tx_bytes += int(ifparts[8])
            now = time.time()
            if _last_net_time is not None and _last_net_io is not None:
                elapsed = now - _last_net_time
                if elapsed > 0.5:
                    down_speed = (rx_bytes - _last_net_io[0]) / elapsed
                    up_speed = (tx_bytes - _last_net_io[1]) / elapsed
                    down_speed = (down_speed * 0.6) + (_last_speeds["down"] * 0.4)
                    up_speed = (up_speed * 0.6) + (_last_speeds["up"] * 0.4)
                else:
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
        if b < 1024 * 1024:
            return f"{b/1024:.1f} KB"
        if b < 1024 * 1024 * 1024:
            return f"{b/1024/1024:.1f} MB"
        return f"{b/1024/1024/1024:.1f} GB"

    def format_speed(b):
        return f"{format_bytes(b)}/s"

    return {
        "up_str": format_speed(max(0, up_speed)),
        "down_str": format_speed(max(0, down_speed)),
        "up_raw": max(0, up_speed) / 1024,
        "down_raw": max(0, down_speed) / 1024,
    }


def format_bytes_global(b):
    if b < 1024:
        return f"{b:.1f} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b/1024/1024:.1f} MB"
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
                    if len(parts) >= 4 and parts[3] == "01":
                        local_addr = parts[1]
                        if ":" in local_addr:
                            port_hex = local_addr.split(":")[1]
                            active_ports.add(int(port_hex, 16))
            except Exception:
                pass
    return list(active_ports)


def get_xray_stats() -> dict:
    global _last_stats, _last_stats_time
    now = time.time()
    current_stats = {}

    if is_xray_running():
        try:
            res = subprocess.run(
                [str(XRAY_BIN), "api", "statsquery", "-server=127.0.0.1:10085"],
                capture_output=True,
                text=True,
                timeout=1,
            )
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
            "speed_str": f"{format_bytes_global(down_speed)}/s \u2193 {format_bytes_global(up_speed)}/s \u2191",
        }

    _last_stats = current_stats
    _last_stats_time = now
    return output
