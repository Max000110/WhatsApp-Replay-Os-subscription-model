# Debugging History — ReplyOS WhatsApp SaaS

**Last Updated**: 2026-05-30T18:30:00+05:30

---

## ## INC-019: Nginx 502 Bad Gateway - Stale Upstream DNS Cache (P0)
- **Severity**: P0 — Business Critical
- **Symptom**: Admin Control Plane returned 502 Bad Gateway on container restarts.
- **Root Cause**: Nginx resolved upstream backend bridge IP address once at boot, caching the stale IP address indefinitely when container IP shifted.
- **Fix**: Added dynamic Docker DNS resolver (`127.0.0.11`) inside Nginx conf with a 5-second TTL cache (`resolver 127.0.0.11 valid=5s;`) and variable-based proxy routing.
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-020: P0 Tenant Suspend / Deactivation Admin Lockout & UI/Backend Reconciliation
- **Severity**: P0 — Control Plane Integrity
- **Symptom**: Suspending a tenant logged the admin out, and the frontend exposed destructive actions (Suspend, Terminate, Revoke Access, Disconnect Sessions, Archive) for the administrative `System Operations` tenant, which backend later rejected, causing UI/Backend policy inconsistency.
- **Root Cause**: Backend lacks admin role exclusion on deactivation loops, and frontend failed to restrict operations on administrative tenants.
- **Fix**: Excluded admin role (`role != 'admin'`) from deactivation sweeps. Hardened the backend by blocking suspend, terminate, purge, logout, access revocation, retention policy change, or session disconnect on `System Operations` with `HTTP 400 Bad Request`. Reconciled the UI by introducing a canonical `isProtectedTenant` check in Next.js, hiding all destructive controls, rendering `'System Managed'` text for Data Policy, and displaying a premium `'Protected System Tenant'` shield badge in place of all action buttons.
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-021: Durable Webhook/ACK Retry Queue (BUG-001)
- **Severity**: P1 — Delivery Reliability
- **Symptom**: ACK delivery notifications lost during container rebuilds.
- **Root Cause**: Webhook and ACK dispatches were one-shot POST requests. If backend container went down, dispatches were silently dropped.
- **Fix**: Created Postgres `pending_webhooks` queue table. Webhook dispatches that catch failures are saved to DB. A background queue scheduler retries failed requests every 30 seconds (up to 5 attempts). Added startup sweep to auto-replay webhooks on engine boot.
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-022: Tenant Termination Inconsistencies & Purge Lifecycles (INCIDENT-B)
- **Severity**: P1 — Administrative Reconciliation
- **Symptom**: Terminated tenants remained visible on dashboard, and attempting to manual purge them returned "Cannot purge. Tenant retention policy is set to 'archive'", blocking space cleanup.
- **Root Cause**: Database had no soft-delete visibility check on lists, and purge endpoints strictly blocked any tenant whose default retention policy was set to "archive".
- **Fix**: Added `is_visible` Column (Boolean, default True) to the `tenants` table schema. When terminated (via Mode 1 or graceful Celery expiration task), `is_visible` is set to `False`, immediately removing them from dashboard views and updating metrics counters instantly without page refresh, keeping audits intact. Upgraded `/purge` endpoint to allow manual hard purging already terminated tenants by bypassing the archive retention policy check.
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-023: AI Brain Quality & Generic Responses (INCIDENT-C)
- **Severity**: P1 — Intelligence Experience
- **Symptom**: Bot responses sound generic, repetitive, and default back to ReplyOS helpdesk info.
- **Root Cause**: Chatbot prompt builder had a simple structure lacking deep company context, location details, customer sentimental context, lead funnel state, or active tickets.
- **Fix**: Upgraded prompt builder to a premium 15-layered system prompt assembly, pulling structured customer metadata and business profile details from DB.
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-024: Dynamic AI 404 Recovery Fallback (INCIDENT P0-A)
- **Severity**: P0 — Conversational Interruption
- **Symptom**: WhatsApp responds with `[AI Engine Response Code Error 404]` when a tenant chatbot model tag is configured with an un-pulled model name.
- **Root Cause**: Missing fallback handling inside background pipelines combined with scope variable shadowing `UnboundLocalError` on line 309 in `/app/routers/sessions.py`.
- **Fix**: Synced the DB models directly to `'qwen2.5:1.5b-instruct'` and added dynamic fallback hierarchy catching 404s inside `ai_service.py` to auto-route to default model. Programmatically validated with `test_production_acceptance_suite.py` Test 8, demonstrating instant recovery (1.27 seconds) under un-pulled model configs.
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-025: SQL ForeignKeyViolation on Tenant Hard Purge (P0)
- **Severity**: P0 — Data Integrity & Administrative Lifecycles
- **Symptom**: Triggered `(psycopg2.errors.ForeignKeyViolation) insert or update on table "audit_logs" violates foreign key constraint` in backend container logs, failing audit dispatches during `/purge` endpoint runs.
- **Root Cause**: The backend router deleted the tenant (`db.delete(tenant)` + `db.commit()`) *before* executing the audit logger (`log_audit`). Because `target_tenant_id` was reference-locked to `tenants(id)`, referencing the already deleted ID threw SQL constraint violations. Since `target_tenant_id` has `ondelete="CASCADE"`, logging it before deletion would have caused the audit log record itself to be wiped by cascade, losing the SRE record of the manual hard purge.
- **Fix**: Re-ordered the execution to log the audit entry *before* deleting the tenant. Set `target_tenant_id = None` inside the log entry to completely bypass the database reference check and prevent cascade deletions, while embedding the target tenant's ID and name into the `affected_resources` string (`f"tenant:{tenant_id}:{tenant_name}"`).
- **Status**: ✅ RESOLVED & VERIFIED

## ## INC-026: Synchronous Endpoint Event Loop RuntimeError in Handoff/Release routes
- **Severity**: P1 — Handoff Reliability
- **Symptom**: `RuntimeError: There is no current event loop in thread 'AnyIO worker thread'` occurred during E2E handoff test runs, failing requests with HTTP 500.
- **Root Cause**: The endpoints `handoff_conversation` and `release_conversation` were defined as synchronous (`def`), forcing FastAPI/AnyIO to execute them in a worker pool thread where no active event loop is established. Attempting to call `asyncio.get_event_loop()` or trigger async websocket publishes inside them threw event loop runtime exceptions.
- **Fix**: Re-engineered both endpoints to be asynchronous (`async def`) and directly awaited the websocket manager `await websocket_manager.publish_event` on the main event loop thread, completely eliminating all worker-thread runtime exceptions and guaranteeing fast, non-blocking broadcasts.
- **Status**: ✅ RESOLVED & VERIFIED

