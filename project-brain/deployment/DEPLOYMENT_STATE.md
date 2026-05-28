# Production Deployment & Infrastructure State

This document details the configuration status, domain structures, Nginx reverse proxy routing rules, security layers (Cloudflare & SSL), and resource allocations of the ReplyOS production deployment.

---

## 1. Domain Routing & Cloudflare Topology

Cloudflare sits at the edge of the infrastructure, managing DNS, CDN, SSL termination, and WebSocket proxy routing.

```
[Client Web Browser] 
       │ (HTTPS / TLS 1.3 Request)
       ▼
   [Cloudflare] ── Proxied (Orange Cloud Enabled)
       │ (DNS wildcard A Record -> Host IP)
       ▼ (SSL/TLS Full Mode)
[Oracle Cloud VM (saas_nginx Gateway on 8080/8443)]
```

### DNS Records Map
* **Root Domain / Dashboard console**: `replyos.com` -> VM IP `144.24.126.153` (Proxied)
* **API Endpoints**: `api.replyos.com` -> VM IP `144.24.126.153` (Proxied)
* **Subdomain Wildcard (Tenants)**: `*.replyos.com` -> VM IP `144.24.126.153` (Proxied)

### Cloudflare Settings Configuration
* **SSL/TLS Mode**: **Full** (strict). Secure encryption from Cloudflare to Nginx reverse proxy.
* **WebSockets**: **Enabled** (Required for real-time state synchronization via WebSocket Connection Manager).
* **IP Forwarding Header**: Cloudflare attaches the `CF-Connecting-IP` header containing the client's public IP address.

---

## 2. Nginx Reverse Proxy State

The Nginx Gateway routes traffic, processes websocket handshakes, caches static resources, and maps real client IPs from Cloudflare headers.

### Active Configuration: `nginx/default.conf`
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m use_temp_path=off;

limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen 80;
    server_name localhost;

    # Gzip Compression Optimization
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # Frontend Server Gateway Routing
    location / {
        proxy_pass http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;

        # Extract Real IP from Cloudflare header or remote address fallback
        set $real_ip $remote_addr;
        if ($http_cf_connecting_ip) {
            set $real_ip $http_cf_connecting_ip;
        }
        proxy_set_header X-Real-IP $real_ip;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API Backend Gateway Routing with Rate Limiting & WebSocket Upgrades
    location /api/v1 {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;

        # Extract Real IP from Cloudflare header or remote address fallback
        set $real_ip $remote_addr;
        if ($http_cf_connecting_ip) {
            set $real_ip $http_cf_connecting_ip;
        }
        proxy_set_header X-Real-IP $real_ip;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Production proxy buffers to prevent 502/504 overflows on large JSON payloads
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }
}
```

---

## 3. Production Resource Allocation (Compose)

Containers are sandboxed with memory limits in `docker-compose.yml` to prevent Out-Of-Memory (OOM) faults on Oracle Cloud Free Tier resources:
* **Postgres (`saas_postgres`)**: RAM Limit `3G`. Holds index lists and vector spaces.
* **Redis (`saas_redis`)**: RAM Limit `1G`. Runs job broker channels and event pub/sub.
* **FastAPI Backend (`saas_backend`)**: RAM Limit `2G`. Processes API requests and DB sessions.
* **Celery Worker (`saas_worker`)**: RAM Limit `2G` (Concurrency pinned to `2` to throttle CPU cores).
* **WhatsApp Node Engine (`saas_whatsapp_engine`)**: RAM Limit `2G`. Maintains multiple Baileys dynamic connection sockets.
* **Frontend Next.js (`saas_frontend`)**: RAM Limit `1.5G`. Handles SSR page serves.
* **Nginx Proxy (`saas_nginx`)**: RAM Limit `1G`. Manages SSL connections and header proxy limits.

---

## 4. Disaster Recovery & Backup Schedule

### Automated Backup Script
File: `~/whatsapp-ai-saas/project-brain/backups/backup_cron.sh`
```bash
#!/bin/bash
BACKUP_DIR="/home/ubuntu/whatsapp-ai-saas/project-brain/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Dump PostgreSQL structures and tables
docker exec -t saas_postgres pg_dump -U saas_admin saas_whatsapp > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

# Archive code modifications and files
tar -czf "$BACKUP_DIR/project_files_backup_$TIMESTAMP.tar.gz" -C /home/ubuntu whatsapp-ai-saas

# Keep only the last 7 days of backups to save disk volume
find "$BACKUP_DIR" -type f -mtime +7 -name "*.sql" -delete
find "$BACKUP_DIR" -type f -mtime +7 -name "*.tar.gz" -delete
```

### Cron Schedule configuration
Executes nightly at 2:00 AM:
```cron
0 2 * * * /bin/bash /home/ubuntu/whatsapp-ai-saas/project-brain/backups/backup_cron.sh
```
