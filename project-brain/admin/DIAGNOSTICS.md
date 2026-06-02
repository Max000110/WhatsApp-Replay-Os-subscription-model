# Master Admin Diagnostics & Health Specification

This document details the telemetry tracking, system diagnostics metrics, and service checks executed by the Super Admin control panel.

---

## 1. System Health Telemetry

Diagnostics centers scrape hardware and network vitals directly from the application host and local docker topology:

* **Host Vitals**: CPU utilization percent, virtual RAM saturation index, and root disk usage percent.
* **PostgreSQL Check**: Validates db readiness using an active ping test:
  `pg_isready -U saas_admin -d saas_whatsapp`
* **Redis Saturation**: Tracks cache accessibility and measures Redis network ping latency (in milliseconds). Counts Celery queue accumulation using `llen("celery")`.
* **WhatsApp Node-engine**: Pulls active socket counts and scans overall daemon status via `/health`.
* **Ollama AI Server**: Pings the local instruction server (`/`) to check if the model inference pipeline is ready.
* **WebSocket Streams**: Measures active WebSockets connections and connected tenant clients in the application instance.

---

## 2. Inbound Queue & Delivery Telemetry

Telemetry gauges query Redis queue sizes and capture transmission violations:

* **Active Outbound Queues**: Scans and displays list sizes for all keys matching `whatsapp_queue_*`.
* **Transmission Failures**: Aggregates total database logs containing message status `failed` or campaigns status `failed`.
* **Webhooks Telemetry**: Highlights Razorpay failed payment order logs, detailing signature mismatches, invalid webhook payloads, or capture interruptions.
* **Security Violations**: Scans Redis for active sliding-window IP bans (`ip_ban:*`) and rate-limit violations (`rate_limit_violation:*`).
