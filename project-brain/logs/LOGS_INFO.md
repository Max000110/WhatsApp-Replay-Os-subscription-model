# Logging & Observability Structure

This document details the log structure, container log file locations, trace identifier formats, and log scanning instructions for debugging the platform.

---

## 1. Container Log Locations

All application logs are printed to `stdout` / `stderr` within Docker containers. Docker daemon records these logs locally on the host VM filesystem under:
`/var/lib/docker/containers/<container-id>/<container-id>-json.log`

Use standard docker commands to query and filter them (refer to `COMMANDS.md` for specific command syntaxes).

---

## 2. Structured Log Trace Patterns

### A. WhatsApp Engine Event Dispatches
Logs from `whatsapp-engine` contain dynamic headers indicating session IDs and event classifications:

```text
[2026-05-28 10:10:35] [Engine-a14b378d-...] INCOMING MESSAGE from: 185654373789739@s.whatsapp.net
[2026-05-28 10:10:35] [Engine-a14b378d-...] POSTing webhook payload to FastAPI backend...
[2026-05-28 10:10:36] [Engine-a14b378d-...] Webhook response: 200 OK
```

### B. Anti-Ban Throttling Actions
Anti-ban queues log realistic typing simulator states and transmission delay computations:

```text
[2026-05-28 10:10:41] [AntiBanQueue-a14b378d-...] Simulating composing status for 1420ms (length: 98 chars)
[2026-05-28 10:10:43] [AntiBanQueue-a14b378d-...] Simulating random jitter delay of 5200ms...
[2026-05-28 10:10:48] [AntiBanQueue-a14b378d-...] Safe dispatch succeeded to 185654373789739@s.whatsapp.net
```

### C. FastAPI Webhook Router Logs
FastAPI logs show incoming webhooks and background task dispatches:

```text
INFO:     172.20.0.8:54201 - "POST /api/v1/sessions/webhook HTTP/1.1" 200 OK
[2026-05-28 10:10:35] [app.routers.sessions] Inbound message webhook received for session: a14b378d-...
[2026-05-28 10:10:35] [app.routers.sessions] Routing to Chatbot AI processing... Dispatching Celery task process_ai_reply_task
```

### D. Celery AI Processing Logs
Celery worker logs capture RAG similarity search parameters and Ollama latency logs:

```text
[2026-05-28 10:10:35 INFO/Worker-1] Task worker.tasks.process_ai_reply_task[9103e30d-...] received
[2026-05-28 10:10:35 INFO/Worker-1] [RAG] Vectorizing input query using all-minilm embeddings...
[2026-05-28 10:10:36 INFO/Worker-1] [RAG] Top similarity match score: 0.892 (dist: 0.108), kb_doc_id: 11b302a-...
[2026-05-28 10:10:36 INFO/Worker-1] [AI] Invoking Ollama Qwen2.5 model generation...
[2026-05-28 10:10:40 INFO/Worker-1] [AI] Model response generated. Latency: 4200ms. Length: 154 chars.
[2026-05-28 10:10:40 INFO/Worker-1] Task worker.tasks.process_ai_reply_task[9103e30d-...] succeeded in 5.2s
```

---

## 3. Log Rotation Setup

To prevent container log files from filling up VM disk space under high message throughput, Docker logs are capped at `50m` with a maximum of `3` rotation backups.

This is set globally in `/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
```
Reload docker daemon to apply rotation limits:
```bash
sudo systemctl reload docker
```
