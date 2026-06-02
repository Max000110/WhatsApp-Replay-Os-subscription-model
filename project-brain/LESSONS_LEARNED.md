# Lessons Learned — ReplyOS Engineering History
**Last Updated**: 2026-05-29T19:27:25+05:30

This document records all root causes discovered, architectural mistakes, and recommended engineering standards derived from the full production history of the ReplyOS WhatsApp SaaS platform.

---

## 1. WhatsApp / JID Architecture Lessons

### LESSON-001: Never Store Raw Phone Numbers — Always Canonical JIDs
**Root Cause**: Different entry points (manual override, inbound webhook, campaign) stored phone numbers differently — raw digits, plus-prefixed, with device suffixes. This caused conversation fragmentation.  
**Correct Pattern**: All storage and retrieval MUST use the canonical format: `[digits]@s.whatsapp.net`. Use `normalize_jid()` at every entry point without exception.  
**Files**: `backend/app/core/jid.py`, `sessions.py`, `chats.py`, `campaigns.py`, `worker/tasks.py`

### LESSON-002: Baileys Companion Device JIDs Are Mangled — Always Strip `:device`
**Root Cause**: Baileys sends companion device events with JIDs like `18565437378:9739@s.whatsapp.net`. The colon separates the primary number from the device agent index. Storing this verbatim creates a different identity than the base user.  
**Correct Pattern**: Always split by `@` then `:` and take `[0]` of each split: `remoteJid.split('@')[0].split(':')[0]`

### LESSON-003: Anti-Ban Regex Must Be Permissive Enough for International Numbers
**Root Cause**: Initial regex `^91[6-9]\d{9}@s\.whatsapp\.net$` only matched Indian mobile numbers. This blocked all international customers and all LID format JIDs.  
**Correct Pattern**: Backend validation and anti-ban TypeScript guard must support full international number ranges: `\d{7,20}` minimum, with special-case handling for `@lid` and `@g.us` domains.

### LESSON-004: Bot Pause State Must Be Reset Between Test Sessions
**Root Cause**: `bot_paused_until` is set for 15 minutes on every manual agent message. In testing, multiple manual sends set a future pause, blocking AI responses for the test duration.  
**Correct Pattern**: Before running AI pipeline tests, always check `bot_paused_until` and reset if needed: `UPDATE conversations SET bot_paused_until = NULL WHERE id = 'xxx'`

### LESSON-005: Fake/Test Numbers Will Never Get Delivery ACKs
**Root Cause**: Test conversations created with invented numbers like `185654373789739` will queue messages successfully but never receive delivery receipt webhooks — because those numbers don't exist on WhatsApp.  
**Correct Pattern**: All end-to-end delivery testing must use a real, registered WhatsApp number. Keep `917021886525` as the canonical test device.

---

## 2. Infrastructure & Container Lessons

### LESSON-006: Nginx DNS Cache Must Be Refreshed After Container Restarts
**Root Cause**: Nginx resolves container hostnames at startup and caches them. Container restart = new Docker IP = Nginx gets `502` for all requests.  
**Correct Pattern**: After ANY backend or whatsapp-engine container restart, always run: `docker exec saas_nginx nginx -s reload`

### LESSON-007: ALL Python Dependencies Must Be in requirements.txt Before Build
**Root Cause**: `psutil` was used in admin health endpoint but not declared in `requirements.txt`. The container built successfully (the import is inside a function), but crashed at runtime with `ModuleNotFoundError`.  
**Correct Pattern**: Any `import` statement in any Python file must have the corresponding package in `requirements.txt`. Always validate with `pip check` after adding packages.

### LESSON-008: Frontend Sequential try-catch Data Loading Is Fragile
**Root Cause**: Admin dashboard loaded all data in one `try-catch` block. A single API failure (the `psutil` crash) aborted ALL subsequent data fetches — tenants, health, monitoring — leaving the UI completely empty.  
**Correct Pattern**: Each data type (tenants, system health, monitoring) must be fetched in **independent** `try-catch` blocks so individual failures don't cascade and kill the whole dashboard.

### LESSON-009: Always Use Optional Chaining on API Response Objects in Frontend
**Root Cause**: `health.services.postgres` threw `Cannot read properties of undefined` if the `services` key was missing (e.g., when API partially failed).  
**Correct Pattern**: Always use `health?.services?.postgres` and initialize all state with safe defaults before the first render.

---

## 3. Database Architecture Lessons

### LESSON-010: Unique Constraints Must Be Applied at Database Level, Not Only in Code
**Root Cause**: Conversation deduplication was only done in application code. Race conditions under concurrent requests still created duplicate rows. The DB had no enforcement.  
**Correct Pattern**: Apply unique constraints at DB level: `UNIQUE(tenant_id, customer_phone)`. Let the database be the final arbiter of uniqueness. Use upsert (`ON CONFLICT DO UPDATE`) patterns in application code.

### LESSON-011: Column Width Matters for JID Storage
**Root Cause**: `customer_phone VARCHAR(50)` was too short for full JID strings like `185654373789739@s.whatsapp.net` (31 chars) or group JIDs which can be longer.  
**Correct Pattern**: Use `VARCHAR(100)` for all JID/phone columns. JIDs can be up to ~40 characters; `VARCHAR(100)` provides safe headroom.

### LESSON-012: Add Idempotency Checks BEFORE INSERT, Not AFTER
**Root Cause**: Baileys retransmits messages. Without a pre-INSERT idempotency check, duplicate `whatsapp_message_id` values caused `IntegrityError` exceptions that were messy to handle.  
**Correct Pattern**: Always check `WHERE whatsapp_message_id = :id` BEFORE attempting INSERT. Return early if already exists.

---

## 4. Payment / Billing Architecture Lessons

### LESSON-013: Never Use Placeholder Payment Keys in Development .env
**Root Cause**: `.env` shipped with `rzp_test_mockKeyId12345`. When the team ran tests, they got confusing authentication errors that looked like SDK problems, not configuration problems.  
**Correct Pattern**: Use `RAZORPAY_KEY_ID=REPLACE_WITH_REAL_TEST_KEY` as placeholder. Document that keys must be provisioned before any billing test.

### LESSON-014: Razorpay SDK Version Matters — Verify PyPI Availability
**Root Cause**: `requirements.txt` specified `razorpay==1.4.3` which doesn't exist on PyPI. Container builds succeeded (dependency ignored by pip?) but the SDK was absent at runtime.  
**Correct Pattern**: Always verify PyPI package version exists before adding to `requirements.txt`. Use `pip index versions razorpay` or check PyPI directly.

### LESSON-015: Bubble Razorpay Errors as 400, Not 500/502
**Root Cause**: Using raw `httpx` to call Razorpay returned raw HTTP errors. These became `500 Internal Server Error` responses, which Nginx surfaced as `502 Bad Gateway` to clients.  
**Correct Pattern**: Use official `razorpay.Client` SDK which raises structured exceptions. Catch `razorpay.errors.BadRequestError` and surface as `HTTP 400` with the exact Razorpay error message.

---

## 5. Authentication & Security Lessons

### LESSON-016: Token Key Namespacing Is Critical for Isolation
**Root Cause**: Admin token was stored under `'saas_admin_token'` in early implementation, then refactored to `'replyos_admin_token'`. Inconsistent naming caused intermittent auth failures when code paths disagreed on the key name.  
**Correct Pattern**: Establish token key names as constants in ONE place (e.g., `api.ts`), never hardcode strings in components. For ReplyOS: customer = `saas_token`, admin = `replyos_admin_token`.

### LESSON-017: Server-Side Token Scope Verification Is Not Optional
**Root Cause**: Early admin routes only checked for "any valid JWT" rather than `scopes: ["super_admin"]`. A tenant JWT could have accessed admin endpoints.  
**Correct Pattern**: Admin endpoints MUST verify `scopes: ["super_admin"]` AND `totp_verified: True` in the JWT claims. Use dedicated middleware `get_current_super_admin`.

---

## 6. Routing & Frontend Lessons

### LESSON-018: Embedded Admin Tabs in Customer Dashboard Cause User Confusion
**Root Cause**: A "Master Admin" tab was embedded inside the customer dashboard (`/dashboard`), gated by `saas_role === 'admin'`. This caused the SaaS owner to think `/` was loading the Super Admin panel.  
**Correct Pattern**: Keep admin functionality in a completely separate URL namespace (`/admin/*`). Never embed admin controls in customer-facing interfaces. Use separate routes and separate authentication contexts.

### LESSON-019: SSR-Rendered Routes and Client-Side Redirects Are Different Things
**Root Cause**: User reported routing regression based on what the browser showed. Investigation showed SSR was correct; the client-side redirect after reading localStorage was the actual control path.  
**Correct Pattern**: When diagnosing routing issues, check BOTH:
1. What the SSR HTML contains (via `curl -sL http://...`)
2. What the JS chunk does on the client side (check built chunks in `.next/static/chunks/`)

---

## 7. Recommended Future Engineering Standards

### STANDARD-001: Pre-Deployment Checklist
Before any container rebuild, verify:
- [ ] All Python imports have matching `requirements.txt` entries
- [ ] All environment variables have non-placeholder values
- [ ] Database migrations are scripted and reversible
- [ ] Optional chaining on all API response objects in frontend

### STANDARD-002: JID Handling Rules
- All phone/JID values MUST pass through `normalize_jid()` before DB write
- All outbound targets MUST be validated by the anti-ban guard before socket.sendMessage()
- Never store raw Baileys `remoteJid` without normalization

### STANDARD-003: Independent Data Loading
- Each dashboard section must fetch data independently with its own `try-catch`
- A single API failure must NEVER blank out the entire dashboard
- All state variables must have safe default values before first render

### STANDARD-004: Test Device Registry
- Primary test device: `917021886525` (registered WhatsApp, verified delivery)
- Always use this number for end-to-end delivery validation
- Never test with invented/fake numbers for delivery validation

### STANDARD-005: Documentation Before Code
- No engineering session is complete without updating project-brain docs
- Every bug fix must have a corresponding entry in `DEBUG_HISTORY.md`
- Every new feature must have a corresponding architecture doc update
- Every runtime test must produce evidence entries in `RUNTIME_VALIDATION.md`

### STANDARD-006: Container Restart Protocol
After any container restart:
1. Run `docker exec saas_nginx nginx -s reload` to refresh Nginx DNS
2. Verify all containers healthy: `docker compose ps`
3. Run health check: `curl http://localhost:8080/api/v1/health`
4. Check backend logs for startup errors: `docker compose logs backend --tail=50`

---

## 8. Host & Infrastructure Lessons

### LESSON-020: Direct Log Truncation on Running Containers Causes FD Lockups
**Root Cause**: Executing `truncate -s 0` on active container log files (`*-json.log`) directly on the host VM breaks the file descriptors managed by the Docker daemon. Because the container process continues writing to the closed/truncated descriptor, it causes the Docker daemon socket requests to block or hang, causing uvicorn and Nginx proxy threads to exhaust their pools and return 502 Bad Gateway.  
**Correct Pattern**: Always run `docker compose down && docker compose up -d` after truncating container log files, or utilize standard Docker log-driver limits (`max-size` and `max-file` in `docker-compose.yml`) to manage container log sizes automatically.

