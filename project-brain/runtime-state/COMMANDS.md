# Runtime & Operations Command Reference

This document provides a catalog of commands required to build, run, monitor, test, and backup the WhatsApp AI SaaS platform.

---

## 1. Docker Compose Management

### Build & Restart All Services
```bash
cd ~/whatsapp-ai-saas
docker compose build
docker compose up -d
```

### Rebuild and Restart Specific Microservice
```bash
# Example for Backend API
docker compose build backend
docker compose up -d backend

# Example for WhatsApp Engine
docker compose build whatsapp-engine
docker compose up -d whatsapp-engine

# Example for Next.js Frontend
docker compose build frontend
docker compose up -d frontend
```

### Stop & Down the Stack
```bash
docker compose down
```

### Nuke and Reset all Volumes (Warning: Wipes DB)
```bash
docker compose down -v
```

---

## 2. Real-Time Log Monitoring

### Stream All Logs
```bash
docker compose logs -f
```

### Stream Service-Specific Logs
```bash
# FastAPI Backend
docker compose logs -f backend

# Node.js WhatsApp Engine
docker compose logs -f whatsapp-engine

# Celery Worker
docker compose logs -f worker

# Ollama LLM Engine
docker compose logs -f ollama
```

---

## 3. Database Administration

### Enter Interactive Postgres Shell (psql)
```bash
docker exec -it saas_postgres psql -U saas_admin -d saas_whatsapp
```

### Dump / Backup Database (SQL format)
```bash
docker exec -t saas_postgres pg_dump -U saas_admin saas_whatsapp > ~/whatsapp-ai-saas/project-brain/backups/db_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore Database Dump
```bash
docker exec -i saas_postgres psql -U saas_admin -d saas_whatsapp < ~/whatsapp-ai-saas/project-brain/backups/your_db_backup.sql
```

### Verify Messages Count and Status inside Postgres
```bash
docker exec -it saas_postgres psql -U saas_admin -d saas_whatsapp -c "SELECT sender_type, status, COUNT(*) FROM messages GROUP BY sender_type, status;"
```

---

## 4. Webhook & Integration Testing (curl)

### Health Check Endpoint Verification
```bash
# Nginx Gateway
curl -i http://localhost:8080/api/v1/sessions/health

# FastAPI Backend Direct
curl -i http://localhost:8000/api/v1/sessions/health
```

### Trigger Inbound Message Simulation (Webhook test)
This simulates a user sending "VALIDATION-FINAL" to the bot:
```bash
curl -X POST http://localhost:8080/api/v1/sessions/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a14b378d-4971-4263-bbe0-b8c63aba71be",
    "customer_phone": "185654373789739",
    "content": "VALIDATION-FINAL message for AI reply"
  }'
```

### Trigger Outbound Live Override Send Test
This simulates an agent manually overriding the AI and pushing a message:
```bash
curl -X POST http://localhost:8080/api/v1/chats/send \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a14b378d-4971-4263-bbe0-b8c63aba71be",
    "customer_phone": "185654373789739",
    "content": "Live Override validation from SRE curl"
  }'
```

---

## 5. Redis Cache & Broker Verification

### Check Redis Health
```bash
docker exec -it saas_redis redis-cli -a SecretRedisPassword123! ping
```

### View Redis Queue Keys
```bash
docker exec -it saas_redis redis-cli -a SecretRedisPassword123! keys "*"
```

### Clear Redis Cache (Warning: Wipes active task queues)
```bash
docker exec -it saas_redis redis-cli -a SecretRedisPassword123! flushall
```

---

## 6. SRE Server Health Checks

### Check RAM Consumption
```bash
free -m
```

### Check VM Disk Storage Usage
```bash
df -h
```

### Monitor VM CPU & Process Spikes
```bash
top -b -n 1 | head -n 20
```

### List Docker Container Port Bindings
```bash
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"
```
