FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iw iproute2 iputils-ping net-tools ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collector.py /app/collector.py
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV CONFIG_DIR=/config
ENV CONFIG_FILE=/config/config.env

ENTRYPOINT ["/entrypoint.sh"]
