FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV XRAY_DATA_DIR=/data
ENV UI_PORT=8088

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    openssl \
    python3 \
    python3-pip \
    unzip \
    wget \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Download and install Xray directly (no systemd required)
RUN XRAY_VERSION=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | grep -oP '"tag_name": "\K[^"]*') && \
    wget -q https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-64.zip && \
    unzip -q Xray-linux-64.zip -d /usr/local/bin && \
    rm Xray-linux-64.zip && \
    chmod +x /usr/local/bin/xray

RUN python3 -m pip install --no-cache-dir flask==3.0.3 qrcode==7.4.2 pillow==10.4.0

RUN mkdir -p /opt/xray /opt/xray-web /data

COPY config.default.json /opt/xray/config.default.json
COPY web/ /opt/xray-web/

EXPOSE 8088

CMD ["python3", "/opt/xray-web/app.py"]
