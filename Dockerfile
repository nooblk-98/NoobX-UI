FROM python:3.12-slim

ENV XRAY_DATA_DIR=/data
ENV XRAY_VERSIONS_DIR=/opt/xray/versions
ENV XRAY_VERSIONS_CONFIG=/opt/xray/versions.json
ENV UI_PORT=8088

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    openssl \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask==3.0.3 qrcode==7.4.2 pillow==10.4.0

RUN mkdir -p /opt/xray/versions /opt/xray-web /data

COPY config.default.json /opt/xray/config.default.json
COPY xray-versions.json /opt/xray/versions.json
COPY scripts/ /opt/xray/scripts/
COPY web/ /opt/xray-web/

# Download only the default (latest) Xray version at build time
RUN python3 /opt/xray/scripts/download_xray_versions.py --only-default

# Set default Xray core (matches first entry in versions.json)
RUN ln -sf /opt/xray/versions/v26.2.6/xray /usr/local/bin/xray && chmod +x /usr/local/bin/xray

WORKDIR /opt/xray-web

EXPOSE 8088

CMD ["python3", "app.py"]
