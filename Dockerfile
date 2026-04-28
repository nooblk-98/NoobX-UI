FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XRAY_DATA_DIR=/data \
    XRAY_VERSIONS_DIR=/opt/xray/versions \
    XRAY_VERSIONS_CONFIG=/opt/xray/versions.json \
    UI_PORT=8088

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    openssl \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /opt/xray/versions /opt/xray-web /data

COPY config.default.json /opt/xray/config.default.json
COPY xray-versions.json /opt/xray/versions.json
COPY scripts/ /opt/xray/scripts/

RUN python3 /opt/xray/scripts/download_xray_versions.py --only-default

RUN XRAY_VER=$(python3 -c "import json; d=json.load(open('/opt/xray/versions.json')); \
    v=d if isinstance(d, list) else d['versions']; print(v[0])") \
    && ln -sf /opt/xray/versions/${XRAY_VER}/xray /usr/local/bin/xray \
    && chmod +x /usr/local/bin/xray

COPY app/ /opt/xray-web/

WORKDIR /opt/xray-web

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8088/healthz || exit 1

CMD ["python3", "app.py"]
