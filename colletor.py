import json, os, platform, re, subprocess, time, socket
from datetime import datetime
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "YOUR_BROKER_HOST")
PORT = int(os.getenv("MQTT_PORT", "8883"))
USERNAME = os.getenv("MQTT_USERNAME", "YOUR_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD", "YOUR_PASSWORD")

TOPIC = os.getenv("MQTT_TOPIC", "wmn/metrics")
DEVICE_ID = os.getenv("DEVICE_ID", socket.gethostname())
IFACE = os.getenv("WIFI_IFACE", "wlan0")
PING_TARGET = os.getenv("PING_TARGET", "1.1.1.1")
INTERVAL = int(os.getenv("INTERVAL_SEC", "5"))

def run(cmd):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()

def get_rssi_linux(i_face):
    try:
        out = run(["iw", "dev", i_face, "link"])
        # Example: "signal: -61 dBm"
        m = re.search(r"signal:\s+(-?\d+)\s+dBm", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None

def ping_stats(target, count=5):
   
    try:
        out = run(["ping", "-c", str(count), "-n", target])
  
        loss = None
        m = re.search(r"(\d+(?:\.\d+)?)%\s+packet loss", out)
        if m: loss = float(m.group(1))


        avg = jitter = None
        m = re.search(r"=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)\s*ms", out)
        if m:
            avg = float(m.group(2))
            jitter = float(m.group(4))
        return avg, jitter, loss
    except Exception:
        return None, None, None

def build_payload():
    rssi = get_rssi_linux(IFACE)
    avg, jitter, loss = ping_stats(PING_TARGET, count=5)
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
        }
    }

def main():
    client = mqtt.Client()
    client.username_pw_set(USERNAME, PASSWORD)

    client.tls_set()
    client.connect(BROKER, PORT, keepalive=60)

    while True:
        payload = build_payload()
        client.publish(TOPIC + f"/{DEVICE_ID}", json.dumps(payload), qos=0)
        print(datetime.now().isoformat(), "sent", payload)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
