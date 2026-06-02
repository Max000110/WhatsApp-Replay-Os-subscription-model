# ReplyOS — Open Bugs Registry

**Last Updated**: 2026-05-30T18:45:00+05:30

This document catalogues all currently identified open bugs, infrastructure limitations, and active operational risks.

---

## 1. Resolved & Verified Bugs (This Session)

### BUG-001 — Outbound Delivery Status Delays (Durable Webhook Queue)
- **Priority**: P1 (Core Functionality)
- **Status**: ✅ RESOLVED & VERIFIED
- **Symptom**: Webhook notifications and delivery ACK callbacks to the backend were lost when backend went down during rebuilds, keeping states stuck in "sent".
- **Resolution**: Implemented Postgres `pending_webhooks` queue table. Engine catches axios failures, saving them to DB. A background queue scheduler retries dispatches every 30 seconds (up to 5 attempts). Added startup sweep to auto-replay webhooks on engine boot.
- **Verification Evidence**: E2E Test 9 (Delivery ACK) validated successful ACK webhook status transitions inside database.

### BUG-002 — International JID Country Code Prepending
- **Priority**: P1 (International Support)
- **Status**: ✅ VERIFIED & OPERATIONAL
- **Symptom**: Outbound messages sent to international numbers manually entered without country codes failed JID normalization.
- **Resolution**: Rewrote `normalize_jid()` to accept optional `default_country_code` parameter (default "91" for Indian backward compat). Added `default_country_code` column to `tenant_settings`. Wired lookup into webhook inbound, manual send, and conversation merge call sites.
- **Verification Evidence**: E2E Test 6 (WhatsApp Message Receive) validated successful normalization of LID and standard phone formats.

### BUG-004 — Multi-intent Truncation
- **Priority**: P1 (Context Assembly)
- **Status**: ✅ RESOLVED & VERIFIED
- **Symptom**: Compound customer questions with multiple logical connectors (aur, and, ,) suffered from parameter token starvation.
- **Resolution**: Injected `SYSTEM_CORE_DIRECTIVE` multi-intent extraction layer and dynamic logical connectors scanner splits compound queries into segment iterations.

### BUG-005 — Multipart RAG File Failures
- **Priority**: P1 (Data Ingestion)
- **Status**: ✅ RESOLVED & VERIFIED
- **Symptom**: Multipart form upload timeouts and file processing blocks.
- **Resolution**: Realigned Next.js client parameters with standard multi-part forms and implemented chunked binary streaming size verification pipeline.

### BUG-006 — Websocket Handoff Blockades
- **Priority**: P1 (State Synchronization)
- **Status**: ✅ RESOLVED & VERIFIED
- **Symptom**: Live human agent overrides failed to flush Ollama loop and update dashboard badges.
- **Resolution**: Deployed `bot_override` tracking in `Conversation` model and forced `CONNECTED_GREEN` websocket state transmissions.

### BUG-007 — Static Config and RAG Catalog Collision
- **Priority**: P1 (Context Assembly)
- **Status**: ✅ RESOLVED & VERIFIED
- **Symptom**: Context collision between static `AI Bot Config` and dynamic `RAG Documents` catalog store (e.g. food menus), resulting in default templates displaying instead of uploaded files.
- **Resolution**: Implemented hybrid context routing in `assemble_layered_prompt` prioritizing RAG vector chunks in Layer 5. Injected compound query multi-intent detection and RAG checks inside fast-path intent classifier to prevent static deflection caches when RAG catalog matching is available.

---

## 2. Active Operational Risks

### BUG-003 — Ollama AI Inference CPU Exhaustion
- **Priority**: P2 (Resource Exhaustion)
- **Symptom**: Heavy chatbot message queues cause CPU spikes on the host VM, slowing down WebSockets and API response times.
- **Root Cause**: Ollama execution runs locally inside the CPU-bound container `saas_ollama` (Oracle VM does not have GPU acceleration).
- **Mitigation Plan**: Implement worker-level concurrency limits in Celery to throttle chatbot processing, and leverage Fast-Path Deflect Caches. Recommend offloading complex conversational prompts to an external GPU hosting provider (e.g. OpenRouter).
