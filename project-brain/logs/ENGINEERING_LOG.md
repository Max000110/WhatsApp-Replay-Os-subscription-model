# Engineering Operations & Logs Reference

This document maps container log directories, structured telemetry formats, logging paths, and log rotation policies.

---

## 1. Active Logs Locations

All services route logs to `stdout` and `stderr` within Docker. Docker records these logs on the host VM filesystem at:
`/var/lib/docker/containers/<container-id>/<container-id>-json.log`

### Query Logs in Real-time
*   **FastAPI Backend Logs**:
    ```bash
    docker compose logs -f backend
    ```
*   **WhatsApp Emulation Engine Logs**:
    ```bash
    docker compose logs -f whatsapp-engine
    ```
*   **Celery Background Task Logs**:
    ```bash
    docker compose logs -f worker
    ```

---

## 2. Structured Log Formats

### A. WhatsApp Outbound Sending Telemetry (Baileys manager + anti-ban)
Logs are structured with JSON parameters to simplify querying and tracing:
```text
[AntiBanQueue - a14b378d-4971-4263-bbe0-b8c63aba71be] BEFORE socket.sendMessage: {
  tenant_id: 'eee18224-de89-41c3-9fb3-e4fdebb532eb',
  session_id: 'a14b378d-4971-4263-bbe0-b8c63aba71be',
  jid: '185654373789739@s.whatsapp.net',
  message_id: 'e1403aed-6f36-4779-bb45-a78ab1aab49e',
  message_body: 'Live Override validation from SRE curl',
  socket_state: 'connected',
  dispatch_source: 'AntiBanQueue'
}
```

### B. Inbound Webhook Logs
```text
saas_backend  | [Webhook - a14b378d-4971-4263-bbe0-b8c63aba71be] Routing to Chatbot: sale
saas_backend  | [Webhook - a14b378d-4971-4263-bbe0-b8c63aba71be] AI reply queued for delivery to 185654373789739
```

### C. Message ACK Logs
```text
saas_backend  | [ACK Webhook] Message e1403aed-6f36-4779-bb45-a78ab1aab49e status updated to sending
```

### D. Celery Worker Logs
```text
saas_worker  | [2026-05-28 11:48:51,784: INFO/MainProcess] Connected to redis://:**@redis:6379/0
saas_worker  | [2026-05-28 11:48:52,813: INFO/MainProcess] celery@b3d30cbe400d ready.
```

---

## 3. Telemetry Ingestion Rotation Policies

To prevent logs from consuming all disk space on the Oracle VM host, log rotation limits are configured in `/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
```

### Apply Rotation Configs
```bash
sudo systemctl reload docker
```
This ensures container logs are rotated when they reach 50MB, keeping at most 3 backups.
