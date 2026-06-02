# Storage Audit — ReplyOS
**Date**: 2026-05-29 | **Prepared by**: Principal SaaS Reliability Engineer
**Methodology**: Extracted via host disk scans, Docker UNIX socket diagnostics, and database telemetry endpoints.

---

## 1. Host Virtual Machine Storage Metrics

The Oracle Cloud host virtual machine disk space allocation details are summarized below:

* **Disk Total Space**: 144.25 GB (`154,894,188,544` bytes)
* **Disk Used Space**: 29.47 GB (`31,639,977,984` bytes)
* **Disk Free Space**: 114.77 GB (`123,237,433,344` bytes)
* **Physical Disk Utilization**: **20.4%**

---

## 2. Platform Component Storage Breakdown

Below is the size distribution across the ReplyOS docker stack and data volumes:

| Component | Storage Size | Size in Bytes | Telemetry Resolution Source |
|:---|:---|:---|:---|
| **Docker Images** | 12.24 GB | `13,141,139,957` | Docker API Socket `/system/df` |
| **Docker Build Cache** | 1.56 GB | `1,676,528,292` | Docker API Socket `/system/df` |
| **Docker Data Volumes** | 1.02 GB | `1,099,013,454` | Docker API Socket `/system/df` |
| **PostgreSQL Database** | 9.19 MB | `9,632,791` | `pg_database_size()` Query |
| **Redis Cache Store** | 1.86 MB | `1,946,176` | Redis `INFO memory` |
| **Project Codebase Files** | 1.61 MB | `1,684,024` | Recursive Directory Scan |
| **Host Container Logs** | 131 KB | `134,502` | JSON Log Directory Scan |
| **Database Backups** | 197 KB | `201,970` | Directory Scan |
| **Temporary Files** | 0 B | `0` | `/tmp` Directory Scan |

---

## 3. Storage Pruning Guidelines

> [!CAUTION]
> **STRICT INSTRUCTION**: DO NOT delete any database backups, logs, container cache, or images automatically. Always solicit user verification and explicit confirmation before executing pruning routines.

### Available Safe Cleanup Commands (For Manual Execution)
* **Prune unused build layers**: `docker builder prune -f`
* **Clean unreferenced networks/containers**: `docker system prune -f`
* **Safely truncate container log file size**:
  ```bash
  find /var/lib/docker/containers/ -name "*-json.log" -exec truncate -s 0 {} \;
  ```
