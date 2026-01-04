# WMN Collector – Dockerized Edge Metrics Publisher

This repository contains the source code and Docker build files for **wmn-collector**, an edge-side service used in the Wireless & Mobile Networks (WMN) project.

The collector runs on an edge device (such as a Raspberry Pi or a development machine) and periodically measures network performance metrics. These metrics are published to an MQTT broker and consumed by downstream services (e.g., a fog-layer analyzer and dashboards).

The **primary distribution method is Docker Hub**. This repository exists to document and reproduce the Docker image build.

---

## What the Collector Does

At a fixed interval, the collector measures and publishes:

* Average latency (ICMP ping)
* Jitter (ping mdev approximation)
* Packet loss percentage
* Wi-Fi RSSI (Linux hosts with real Wi-Fi interfaces only)

The output is published as JSON messages over MQTT.

---

## Intended Deployment

Typical placement:

* **Edge device**: Raspberry Pi, laptop, or VM close to the network being measured
* **Fog / server**: MQTT analyzer and dashboards
* **Cloud (optional)**: MQTT broker and Grafana Cloud

The collector is designed to be lightweight and hardware-aware, keeping radio-level measurements at the edge.

---

## MQTT Output

Messages are published to:

```
<MQTT_TOPIC>/<DEVICE_ID>
```

Default example:

```
wmn/metrics/irfanwmn
```

Example payload:

```json
{
  "device_id": "irfanwmn",
  "platform": "linux",
  "timestamp": 1767523544,
  "metrics": {
    "latency_ms_avg": 84.5,
    "jitter_ms": 44.7,
    "packet_loss_pct": 0.0,
    "rssi_dbm": -62
  }
}
```

---

## Docker Image

Pre-built Docker images are published on Docker Hub.

* **WMN Collector (this repository)**
  [https://hub.docker.com/r/irfanuruchi/wmn-collector](https://hub.docker.com/r/irfanuruchi/wmn-collector)

Related images in the same project:

* **WMN Analyzer (fog-layer analytics)**
  [https://hub.docker.com/r/irfanuruchi/wmn-analyzer](https://hub.docker.com/r/irfanuruchi/wmn-analyzer)

* **WMN Explainer (LLM-based explanation service)**
  *(to be added)*

---

## Running the Collector

### Raspberry Pi (recommended for RSSI)

```bash
docker run -it --name wmn-collector \
  --restart unless-stopped \
  --net=host --privileged \
  -v wmn_config:/config \
  -v wmn_data:/data \
  irfanuruchi/wmn-collector:latest
```

### PC / WSL / macOS

```bash
docker run -it --name wmn-collector \
  --restart unless-stopped \
  -v wmn_config:/config \
  -v wmn_data:/data \
  irfanuruchi/wmn-collector:latest
```

On first start, the container prompts for MQTT connection details and stores them in a persistent Docker volume.

---

## Configuration Handling

Configuration is stored in:

```
/config/config.env
```

This file is created automatically on first run and persisted using a Docker volume. It can be reset by deleting the volume or the file.

---

## Repository Contents

This repository includes:

* `collector.py` – metrics collection and MQTT publishing logic
* `entrypoint.sh` – first-run configuration script
* `Dockerfile` – container build definition
* `requirements.txt` – Python dependencies

Secrets and runtime configuration are **not** committed to this repository.

---

## Related Repositories

This repository is part of a multi-component system. Related GitHub repositories include:

* **wmn-collector** (this repository)
  Edge-side metrics collection

* **wmn-analyzer** *(to be added)*
  Fog-layer analytics and scoring service

* **wmn-explainer** *(to be added)*
  Fog-layer explanation service

* **wmn-edge-system** *(head repository, to be added)*
  Top-level repository that documents the full system architecture and links all components together

Additional repositories may be added as the project evolves.

---

## Other GitHub Resources

The following GitHub repositories may be linked here as the project expands:

* MQTT broker configuration (local fog broker / bridging)
* Dashboard definitions (Grafana JSON exports)
* Evaluation scripts and experiments
* Documentation and reports

This section is intentionally left open to support future extensions without restructuring the repository.

---

## Notes

* RSSI is only available on Linux hosts with direct access to a Wi-Fi interface.
* On WSL and macOS, RSSI is expected to be `null`.
* The collector includes an offline spool mechanism to buffer data if MQTT is temporarily unavailable.
