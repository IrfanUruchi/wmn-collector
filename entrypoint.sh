#!/usr/bin/env sh
set -eu

CONFIG_DIR="${CONFIG_DIR:-/config}"
CONFIG_FILE="${CONFIG_FILE:-/config/config.env}"

mkdir -p "$CONFIG_DIR"

has_tty() {
  [ -t 0 ] && [ -t 1 ]
}

write_config() {
  echo "Writing config to: $CONFIG_FILE"

  : "${MQTT_BROKER:?MQTT_BROKER required}"
  : "${MQTT_PORT:=8883}"
  : "${MQTT_TLS:=1}"
  : "${MQTT_USERNAME:=}"
  : "${MQTT_PASSWORD:=}"
  : "${DEVICE_ID:=$(hostname)}"
  : "${MQTT_TOPIC:=wmn/metrics}"
  : "${PING_TARGET:=1.1.1.1}"
  : "${INTERVAL_SEC:=5}"
  : "${WIFI_IFACE:=wlan0}"

  cat > "$CONFIG_FILE" <<EOF
MQTT_BROKER=$MQTT_BROKER
MQTT_PORT=$MQTT_PORT
MQTT_TLS=$MQTT_TLS
MQTT_USERNAME=$MQTT_USERNAME
MQTT_PASSWORD=$MQTT_PASSWORD
DEVICE_ID=$DEVICE_ID
MQTT_TOPIC=$MQTT_TOPIC
PING_TARGET=$PING_TARGET
INTERVAL_SEC=$INTERVAL_SEC
WIFI_IFACE=$WIFI_IFACE
EOF

  echo "✅ Saved."
}

interactive_setup() {
  echo "=== WMN Collector first-run setup ==="
  printf "MQTT broker host (required): "
  read -r MQTT_BROKER

  printf "MQTT port [8883]: "
  read -r MQTT_PORT; MQTT_PORT="${MQTT_PORT:-8883}"

  printf "Use TLS? [1] (1=true, 0=false): "
  read -r MQTT_TLS; MQTT_TLS="${MQTT_TLS:-1}"

  printf "MQTT username (empty if none): "
  read -r MQTT_USERNAME

  printf "MQTT password (empty if none): "
  # shellcheck disable=SC2162
  stty -echo; read MQTT_PASSWORD; stty echo; echo ""

  printf "Device ID [$(hostname)]: "
  read -r DEVICE_ID; DEVICE_ID="${DEVICE_ID:-$(hostname)}"

  printf "MQTT topic base [wmn/metrics]: "
  read -r MQTT_TOPIC; MQTT_TOPIC="${MQTT_TOPIC:-wmn/metrics}"

  printf "Ping target [1.1.1.1]: "
  read -r PING_TARGET; PING_TARGET="${PING_TARGET:-1.1.1.1}"

  printf "Interval seconds [5]: "
  read -r INTERVAL_SEC; INTERVAL_SEC="${INTERVAL_SEC:-5}"

  printf "Wi-Fi interface [wlan0]: "
  read -r WIFI_IFACE; WIFI_IFACE="${WIFI_IFACE:-wlan0}"

  export MQTT_BROKER MQTT_PORT MQTT_TLS MQTT_USERNAME MQTT_PASSWORD DEVICE_ID MQTT_TOPIC PING_TARGET INTERVAL_SEC WIFI_IFACE
  write_config
}

# If config exists, load it.
if [ -f "$CONFIG_FILE" ]; then
  echo "Loading config: $CONFIG_FILE"
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
else
  # No config yet.
  if has_tty; then
    interactive_setup
  else
    echo "[ERROR] No config found at $CONFIG_FILE and no TTY available."
    echo "Run once interactively to create config:"
    echo "  docker run -it --rm -v wmn_config:/config <image>"
    echo "Or provide env vars (MQTT_BROKER, MQTT_USERNAME, MQTT_PASSWORD, ...)."
    exit 1
  fi
fi

# Export loaded config for the Python app
export MQTT_BROKER MQTT_PORT MQTT_TLS MQTT_USERNAME MQTT_PASSWORD DEVICE_ID MQTT_TOPIC PING_TARGET INTERVAL_SEC WIFI_IFACE

# Run the collector
exec python /app/collector.py
