# LIVE INFRASTRUCTURE AUDIT — ReplyOS

**Date of Audit**: 2026-05-30T17:40:00+05:30  
**Audit Executed By**: Principal Staff SRE Team  

---

## 1. Containerized Services Topology & Uptime

All 8 containers defined in the Docker Compose file are fully active, with zero restart counts and optimal status bounds.

| Container Name | Internal Service | Host Port Mapping | Uptime Status | Health | Restart Count |
|---|---|---|---|---|---|
| `saas_nginx` | Gateway Nginx | `8080->80`, `8443->443` | Up 3 hours | N/A | 0 |
| `saas_backend` | FastAPI Core API | None (Nginx bridged) | Up 17 minutes | Healthy | 0 |
| `saas_frontend` | Next.js Interface | `30000->3000` | Up 2 hours | N/A | 0 |
| `saas_whatsapp_engine` | Baileys Companion | `3000->3000` | Up 2 hours | N/A | 0 |
| `saas_worker` | Celery Processor | None (Nginx bridged) | Up 17 minutes | Healthy | 0 |
| `saas_redis` | Redis Cache/Broker | None (Port 6379) | Up 21 hours | Healthy (`PONG`) | 0 |
| `saas_postgres` | Relational & Vector | None (Port 5432) | Up 21 hours | Healthy (`pg_isready`) | 0 |
| `saas_ollama` | Ollama LLM | `11434->11434` | Up 21 hours | N/A | 0 |

---

## 2. Resource Utilization & Pressure Matrix

The actual resource draw was checked via `docker stats --no-stream` under nominal load conditions:

| Container | CPU % | Memory Draw / Limit | Memory % | PID Count | Network I/O (In / Out) |
|---|---|---|---|---|---|
| `saas_backend` | 0.10% | 94.59 MiB / 2 GiB | 4.62% | 6 | 5.04 MB / 189 kB |
| `saas_worker` | 0.16% | 152.6 MiB / 2 GiB | 7.45% | 3 | 636 kB / 677 kB |
| `saas_frontend` | 0.00% | 56.8 MiB / 1.5 GiB | 3.70% | 23 | 110 kB / 359 kB |
| `saas_whatsapp_engine`| 0.00% | 71.14 MiB / 2 GiB | 3.47% | 11 | 2.25 MB / 16.9 MB |
| `saas_nginx` | 0.00% | 5.60 MiB / 23.41 GiB | 0.02% | 6 | 5.99 MB / 5.81 MB |
| `saas_redis` | 0.51% | 5.12 MiB / 1 GiB | 0.50% | 6 | 52.5 MB / 48.3 MB |
| `saas_postgres` | 0.49% | 63.54 MiB / 3 GiB | 2.07% | 21 | 318 MB / 219 MB |
| `saas_ollama` | 0.00% | 326.9 MiB / 10 GiB | 3.19% | 13 | 1 MB / 301 kB |

---

## 3. Network & Connection Verification

1. **Internal Bridge Network**: All containers are bound to the `whatsapp-ai-saas_default` Docker network and successfully ping each other by name (e.g., `postgres`, `redis`, `ollama`).
2. **Dynamic DNS Routing**: Dynamic upstream resolution in `nginx.conf` (`127.0.0.11` DNS with 5s TTL) ensures Nginx recovers from container IP shifts cleanly on container rebuilds.
3. **Database Health**: Relational tables and vector extension (`pgvector`) have been transactionally verified.
