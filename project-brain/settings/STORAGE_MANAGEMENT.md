# Storage Management and Cleanup Workflow Specification

This document details the disk storage capacity, Docker environment footprint, and step-by-step cleanup workflows configured for the ReplyOS host virtual machine.

---

## 1. Solid State Disk Footprint

The host VM is allocated a solid-state disk partition:
* **Total Host Capacity**: ~145 GB
* **Normal Operating Base**: ~28 - 30 GB used (Postgres, Redis, Ollama models, Next.js assets, Docker images, pruned build cache)
* **Free Buffer Size**: ~115 - 116 GB free

### 1.1 In-Container Telemetry Resolution
Since the FastAPI server executes inside a Docker container (`saas_backend`), host-level disk metrics are retrieved using the following enforcements:
1. **Host Disk Partition**: Checked using Python's `psutil.disk_usage('/')` within the container. (Due to Docker's overlay filesystem mapping on Linux, this returns the parent VM's partition capacity and usage).
2. **Docker Engine Disk Usage**: Measured by mounting `/var/run/docker.sock` to the backend container and executing raw Unix socket queries to the Docker API endpoint `/system/df`.
3. **Database Footprint**: Querying the active Postgres session: `SELECT pg_database_size(current_database())`.
4. **Redis Cache Memory**: Querying Redis memory stats: `r.info("memory")["used_memory"]`.
5. **Log File Accumulation**: Mounting `/var/lib/docker/containers` as read-only to the backend container at `/app/docker-logs`. The system sums the sizes of all active `*-json.log` files recursively.

---

## 2. Safe Cleanup Workflow (Phase 7)

A safe cleanup workflow was executed on 2026-05-29:
* **Before**: ~39 GB VM disk used (Build Cache: 12.16 GB, Container logs: 880 KB)
* **After**: ~29 GB VM disk used (Build Cache: 977 MB, Container logs: 53 KB)
* **Reclaimed space**: 10.02 GB (Build cache: 11.18 GB pruned)


To prevent accidental data loss, the cleaning script must **NEVER** run automatically. It must be triggered manually by the Super Admin after confirming estimated savings.

### 2.1 Reclaimable Components
The following resources are audited and eligible for cleanup:

| Component | Prune Command | Safety / Risk |
| :--- | :--- | :--- |
| **Docker Builder Cache** | `docker builder prune -f` | ✅ High Safety. Removes intermediate build stages. No runtime impact. |
| **Unused Docker Images** | `docker image prune -a -f` | ✅ Safe. Only drops image layers not linked to running containers. |
| **Unused Docker Volumes** | `docker volume prune -f` | ⚠️ Moderate Risk. Drops inactive volumes. Active data volumes are locked. |
| **Temporary Files** | `rm -rf /tmp/*` | ✅ High Safety. Cleans system temp files. |
| **Old Logs** | Truncate log files to 0 bytes. | ✅ High Safety. Cleans container stdout output logs. |

### 2.2 Execution Sequence
1. Admin queries storage status: `GET /admin/storage-report`
2. UI displays reclaimable space: `X GB`
3. Admin triggers cleanup via command line or Chat interface.
4. System executes commands sequentially and captures disk metrics before and after the operation.
