import json
import os
import platform
import re
import socket
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import paho.mqtt.client as mqtt


# ---------------------------
# Config (ENV-driven, no secrets baked in)
# ---------------------------

def require(name: str, value: str) -> str:
    """Fail-fast if a required env var is missing."""
    if value is None or str(value).strip() == "":
        raise SystemExit(
            f"[config] Missing required env var: {name}\n"
            f"Tip: copy .env.example to .env and fill it in."
        )
    return value


BROKER = os.getenv("MQTT_BROKER", "").strip()
PORT = int(os.getenv("MQTT_PORT", "8883"))

# Do NOT default these to real values (keeps image safe to publish)
USERNAME = os.getenv("MQTT_USERNAME", "").strip()
PASSWORD = os.getenv("MQTT_PASSWORD", "").strip()

TOPIC_BASE = os.getenv("MQTT_TOPIC", "wmn/metrics").strip()
DEVICE_ID = os.getenv("DEVICE_ID", socket.gethostname()).strip()
IFACE = os.getenv("WIFI_IFACE", "wlan0").strip()
PING_TARGET = os.getenv("PING_TARGET", "1.1.1.1").strip()
INTERVAL = int(os.getenv("INTERVAL_SEC", "5"))

# Spool settings
SPOOL_PATH = os.getenv("SPOOL_DB", "/data/spool.db")
MAX_SPOOL_ROWS = int(os.getenv("MAX_SPOOL_ROWS", "200000"))  # safety cap
FLUSH_BATCH = int(os.getenv("FLUSH_BATCH", "200"))           # send up to N queued rows per flush

# MQTT / TLS
USE_TLS = os.getenv("MQTT_TLS", "1").lower() in ("1", "true", "yes")
QOS = int(os.getenv("MQTT_QOS", "0"))

# Ping tuning
PING_COUNT = int(os.getenv("PING_COUNT", "5"))
PING_TIMEOUT_SEC = int(os.getenv("PING_TIMEOUT_SEC", "3"))


# ---------------------------
# Helpers
# ---------------------------
def run(cmd) -> str:
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()


def get_rssi_linux(i_face: str) -> Optional[int]:
    """
    Works on Linux hosts where 'iw' can see wifi interface (e.g. Raspberry Pi).
    In Docker Desktop / WSL it may return None (expected).
    """
    try:
        out = run(["iw", "dev", i_face, "link"])
        m = re.search(r"signal:\s+(-?\d+)\s+dBm", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def ping_stats(target: str, count: int) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Returns (avg_ms, jitter_ms, loss_pct)
    jitter approximated as mdev from ping summary.
    """
    try:
        out = run(["ping", "-c", str(count), "-n", "-W", str(PING_TIMEOUT_SEC), target])

        loss = None
        m = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", out)
        if m:
            loss = float(m.group(1))

        avg = jitter = None
        m = re.search(r"=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)\s*ms", out)
        if m:
            avg = float(m.group(2))
            jitter = float(m.group(4))
        return avg, jitter, loss
    except Exception:
        return None, None, None


def build_payload() -> dict:
    rssi = get_rssi_linux(IFACE) if platform.system().lower() == "linux" else None
    avg, jitter, loss = ping_stats(PING_TARGET, count=PING_COUNT)

    return {
        "device_id": DEVICE_ID,
        "platform": platform.system().lower(),
        "timestamp": int(time.time()),
        "target": PING_TARGET,
        "metrics": {
            "latency_ms_avg": avg,
            "jitter_ms": jitter,
            "packet_loss_pct": loss,
            "rssi_dbm": rssi,
        },
    }


# ---------------------------
# SQLite Spool
# ---------------------------
def db_connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            topic TEXT NOT NULL,
            payload TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0,
            sent_ts INTEGER
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spool_sent_id ON spool(sent, id);")
    conn.commit()
    return conn


def spool_insert(conn: sqlite3.Connection, topic: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO spool(ts, topic, payload, sent) VALUES(?,?,?,0)",
        (int(time.time()), topic, json.dumps(payload, separators=(",", ":"))),
    )
    conn.commit()


def spool_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM spool")
    return int(cur.fetchone()[0])


def spool_trim_if_needed(conn: sqlite3.Connection, max_rows: int) -> None:
    """
    If spool grows too large (e.g. long offline), delete oldest SENT rows first.
    If still too large, delete oldest rows (even unsent) to avoid disk death.
    """
    total = spool_count(conn)
    if total <= max_rows:
        return

    to_delete = total - max_rows
    conn.execute("""
        DELETE FROM spool
        WHERE id IN (
            SELECT id FROM spool WHERE sent=1 ORDER BY id ASC LIMIT ?
        )
    """, (to_delete,))
    conn.commit()

    total2 = spool_count(conn)
    if total2 <= max_rows:
        return

    to_delete2 = total2 - max_rows
    conn.execute("""
        DELETE FROM spool
        WHERE id IN (
            SELECT id FROM spool ORDER BY id ASC LIMIT ?
        )
    """, (to_delete2,))
    conn.commit()


def spool_fetch_unsent(conn: sqlite3.Connection, limit: int):
    cur = conn.execute(
        "SELECT id, topic, payload FROM spool WHERE sent=0 ORDER BY id ASC LIMIT ?",
        (limit,),
    )
    return cur.fetchall()


def spool_mark_sent(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute(
        "UPDATE spool SET sent=1, sent_ts=? WHERE id=?",
        (int(time.time()), row_id),
    )
    conn.commit()


# ---------------------------
# MQTT wrapper
# ---------------------------
@dataclass
class MqttState:
    connected: bool = False


def make_mqtt_client(state: MqttState) -> mqtt.Client:
    client = mqtt.Client()

    # Auth only if provided (works for brokers with/without auth)
    if USERNAME and PASSWORD:
        client.username_pw_set(USERNAME, PASSWORD)

    if USE_TLS:
        # Uses system CA certs inside container (we install ca-certificates)
        client.tls_set()

    def on_connect(_client, _userdata, _flags, rc):
        state.connected = (rc == 0)
        print(f"[mqtt] on_connect rc={rc} connected={state.connected}")

    def on_disconnect(_client, _userdata, rc):
        state.connected = False
        print(f"[mqtt] on_disconnect rc={rc}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    return client


def main():
    # ---- Validate config ----
    require("MQTT_BROKER", BROKER)

    # Common for cloud brokers: both must be set together.
    if (USERNAME and not PASSWORD) or (PASSWORD and not USERNAME):
        raise SystemExit("[config] Provide BOTH MQTT_USERNAME and MQTT_PASSWORD (or neither).")

    state = MqttState()
    conn = db_connect(SPOOL_PATH)

    client = make_mqtt_client(state)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    # Start MQTT loop in background thread
    try:
        client.connect(BROKER, PORT, keepalive=60)
    except Exception as e:
        print(f"[mqtt] initial connect failed: {e}")

    client.loop_start()

    topic = f"{TOPIC_BASE}/{DEVICE_ID}"

    while True:
        # 1) Collect -> spool
        payload = build_payload()
        spool_insert(conn, topic, payload)
        spool_trim_if_needed(conn, MAX_SPOOL_ROWS)

        # 2) Try flush backlog if connected
        if state.connected:
            rows = spool_fetch_unsent(conn, FLUSH_BATCH)
            sent_now = 0
            for row_id, row_topic, row_payload in rows:
                try:
                    info = client.publish(row_topic, row_payload, qos=QOS)
                    info.wait_for_publish(timeout=2)
                    if info.rc == mqtt.MQTT_ERR_SUCCESS:
                        spool_mark_sent(conn, row_id)
                        sent_now += 1
                    else:
                        break
                except Exception:
                    break

            if sent_now > 0:
                print(f"[flush] sent {sent_now} queued messages")

        print(f"[tick] queued_total={spool_count(conn)} connected={state.connected} last={payload}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
