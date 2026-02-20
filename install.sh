#!/bin/bash

# 🚀 XRAY SERVER - AUTOMATED INSTALLATION SCRIPT
# Single script to automate the entire setup process
# Usage: bash install.sh

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
LOG_FILE="install.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2>&1

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          🚀 XRAY SERVER - AUTOMATED INSTALLATION            ║"
echo "║           Complete Setup in One Command                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "This script will automate the entire Xray server setup."
echo "Installation started: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ============================================================================
# PHASE 1: PREREQUISITES CHECK
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 1: Prerequisites Check${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if running on Linux
if ! [ -f /etc/os-release ]; then
    echo -e "${RED}❌ This script requires Linux. Current OS is not supported.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Linux OS detected${NC}"

# Check and install Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Installing Docker...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    newgrp docker
    
    echo -e "${GREEN}✓ Docker installed: $(docker --version)${NC}"
else
    echo -e "${GREEN}✓ Docker installed: $(docker --version)${NC}"
fi

# Check and install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Installing Docker Compose...${NC}"
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo -e "${GREEN}✓ Docker Compose installed: $(docker-compose --version)${NC}"
else
    echo -e "${GREEN}✓ Docker Compose installed: $(docker-compose --version)${NC}"
fi

# Check if Docker daemon is running
if ! docker ps &> /dev/null; then
    echo -e "${YELLOW}Starting Docker daemon...${NC}"
    sudo systemctl start docker
    sudo systemctl enable docker
    sleep 2
fi

if docker ps &> /dev/null; then
    echo -e "${GREEN}✓ Docker daemon is running${NC}"
else
    echo -e "${RED}❌ Docker daemon failed to start${NC}"
    exit 1
fi

echo ""

# ============================================================================
# PHASE 2: USER INPUT
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 2: Configuration Input${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Domain input
read -p "Enter your domain (e.g., example.com): " DOMAIN
if [ -z "$DOMAIN" ] || [ "$DOMAIN" = "example.com" ]; then
    echo -e "${RED}❌ Invalid domain${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Domain: $DOMAIN${NC}"
echo ""

# Email input
read -p "Enter email for SSL certificate (e.g., admin@example.com): " EMAIL
if [ -z "$EMAIL" ] || ! [[ "$EMAIL" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    echo -e "${RED}❌ Invalid email format${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Email: $EMAIL${NC}"
echo ""

# Port Configuration
echo -e "${YELLOW}━━━ Port Configuration ━━━${NC}"
echo "Enter one or two ports (comma-separated). Paths are auto-generated."
echo ""

read -p "WS (no TLS) ports [default: 80,8080]: " WS_PORTS_INPUT
WS_PORTS_INPUT=${WS_PORTS_INPUT:-80,8080}
read -p "WS + TLS ports [default: 443,8443]: " TLS_PORTS_INPUT
TLS_PORTS_INPUT=${TLS_PORTS_INPUT:-443,8443}

WS_PORTS_INPUT=$(echo "$WS_PORTS_INPUT" | tr -d ' ')
TLS_PORTS_INPUT=$(echo "$TLS_PORTS_INPUT" | tr -d ' ')

IFS=',' read -r WS_PORT_1 WS_PORT_2 <<< "$WS_PORTS_INPUT"
IFS=',' read -r TLS_PORT_1 TLS_PORT_2 <<< "$TLS_PORTS_INPUT"

PORT_80=${WS_PORT_1:-80}
PORT_8080=${WS_PORT_2:-}
PORT_443=${TLS_PORT_1:-443}
PORT_8443=${TLS_PORT_2:-}

ENABLE_80=yes
ENABLE_8080=no
ENABLE_443=yes
ENABLE_8443=no

[ -n "$PORT_8080" ] && ENABLE_8080=yes
[ -n "$PORT_8443" ] && ENABLE_8443=yes

PATH_80=/ws
[ "$ENABLE_8080" = "yes" ] && PATH_8080=/ws${PORT_8080}
PATH_443=/ws${PORT_443}
[ "$ENABLE_8443" = "yes" ] && PATH_8443=/ws${PORT_8443}

validate_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

for p in "$PORT_80" "$PORT_443"; do
    if ! validate_port "$p"; then
        echo -e "${RED}❌ Invalid port: $p (must be 1-65535)${NC}"
        exit 1
    fi
done
if [ "$ENABLE_8080" = "yes" ] && ! validate_port "$PORT_8080"; then
    echo -e "${RED}❌ Invalid port: $PORT_8080 (must be 1-65535)${NC}"
    exit 1
fi
if [ "$ENABLE_8443" = "yes" ] && ! validate_port "$PORT_8443"; then
    echo -e "${RED}❌ Invalid port: $PORT_8443 (must be 1-65535)${NC}"
    exit 1
fi

declare -A PORT_SEEN
for p in "$PORT_80" "$PORT_443"; do
    if [ -n "${PORT_SEEN[$p]}" ]; then
        echo -e "${RED}❌ Duplicate port detected: $p. Use unique ports for WS and WS+TLS.${NC}"
        exit 1
    fi
    PORT_SEEN[$p]=1
done
if [ "$ENABLE_8080" = "yes" ]; then
    if [ -n "${PORT_SEEN[$PORT_8080]}" ]; then
        echo -e "${RED}❌ Duplicate port detected: $PORT_8080. Use unique ports for WS and WS+TLS.${NC}"
        exit 1
    fi
    PORT_SEEN[$PORT_8080]=1
fi
if [ "$ENABLE_8443" = "yes" ]; then
    if [ -n "${PORT_SEEN[$PORT_8443]}" ]; then
        echo -e "${RED}❌ Duplicate port detected: $PORT_8443. Use unique ports for WS and WS+TLS.${NC}"
        exit 1
    fi
    PORT_SEEN[$PORT_8443]=1
fi

if [ "$ENABLE_8080" = "yes" ]; then
    echo -e "  ${GREEN}✓ WS ports: ${PORT_80} (${PATH_80}), ${PORT_8080} (${PATH_8080})${NC}"
else
    echo -e "  ${GREEN}✓ WS ports: ${PORT_80} (${PATH_80})${NC}"
fi
if [ "$ENABLE_8443" = "yes" ]; then
    echo -e "  ${GREEN}✓ WS+TLS ports: ${PORT_443} (${PATH_443}), ${PORT_8443} (${PATH_8443})${NC}"
else
    echo -e "  ${GREEN}✓ WS+TLS ports: ${PORT_443} (${PATH_443})${NC}"
fi
echo ""

# Certificate type selection
echo "Choose certificate type:"
echo "1) Let's Encrypt (production) - requires domain to be accessible"
echo "2) Self-signed (testing/development)"
read -p "Select (1 or 2): " CERT_TYPE
if [ "$CERT_TYPE" != "1" ] && [ "$CERT_TYPE" != "2" ]; then
    echo -e "${RED}❌ Invalid selection${NC}"
    exit 1
fi
echo ""

# Confirmation
echo -e "${YELLOW}Summary:${NC}"
echo "  Domain: $DOMAIN"
echo "  Email: $EMAIL"
echo "  Certificate: $([ "$CERT_TYPE" = "1" ] && echo "Let's Encrypt" || echo "Self-signed")"
echo "  WS ports: $PORT_80 ($PATH_80), $PORT_8080 ($PATH_8080)"
echo "  WS+TLS ports: $PORT_443 ($PATH_443), $PORT_8443 ($PATH_8443)"
echo ""
read -p "Continue with these settings? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo -e "${RED}Installation cancelled${NC}"
    exit 0
fi
echo ""

# ============================================================================
# PHASE 3: GENERATE UUIDS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 3: Generate UUIDs${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Function to generate UUID
generate_uuid() {
    if command -v uuidgen &> /dev/null; then
        uuidgen
    else
        openssl rand -hex 16 | sed 's/\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)/\1\2\3\4\5-\6\7\8\9-\10\11\12\13-\14\15\16\17-\18\19\20\21\22\23/'
    fi
}

UUID_80=$(generate_uuid)
UUID_8080=$(generate_uuid)
UUID_8443=$(generate_uuid)
UUID_443=$(generate_uuid)

echo "Generated UUIDs:"
echo -e "  Port 80:   ${GREEN}$UUID_80${NC}"
echo -e "  Port 8080: ${GREEN}$UUID_8080${NC}"
echo -e "  Port 8443: ${GREEN}$UUID_8443${NC}"
echo -e "  Port 443:  ${GREEN}$UUID_443${NC}"
echo ""

# ============================================================================
# PHASE 4: CREATE DIRECTORIES
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 4: Create Directories${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

mkdir -p certs logs backups
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# ============================================================================
# PHASE 5: CREATE .env FILE
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 5: Create Configuration Files${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

cat > .env << EOF
# Xray Server Configuration
DOMAIN=$DOMAIN
LETSENCRYPT_EMAIL=$EMAIL
PORT_80=$PORT_80
PORT_443=$PORT_443
PORT_8080=$PORT_8080
PORT_8443=$PORT_8443
UUID_PORT_80=$UUID_80
UUID_PORT_8080=$UUID_8080
UUID_PORT_8443=$UUID_8443
UUID_PORT_443=$UUID_443
WS_PATH_80=$PATH_80
WS_PATH_443=$PATH_443
WS_PATH_8080=$PATH_8080
WS_PATH_8443=$PATH_8443
LOG_LEVEL=info
TZ=UTC
EOF

echo -e "${GREEN}✓ Created .env file${NC}"

# ============================================================================
# PHASE 6: UPDATE XRAY CONFIGURATION
# ============================================================================
echo "Updating Xray configuration files..."

# Update main config.json
sed -i "s|\"Host\": \"example.com\"|\"Host\": \"$DOMAIN\"|g" xray-configs/config.json
sed -i "s|12345678-1234-1234-1234-123456789012|$UUID_80|g" xray-configs/config.json
sed -i "s|87654321-4321-4321-4321-210987654321|$UUID_8080|g" xray-configs/config.json
sed -i "s|11111111-2222-3333-4444-555555555555|$UUID_8443|g" xray-configs/config.json
sed -i "s|99999999-8888-7777-6666-555555555555|$UUID_443|g" xray-configs/config.json
sed -i "s|\"port\": 80|\"port\": $PORT_80|g" xray-configs/config.json
sed -i "s|\"port\": 443|\"port\": $PORT_443|g" xray-configs/config.json
sed -i "s|\"path\": \"/ws\"|\"path\": \"$PATH_80\"|g" xray-configs/config.json
sed -i "s|\"path\": \"/ws443\"|\"path\": \"$PATH_443\"|g" xray-configs/config.json

if [ "$ENABLE_8080" = "yes" ]; then
    sed -i "s|\"port\": 8080|\"port\": $PORT_8080|g" xray-configs/config.json
    sed -i "s|\"path\": \"/ws8080\"|\"path\": \"$PATH_8080\"|g" xray-configs/config.json
fi

if [ "$ENABLE_8443" = "yes" ]; then
    sed -i "s|\"port\": 8443|\"port\": $PORT_8443|g" xray-configs/config.json
    sed -i "s|\"path\": \"/ws8443\"|\"path\": \"$PATH_8443\"|g" xray-configs/config.json
fi

python3 - << 'PY'
import json

path = 'xray-configs/config.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

inbounds = data.get('inbounds', [])
filtered = []
for ib in inbounds:
    tag = ib.get('tag', '')
    if tag == 'alt-ws' and "${ENABLE_8080}" != 'yes':
        continue
    if tag == 'tls-ws-alt' and "${ENABLE_8443}" != 'yes':
        continue
    filtered.append(ib)

data['inbounds'] = filtered

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY

echo -e "${GREEN}✓ Configuration files updated${NC}"
echo ""

# ============================================================================
# PHASE 7: SETUP SSL CERTIFICATES
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 6: Setup SSL Certificates${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$CERT_TYPE" = "1" ]; then
    # Let's Encrypt Certificate
    echo "Obtaining Let's Encrypt certificate..."
    echo "⚠️  Make sure your domain is accessible and port 80 is open"
    echo ""
    
    # Install certbot if needed
    if ! command -v certbot &> /dev/null; then
        echo "Installing certbot..."
        sudo apt-get update -qq
        sudo apt-get install -y certbot > /dev/null 2>&1
    fi
    
    # Obtain certificate
    if sudo certbot certonly \
        --standalone \
        --agree-tos \
        --no-eff-email \
        -m "$EMAIL" \
        -d "$DOMAIN" \
        --non-interactive 2>/dev/null; then
        
        # Copy certificates
        sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem certs/cert.pem
        sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem certs/key.pem
        sudo chown $(whoami):$(whoami) certs/cert.pem certs/key.pem
        chmod 644 certs/cert.pem
        chmod 600 certs/key.pem
        
        echo -e "${GREEN}✓ Let's Encrypt certificate obtained${NC}"
    else
        echo -e "${RED}❌ Failed to obtain Let's Encrypt certificate${NC}"
        echo "Make sure:"
        echo "  1. Domain DNS is pointing to this server"
        echo "  2. Port 80 is open in firewall"
        echo "  3. No other service is using port 80"
        exit 1
    fi
else
    # Self-signed Certificate
    echo "Generating self-signed certificate..."
    
    openssl genrsa -out certs/key.pem 2048 > /dev/null 2>&1
    openssl req -new -x509 \
        -key certs/key.pem \
        -out certs/cert.pem \
        -days 365 \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=$DOMAIN" > /dev/null 2>&1
    
    chmod 644 certs/cert.pem
    chmod 600 certs/key.pem
    
    echo -e "${GREEN}✓ Self-signed certificate generated${NC}"
    echo -e "${YELLOW}⚠️  Remember: Self-signed certs are for testing only${NC}"
fi

echo ""

# ============================================================================
# PHASE 8: BUILD AND START DOCKER
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 7: Build and Start Docker Container${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "Building Docker image..."
docker-compose build --quiet 2>&1 | grep -v "^$" || true
echo -e "${GREEN}✓ Docker image built${NC}"
echo ""

echo "Starting Xray server..."
docker-compose up -d
echo -e "${GREEN}✓ Xray server started${NC}"
echo ""

# Wait for container to be ready
sleep 3

# Check if container is running
if docker-compose ps | grep -q "xray-server.*Up"; then
    echo -e "${GREEN}✓ Container is running${NC}"
else
    echo -e "${RED}❌ Container failed to start${NC}"
    echo "Check logs: docker-compose logs"
    exit 1
fi

echo ""

# ============================================================================
# PHASE 9: GENERATE CONNECTION STRINGS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 8: Generate Client Connection Strings${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "Your VLESS Connection Strings:"
echo ""
echo -e "${YELLOW}Port 80 (HTTP WebSocket - NO ENCRYPTION):${NC}"
echo "vless://${UUID_80}@${DOMAIN}:80?path=/ws&type=ws#Port80-WS"
echo ""

echo -e "${YELLOW}Port 8080 (Alternative WebSocket):${NC}"
echo "vless://${UUID_8080}@${DOMAIN}:8080?path=/ws8080&type=ws#Port8080-WS"
echo ""

echo -e "${YELLOW}Port 8443 (WebSocket + TLS):${NC}"
echo "vless://${UUID_8443}@${DOMAIN}:8443?path=/ws8443&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port8443-TLS-WS"
echo ""

echo -e "${GREEN}Port 443 (WebSocket + TLS - RECOMMENDED):${NC}"
echo "vless://${UUID_443}@${DOMAIN}:443?path=/ws443&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port443-TLS-WS"
echo ""

echo ""

# ============================================================================
# PHASE 10: SAVE CONFIGURATION
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 9: Save Configuration${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Save connection strings to file
cat > connection-strings.txt << EOF
XRAY SERVER - CLIENT CONNECTION STRINGS
Generated: $(date)
Domain: $DOMAIN

PORT 80 (HTTP WebSocket - NO ENCRYPTION):
vless://${UUID_80}@${DOMAIN}:80?path=/ws&type=ws#Port80-WS

PORT 8080 (Alternative WebSocket):
vless://${UUID_8080}@${DOMAIN}:8080?path=/ws8080&type=ws#Port8080-WS

PORT 8443 (WebSocket + TLS):
vless://${UUID_8443}@${DOMAIN}:8443?path=/ws8443&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port8443-TLS-WS

PORT 443 (WebSocket + TLS - RECOMMENDED):
vless://${UUID_443}@${DOMAIN}:443?path=/ws443&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port443-TLS-WS

RECOMMENDED:
- Use Port 443 for production (encrypted HTTPS)
- Use Port 8080 as backup (unencrypted)
- Keep connection strings private
- Share only with trusted clients

FIREWALL RULES:
Allow ports: 80, 443, 8080, 8443

MONITORING:
- View logs: docker-compose logs -f
- Check status: docker-compose ps
- Monitor resources: docker stats xray-server

MANAGEMENT:
- Stop server: docker-compose down
- Restart server: docker-compose restart
- Rebuild: docker-compose build --no-cache

For more information, see README.md
EOF

echo -e "${GREEN}✓ Connection strings saved to: connection-strings.txt${NC}"
echo ""

# ============================================================================
# COMPLETION
# ============================================================================
echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            ✅ INSTALLATION COMPLETED SUCCESSFULLY!          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

echo -e "${YELLOW}📋 Installation Summary:${NC}"
echo "  Domain: $DOMAIN"
echo "  Email: $EMAIL"
echo "  Certificate: $([ "$CERT_TYPE" = "1" ] && echo "Let's Encrypt" || echo "Self-signed")"
echo "  Ports: 80, 8080, 8443, 443"
echo "  Container: xray-server (Running ✓)"
echo ""

echo -e "${YELLOW}📝 Configuration Files:${NC}"
echo "  .env - Environment configuration"
echo "  xray-configs/config.json - Xray configuration"
echo "  certs/cert.pem - SSL certificate"
echo "  certs/key.pem - SSL private key"
echo ""

echo -e "${YELLOW}🔗 Connection Strings:${NC}"
echo "  Saved in: connection-strings.txt"
echo "  Use Port 443 (TLS) for secure connections"
echo ""

echo -e "${YELLOW}📊 Next Steps:${NC}"
echo "  1. View logs: docker-compose logs -f"
echo "  2. Check status: docker-compose ps"
echo "  3. Import connection strings into your Xray client"
echo "  4. Test connectivity"
echo "  5. Set up firewall rules for ports 80, 443, 8080, 8443"
echo ""

echo -e "${YELLOW}🔐 Firewall Setup (example with ufw):${NC}"
echo "  sudo ufw allow 22/tcp"
echo "  sudo ufw allow 80/tcp"
echo "  sudo ufw allow 443/tcp"
echo "  sudo ufw allow 8080/tcp"
echo "  sudo ufw allow 8443/tcp"
echo "  sudo ufw enable"
echo ""

echo -e "${YELLOW}📋 Installation Log:${NC}"
echo "  Saved in: $LOG_FILE"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Installation time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ============================================================================
# PHASE 10: GENERATE QR CODES AND IMPORT CONFIGS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Client Import Methods${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "1️⃣ VLESS Connection Strings (ready to import):"
echo ""

if [ "$ENABLE_80" = "yes" ]; then
    echo -e "${YELLOW}━━━ Port ${PORT_80} (HTTP WebSocket) ━━━${NC}"
    echo "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
    echo ""
fi

if [ "$ENABLE_8080" = "yes" ]; then
    echo -e "${YELLOW}━━━ Port ${PORT_8080} (Alternative WebSocket) ━━━${NC}"
    echo "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
    echo ""
fi

if [ "$ENABLE_8443" = "yes" ]; then
    echo -e "${YELLOW}━━━ Port ${PORT_8443} (WebSocket + TLS) ━━━${NC}"
    echo "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
    echo ""
fi

if [ "$ENABLE_443" = "yes" ]; then
    echo -e "${GREEN}━━━ Port ${PORT_443} (WebSocket + TLS - RECOMMENDED) ━━━${NC}"
    echo "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
    echo ""
fi

# Try to generate QR codes if qrencode is available
if command -v qrencode &> /dev/null; then
    echo "2️⃣ Generating QR Codes..."
    echo ""
    
    mkdir -p qrcodes
    
    echo "Creating QR codes for all enabled ports..."
    [ "$ENABLE_80" = "yes" ] && qrencode -t PNG -s 10 -o qrcodes/port${PORT_80}.png "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
    [ "$ENABLE_8080" = "yes" ] && qrencode -t PNG -s 10 -o qrcodes/port${PORT_8080}.png "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
    [ "$ENABLE_8443" = "yes" ] && qrencode -t PNG -s 10 -o qrcodes/port${PORT_8443}.png "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
    [ "$ENABLE_443" = "yes" ] && qrencode -t PNG -s 10 -o qrcodes/port${PORT_443}.png "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
    
    # Generate ASCII QR codes for terminal display
    echo ""
    [ "$ENABLE_80" = "yes" ] && {
        echo -e "${BLUE}━━━ Port ${PORT_80} (HTTP WebSocket) ━━━${NC}"
        echo "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
        echo ""
        qrencode -t ANSIUTF8 "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
        echo ""
    }
    
    [ "$ENABLE_8080" = "yes" ] && {
        echo -e "${BLUE}━━━ Port ${PORT_8080} (Alternative WebSocket) ━━━${NC}"
        echo "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
        echo ""
        qrencode -t ANSIUTF8 "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
        echo ""
    }
    
    [ "$ENABLE_8443" = "yes" ] && {
        echo -e "${BLUE}━━━ Port ${PORT_8443} (WebSocket + TLS) ━━━${NC}"
        echo "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
        echo ""
        qrencode -t ANSIUTF8 "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
        echo ""
    }
    
    [ "$ENABLE_443" = "yes" ] && {
        echo -e "${GREEN}━━━ Port ${PORT_443} (WebSocket + TLS - RECOMMENDED) ━━━${NC}"
        echo "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
        echo ""
        qrencode -t ANSIUTF8 "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
        echo ""
    }
    
    echo -e "${GREEN}✓ PNG QR codes saved to: qrcodes/${NC}"
    PNG_LIST="port${PORT_80}.png"
    [ "$ENABLE_8080" = "yes" ] && PNG_LIST+=" , port${PORT_8080}.png"
    [ "$ENABLE_8443" = "yes" ] && PNG_LIST+=" , port${PORT_8443}.png"
    PNG_LIST+=" , port${PORT_443}.png"
    echo "   ${PNG_LIST}"
    echo ""
else
    echo "2️⃣ QR Code Generation:"
    echo ""
    echo "Installing qrencode..."
    if sudo apt-get install -y qrencode > /dev/null 2>&1; then
        mkdir -p qrcodes
        qrencode -t PNG -s 10 -o qrcodes/port${PORT_80}.png "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
        qrencode -t PNG -s 10 -o qrcodes/port${PORT_8080}.png "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
        qrencode -t PNG -s 10 -o qrcodes/port${PORT_8443}.png "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
        qrencode -t PNG -s 10 -o qrcodes/port${PORT_443}.png "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
        
        echo ""
        if [ "$ENABLE_80" = "yes" ]; then
            echo -e "${BLUE}━━━ Port ${PORT_80} (HTTP WebSocket) ━━━${NC}"
            echo "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
            echo ""
            qrencode -t ANSIUTF8 "vless://${UUID_80}@${DOMAIN}:${PORT_80}?path=${PATH_80}&type=ws#Port${PORT_80}-WS"
            echo ""
        fi
        
        if [ "$ENABLE_8080" = "yes" ]; then
            echo -e "${BLUE}━━━ Port ${PORT_8080} (Alternative WebSocket) ━━━${NC}"
            echo "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
            echo ""
            qrencode -t ANSIUTF8 "vless://${UUID_8080}@${DOMAIN}:${PORT_8080}?path=${PATH_8080}&type=ws#Port${PORT_8080}-WS"
            echo ""
        fi
        
        if [ "$ENABLE_8443" = "yes" ]; then
            echo -e "${BLUE}━━━ Port ${PORT_8443} (WebSocket + TLS) ━━━${NC}"
            echo "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
            echo ""
            qrencode -t ANSIUTF8 "vless://${UUID_8443}@${DOMAIN}:${PORT_8443}?path=${PATH_8443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_8443}-TLS-WS"
            echo ""
        fi
        
        if [ "$ENABLE_443" = "yes" ]; then
            echo -e "${GREEN}━━━ Port ${PORT_443} (WebSocket + TLS - RECOMMENDED) ━━━${NC}"
            echo "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
            echo ""
            qrencode -t ANSIUTF8 "vless://${UUID_443}@${DOMAIN}:${PORT_443}?path=${PATH_443}&security=tls&type=ws&sni=${DOMAIN}&host=${DOMAIN}#Port${PORT_443}-TLS-WS"
            echo ""
        fi
        
        echo -e "${GREEN}✓ QR codes generated in: qrcodes/${NC}"
    else
        echo "Could not install qrencode. You can:"
        echo "- Install manually: sudo apt-get install qrencode"
        echo "- Use online QR generator with connection strings above"
    fi
    echo ""
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

cat > client-configs.txt << EOF
📲 CLIENT APPLICATIONS:

Compatible with:
✓ V2RayN / V2RayNG (Windows/Android)
✓ Clash / ClashX / ClashMeta (Multi-platform)
✓ Shadowrocket (iOS)
✓ Quantumult X (iOS)
✓ Qv2ray (Multi-platform)
✓ Any VLESS-compatible client

═══════════════════════════════════════════════════════════════

🔐 SECURITY NOTES:

- Use Port 443 for encrypted connections (HTTPS)
- Keep connection strings private
- UUIDs act as passwords - don't share publicly
- Change UUIDs periodically for security
- Monitor server logs regularly

═══════════════════════════════════════════════════════════════

📋 IMPORT INSTRUCTIONS:

V2RayN/V2RayNG:
1. Copy connection string (starting with 'vless://')
2. Open app → Subscription → Add → Paste
3. Or scan QR code if available

Clash:
1. Add config to yaml under 'proxies' section
2. Or copy connection string to clipboard
3. App will auto-detect VLESS format

Shadowrocket:
1. Copy connection string
2. Tap '+' → Paste
3. Or scan QR code

═══════════════════════════════════════════════════════════════

Generated: $(date '+%Y-%m-%d %H:%M:%S')
EOF

echo -e "${GREEN}✓ All configs saved to: client-configs.txt${NC}"
echo ""

echo -e "${GREEN}✨ Your Xray server is ready to use!${NC}"
echo ""
