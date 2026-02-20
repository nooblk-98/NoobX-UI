FROM ubuntu:22.04

# Install necessary dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    ca-certificates \
    certbot \
    openssl \
    unzip \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /etc/xray /var/log/xray /certs

# Download and install Xray directly (no systemd required)
RUN XRAY_VERSION=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | grep -oP '"tag_name": "\K[^"]*') && \
    wget -q https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-64.zip && \
    unzip -q Xray-linux-64.zip -d /usr/local/bin && \
    rm Xray-linux-64.zip && \
    chmod +x /usr/local/bin/xray

# Copy Xray configuration files
COPY xray-configs/ /etc/xray/

# Copy certificates (required when not using volume mounts)
COPY certs/ /certs/

# Create directories for logs and certificates
RUN mkdir -p /etc/xray /certs /var/log/xray

# Set proper permissions
RUN chmod 644 /etc/xray/*.json

# Start Xray
CMD ["xray", "-c", "/etc/xray/config.json"]
