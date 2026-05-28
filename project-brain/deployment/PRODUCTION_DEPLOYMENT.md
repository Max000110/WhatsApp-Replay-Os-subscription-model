# Production Deployment & Infrastructure Guide

This guide details the steps to migrate the WhatsApp AI SaaS platform from a development sandboxed environment into a production-grade infrastructure on Oracle Cloud/AWS, secured with Cloudflare, SSL/TLS, and automated backup routines.

---

## 1. Domain Routing & Cloudflare Setup

To optimize security and availability, Cloudflare should act as the DNS provider, CDN, and DDoS protection layer:

```
[Client Web Browser] 
       │ (HTTPS Request)
       ▼
  [Cloudflare] ── Proxy (Orange Cloud Enabled)
       │ (DNS A Record -> Oracle VM IP)
       ▼ (SSL Full Mode)
[Oracle Cloud VM (saas_nginx Gateway on 80/443)]
```

### Cloudflare Settings Configuration Checklist
1. **DNS Records**:
   - Create an `A` record pointing `yourdomain.com` and `*.yourdomain.com` (wildcard for SaaS tenants) to your public Oracle Cloud VM IP (`144.24.126.153`).
   - Enable the **Orange Cloud Proxy** (Proxied status).
2. **SSL/TLS Encryption Mode**:
   - Set encryption mode to **Full** or **Full (strict)**. This guarantees E2E encryption between Cloudflare and your Nginx container gateway.
3. **Websockets Support**:
   - Inside Cloudflare Network dashboard, verify **WebSockets** is toggled **ON**.
4. **Security Settings**:
   - Enable **Browser Integrity Check**.
   - Configure a WAF rule block challenging automated malicious crawlers bypassing Nginx.

---

## 2. Nginx Production Reverse Proxy Configuration

Nginx acts as the primary API Gateway, managing SSL termination, routing HTTP requests to FastAPI, websockets to the frontend and backend sockets, and enforcing rate limits.

Below is the production `nginx/default.conf` configuration template:

```nginx
# File: nginx/default.conf

# Upstream Server Pools for Load Balancing
upstream frontend_pool {
    server frontend:3000;
}

upstream backend_pool {
    server backend:8000;
}

# Rate Limiting Definitions
limit_req_zone $binary_remote_addr zone=api_limit_zone:10m rate=15r/s;

server {
    listen 80;
    server_name yourdomain.com *.yourdomain.com;

    # Automated Redirect to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com *.yourdomain.com;

    # SSL Certificates Configuration (Let's Encrypt / Cloudflare Origin Certs)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # Secure SSL Protocols and Ciphers
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';

    # Buffer Adjustments to Prevent 502 Bad Gateway with Base64 QR codes
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;

    # Gzip Optimization
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # 1. Routing Next.js Frontend (Static & Websockets)
    location / {
        proxy_pass http://frontend_pool;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 2. Routing FastAPI Backend API (Throttled)
    location /api/v1/ {
        limit_req zone=api_limit_zone burst=30 nodelay;
        proxy_pass http://backend_pool/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 3. Production Environment Secret Configuration

Store production parameters in `/home/ubuntu/whatsapp-ai-saas/.env`. Never commit this file to public version controls.

```ini
# Database Configurations (Production Hardened)
DB_NAME=saas_whatsapp
DB_USER=saas_admin_prod
DB_PASSWORD=SecurePasswordHashedAndGenerated987!

# Redis Configurations
REDIS_PASSWORD=SecureBrokerPasswordHashedAndGenerated456!

# JWT Authentication Configs
JWT_SECRET=HMACSIGNKEY256BITGENERATEDFORPRODUCTIONSECURITY987654321!

# Active AI Provider Driver: ollama | openrouter | gemini
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-v1-your-openrouter-production-api-key-here
OLLAMA_HOST=http://ollama:11434

# Internal API Routing Keys
WHATSAPP_ENGINE_URL=http://whatsapp-engine:3000
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
```

---

## 4. Production Docker Strategy

For production runtime environments:
1. **Remove Port Exposure Bindings**:
   - Remove Host port bindings for `ollama` (`11434:11434`) and `whatsapp-engine` (`3000:3000`) in `docker-compose.yml`. Only expose Nginx Gateway ports `80` and `443` to host interface. This secures micro-services inside isolated virtual docker networks.
2. **Resource Throttling Settings**:
   - Enforce memory limit caps in Docker Compose:
     * Postgres: Limit `3G`, Reservation `1.5G`
     * Backend: Limit `2G`, Reservation `500M`
     * Engine: Limit `2G`, Reservation `500M`
     * Nginx: Limit `1G`, Reservation `100M`

---

## 5. Automated Backup Systems

Create a backup shell script `~/whatsapp-ai-saas/project-brain/backups/backup_cron.sh`:

```bash
#!/bin/bash
# Production Backup Script
BACKUP_DIR="/home/ubuntu/whatsapp-ai-saas/project-brain/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 1. Backup PostgreSQL Schema & Data
docker exec -t saas_postgres pg_dump -U saas_admin saas_whatsapp > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

# 2. Package codebase, configuration, and logs
tar -czf "$BACKUP_DIR/project_files_backup_$TIMESTAMP.tar.gz" -C /home/ubuntu whatsapp-ai-saas

# 3. Retain only last 7 days of backups locally to prevent disk fill
find "$BACKUP_DIR" -type f -mtime +7 -name "*.sql" -delete
find "$BACKUP_DIR" -type f -mtime +7 -name "*.tar.gz" -delete

echo "Backup execution finished successfully for $TIMESTAMP"
```

Configure `cron` to execute the backup script daily at 2:00 AM:
```bash
0 2 * * * /bin/bash /home/ubuntu/whatsapp-ai-saas/project-brain/backups/backup_cron.sh
```

---

## 6. SRE Monitoring & Alerts

1. **Host Monitoring (Prometheus + Grafana)**:
   - Configure `node_exporter` on the Ubuntu host VM to scrape CPU, RAM, and Disk metrics.
2. **Docker Container Health Logs**:
   - Configure `cAdvisor` to collect individual CPU/RAM resource logs per container.
3. **Health Alerts**:
   - Configure a webhook alert in Grafana to message Discord or Slack if any core service becomes `unhealthy` or memory usage spikes past 92% for longer than 3 minutes.
