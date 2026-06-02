# Master Admin WhatsApp Runtime Controls

This document details the Master Admin control interface that monitors, suspends, and coordinates WhatsApp instances, anti-ban queues, and Redis PubSub networks.

---

## 1. Global Session Monitoring

The Master Admin panel accesses the `/api/v1/admin/system-health` and `/api/v1/admin/monitoring` endpoints to pull session diagnostics directly from PostgreSQL and the WhatsApp Engine.

### Super Admin Session Metrics
* **Total Registered Sessions**: Count of all WhatsApp Web instances in the database.
* **Connected Sockets**: Count of active TCP socket connections managed in-memory by Baileys.
* **Redis Queue State Audit**: Monitors Redis lists `whatsapp_queue_[sessionId]` for size and queue delays to detect delivery bottlenecks.
* **Active WebSocket Scopes**: Counts total real-time browser connections active across the multi-tenant system.

---

## 2. Emergency Session Terminations & Quota Overrides

In the event of network abuse, spamming, or subscription defaults, the Master Admin can trigger immediate socket closures and block dispatches.

### Emergency Shutdown Route
* **Endpoint**: `/api/v1/admin/tenants/{id}/shutdown`
* **Backend Action**:
  1. Sets all active `whatsapp_sessions` status to `"disconnected"` in PostgreSQL.
  2. Queries the WhatsApp Node Engine via `DELETE /sessions/{sessionId}` to immediately terminate the Baileys TCP socket connection.
  3. Flushes the Redis Anti-Ban queue `whatsapp_queue_[sessionId]` to purge any pending outbound messages.
  4. Publishes a `session_terminated` event down the tenant's WebSocket channel to force-disconnect the dashboard client.

---

## 3. Realtime Maintenance Broadcasts

Admin operators can broadcast urgent notifications (e.g. system maintenance windows, billing alerts) to all connected clients globally.

### Broadcast Mechanism
* **Endpoint**: `POST /api/v1/admin/broadcast-maintenance`
* **Execution Flow**:
  1. Backend receives message payload.
  2. Calls `websocket_manager.broadcast_global_event("maintenance_broadcast", {"message": payload.message})`.
  3. Iterates over all active socket maps in Python memory and publishes down all tenant channels simultaneously.
  4. Next.js dashboard receives event in the core WebSocket reducer and pops up a premium, vibrant system-wide glassmorphism notification banner across the UI.
