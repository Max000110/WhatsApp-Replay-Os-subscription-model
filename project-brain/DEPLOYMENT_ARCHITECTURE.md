# ReplyOS — Deployment & Infrastructure Architecture

This document describes the host VM infrastructure, container topology, volume bindings, and proxy port mappings.

---

## 1. Hosting VM Profile

* **Infrastructure Provider**: Oracle Cloud Infrastructure (OCI) Virtual Machine.
* **Public Gateway IP**: `144.24.126.153`
* **Nginx Reverse Proxy Gateway Port**: `8080` (mapped to port `80` inside the container)
* **Frontend Internal Port**: `3000` (mapped to `30000` on the host for direct dev tests)

---

## 2. Docker Container Stack

The application runs as 8 interconnected services orchestrated via Docker Compose:

```
                  +--------------------------------+
                  |         saas_nginx (8080)      |
                  +--------------------------------+
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
+------------------+                              +------------------+
|  saas_frontend   |                              |   saas_backend   |
|   (Next.js:3000) |                              |   (FastAPI:8000) |
+------------------+                              +------------------+
                                                           │
                                   ┌───────────────────────┼───────────────────────┐
                                   ▼                       ▼                       ▼
                        +--------------------+  +--------------------+  +--------------------+
                        | saas_whatsapp_eng  |  |    saas_worker     |  |    saas_ollama     |
                        | (Baileys Node:3000)|  |   (Celery:8000)    |  |   (Ollama:11434)   |
                        +--------------------+  +--------------------+  +--------------------+
                                   │                       │
                                   └───────────┬───────────┘
                                               ▼
                                    ┌────────────────────┐
                                    |    Redis / PG DB   |
                                    +--------------------+
```

---

## 3. Host System Volume Bindings

Specific host paths are mounted to provide data persistence and telemetry resolution inside the FastAPI container (`saas_backend`):

| Host Path | Container Path (backend) | Mount Type | Purpose |
| :--- | :--- | :--- | :--- |
| `uploads_data` (volume) | `/app/uploads` | Read-Write | Shared RAG document storage between backend and worker |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Read-Write | Queries Docker engine `/system/df` for container stats |
| `/var/lib/docker/containers` | `/app/docker-logs` | Read-Only | Computes total container log size |
| `/home/ubuntu/whatsapp-ai-saas` | `/app/project-files` | Read-Only | Audits project codebase size |
| `/tmp` | `/tmp` | Read-Write | Local temporary uploads buffer |

---

## 4. Upstream Proxy Configuration

Nginx acts as the reverse proxy gateway, enforcing rate limiting and timeout configurations:
* **Frontend proxy**: All incoming root traffic (`/`) is proxied to `http://frontend:3000`.
* **API proxy**: Traffic prepended with `/api/v1` is proxied to `http://backend:8000` with:
  * `proxy_read_timeout 3600s` to keep WebSockets connections open.
  * Explicit proxy buffers (`proxy_buffers 4 256k`) to handle large JSON responses without overflow errors.
