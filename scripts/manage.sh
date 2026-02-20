#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/xray-configs/config.json"
CLIENT_CONFIGS="$ROOT_DIR/client-configs.txt"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

generate_uuid() {
    if command -v uuidgen &> /dev/null; then
        uuidgen
    else
        openssl rand -hex 16 | sed 's/\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)/\1\2\3\4\5-\6\7\8\9-\10\11\12\13-\14\15\16\17-\18\19\20\21\22\23/'
    fi
}

pause() {
    read -p "Press Enter to continue..." _
}

ensure_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}❌ Config not found: $CONFIG_FILE${NC}"
        exit 1
    fi
}

install_server() {
    cd "$ROOT_DIR"
    bash install.sh
}

update_server() {
    cd "$ROOT_DIR"
    echo -e "${BLUE}Updating container...${NC}"
    docker compose down
    docker compose build --no-cache
    docker compose up -d
    echo -e "${GREEN}✓ Updated and restarted${NC}"
}

uninstall_server() {
    cd "$ROOT_DIR"
    echo -e "${YELLOW}This will stop and remove the container.${NC}"
    read -p "Remove Docker image too? (yes/no) [default: no]: " REMOVE_IMG
    REMOVE_IMG=${REMOVE_IMG:-no}
    read -p "Remove certs/logs? (yes/no) [default: no]: " REMOVE_DATA
    REMOVE_DATA=${REMOVE_DATA:-no}

    docker compose down
    if [ "$REMOVE_IMG" = "yes" ]; then
        docker rmi xray-server-xray-server || true
    fi
    if [ "$REMOVE_DATA" = "yes" ]; then
        rm -rf "$ROOT_DIR/certs" "$ROOT_DIR/logs"
    fi
    echo -e "${GREEN}✓ Uninstalled${NC}"
}

reinstall_server() {
    uninstall_server
    install_server
}

show_configs() {
    ensure_config
    echo -e "${BLUE}Current inbounds:${NC}"
    python3 - << 'PY'
import json
import os

path = os.environ.get('CONFIG_FILE')
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for ib in data.get('inbounds', []):
    if ib.get('protocol') != 'vless':
        continue
    port = ib.get('port')
    stream = ib.get('streamSettings', {})
    ws = stream.get('wsSettings', {})
    path = ws.get('path', '')
    security = stream.get('security', 'none')
    clients = ib.get('settings', {}).get('clients', [])
    uuid = clients[0].get('id') if clients else ''
    host = ws.get('headers', {}).get('Host', '')
    if security == 'tls':
        link = f"vless://{uuid}@{host}:{port}?path={path}&security=tls&type=ws&sni={host}&host={host}#Port{port}-TLS-WS"
    else:
        link = f"vless://{uuid}@{host}:{port}?path={path}&type=ws#Port{port}-WS"
    print(f"- port: {port}  tls: {security == 'tls'}  path: {path}")
    print(f"  {link}\n")
PY
}

add_config() {
    ensure_config
    read -p "Port: " PORT
    read -p "TLS? (yes/no) [default: no]: " USE_TLS
    USE_TLS=${USE_TLS:-no}
    read -p "Path (press Enter to auto /ws<port>): " PATH_IN
    PATH_IN=${PATH_IN:-/ws${PORT}}
    UUID=$(generate_uuid)

    python3 - << 'PY'
import json
import os

path = os.environ.get('CONFIG_FILE')
port = int(os.environ.get('PORT'))
use_tls = os.environ.get('USE_TLS') == 'yes'
ws_path = os.environ.get('PATH_IN')
uuid = os.environ.get('UUID')

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for ib in data.get('inbounds', []):
    if ib.get('port') == port:
        raise SystemExit(f"Port {port} already exists")

host = None
for ib in data.get('inbounds', []):
    ws = ib.get('streamSettings', {}).get('wsSettings', {})
    host = ws.get('headers', {}).get('Host')
    if host:
        break

if not host:
    host = "example.com"

inbound = {
    "port": port,
    "listen": "0.0.0.0",
    "protocol": "vless",
    "tag": f"{'tls-ws' if use_tls else 'ws'}-{port}",
    "settings": {
        "clients": [
            {"id": uuid, "level": 0, "email": f"client-{port}@example.com"}
        ],
        "decryption": "none"
    },
    "streamSettings": {
        "network": "ws",
        "wsSettings": {"path": ws_path, "headers": {"Host": host}}
    },
    "sniffing": {
        "enabled": True,
        "destOverride": ["http", "tls"],
        "metadataOnly": False
    }
}

if use_tls:
    inbound["streamSettings"]["security"] = "tls"
    inbound["streamSettings"]["tlsSettings"] = {
        "certificates": [{"certificateFile": "/certs/cert.pem", "keyFile": "/certs/key.pem"}],
        "minVersion": "1.2",
        "maxVersion": "1.3",
        "cipherSuites": "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305:TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256",
        "alpn": ["http/1.1"],
        "allowInsecure": False
    }

inbounds = data.get('inbounds', [])
inbounds.append(inbound)
data['inbounds'] = inbounds

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY
    
    echo -e "${GREEN}✓ Added inbound on port $PORT${NC}"
    echo "UUID: $UUID"
    if [ "$USE_TLS" = "yes" ]; then
        echo "vless://${UUID}@$(grep -m1 -o '"Host": "[^"]*"' "$CONFIG_FILE" | cut -d '"' -f4):${PORT}?path=${PATH_IN}&security=tls&type=ws&sni=$(grep -m1 -o '"Host": "[^"]*"' "$CONFIG_FILE" | cut -d '"' -f4)&host=$(grep -m1 -o '"Host": "[^"]*"' "$CONFIG_FILE" | cut -d '"' -f4)#Port${PORT}-TLS-WS"
    else
        echo "vless://${UUID}@$(grep -m1 -o '"Host": "[^"]*"' "$CONFIG_FILE" | cut -d '"' -f4):${PORT}?path=${PATH_IN}&type=ws#Port${PORT}-WS"
    fi
}

remove_config() {
    ensure_config
    read -p "Port to remove: " PORT
    python3 - << 'PY'
import json
import os

path = os.environ.get('CONFIG_FILE')
port = int(os.environ.get('PORT'))

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

before = len(data.get('inbounds', []))
filtered = [ib for ib in data.get('inbounds', []) if ib.get('port') != port]

after = len(filtered)
if before == after:
    raise SystemExit(f"Port {port} not found")

data['inbounds'] = filtered
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY
    echo -e "${GREEN}✓ Removed inbound on port $PORT${NC}"
}

restart_server() {
    cd "$ROOT_DIR"
    docker compose restart
    echo -e "${GREEN}✓ Restarted${NC}"
}

while true; do
    clear
    echo -e "${BLUE}XRAY SERVER MENU${NC}"
    echo "1) Install"
    echo "2) Update"
    echo "3) Uninstall"
    echo "4) Reinstall"
    echo "5) Show configs"
    echo "6) Add config"
    echo "7) Remove config"
    echo "8) Restart"
    echo "9) Exit"
    echo ""
    read -p "Choose an option: " CHOICE
    case "$CHOICE" in
        1) install_server; pause ;;
        2) update_server; pause ;;
        3) uninstall_server; pause ;;
        4) reinstall_server; pause ;;
        5) CONFIG_FILE="$CONFIG_FILE" show_configs; pause ;;
        6) CONFIG_FILE="$CONFIG_FILE" add_config; pause ;;
        7) CONFIG_FILE="$CONFIG_FILE" remove_config; pause ;;
        8) restart_server; pause ;;
        9) exit 0 ;;
        *) echo -e "${RED}Invalid choice${NC}"; pause ;;
    esac
 done
