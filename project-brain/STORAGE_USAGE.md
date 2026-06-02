# ReplyOS — Storage & Infrastructure Usage Registry

This document records the exact physical disk partition usage and container storage metrics audited on the Oracle Cloud VM host.

---

## 1. Physical Host Disk Partition Footprint

* **Audit Timestamp**: 2026-05-29T21:18:00+05:30  
* **Target Partition**: `/dev/sda1` (Root mount point)
* **Total Host Disk Space**: **144.26 GB** (`154,894,188,544` bytes)
* **Used Host Disk Space**: **28.39 GB** (`30,484,676,608` bytes) — **20%** utilization
* **Free Host Disk Space**: **115.85 GB** (`124,392,734,720` bytes) — **80%** available buffer

---

## 2. Docker Container Stack Footprint

Resolved dynamically from the Unix socket `/var/run/docker.sock` and host mappings:

| Component | Size in Bytes | Human Readable Size | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Docker Images** | `13,141,140,011` | 12.24 GB | In Use | Size of all 8 system container images |
| **Docker Volumes** | `1,098,976,562` | 1.02 GB | In Use | postgres_data, redis_data, ollama_data, certs, uploads |
| **Docker Build Cache**| `977,593,995` | 932.30 MB | Pruned | Baseline cache remaining after Phase 7 cleanup |
| **Container Stdout Logs**| `82,652` | 80.71 KB | Truncated | All `*-json.log` files truncated to 0 |
| **PostgreSQL Database**| `9,624,599` | 9.18 MB | Active | Application data |
| **Redis Cache Memory** | `1,642,776` | 1.57 MB | Active | Runtime lock and session data |
| **Project Workspace** | `1,581,049` | 1.51 MB | Active | ReplyOS source files `/home/ubuntu/whatsapp-ai-saas` |
| **Backups & Dumps** | `201,970` | 197.24 KB | Active | Database state dumps |
| **Documentation Folder**| `962,560` | 940.00 KB | Active | `project-brain/` folder size |
| **Temporary Folder** | `0` | 0.00 KB | Cleared | `/tmp` cleaned files |

---

## 3. Storage Cleanup Event Summary (2026-05-29)

A safe storage cleanup workflow was executed:
1. **Docker Builder Prune**: Removed unused build steps, reclaiming **11.18 GB**.
2. **Log Truncation**: Truncated all active container output json logs, reclaiming **827.01 KB**.
3. **Dangling images / volumes**: Confirmed 0B of dangling layers exist on active containers.
4. **Overall Host Reclaimed Space**: Dropped Used Space on `/` partition from **38.41 GB** to **28.39 GB** (recovering **10.02 GB** of physical storage).
