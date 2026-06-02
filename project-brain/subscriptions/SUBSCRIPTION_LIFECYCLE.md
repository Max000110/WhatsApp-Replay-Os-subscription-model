# Subscription Lifecycle — ReplyOS
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## Plan Hierarchy

| Tier | Monthly Messages | WhatsApp Sessions | Active Bots | Price (INR/mo) |
|---|---|---|---|---|
| `free` | 500 | 1 | 1 | ₹0 |
| `starter` | 5,000 | 2 | 2 | ₹999 |
| `pro` | 50,000 | 5 | 5 | ₹2,999 |
| `agency` | 1,000,000 | 20 | 20 | ₹9,999 |

Razorpay amounts (paise): Starter = 99900, Pro = 299900, Agency = 999900

---

## Subscription States

| Status | Outbound Sends | AI Replies | Campaigns | Dashboard |
|---|---|---|---|---|
| `active` | ✅ Allowed | ✅ Allowed | ✅ Allowed | ✅ Full access |
| `expired` | ❌ `HTTP 402` | ❌ Silently dropped | ❌ Paused | ⚠️ Locked overlay |
| `suspended` | ❌ `HTTP 402` | ❌ Silently dropped | ❌ Paused | ⚠️ Locked overlay |
| `terminated` | ❌ All routes `403` | ❌ Blocked | ❌ Blocked | ❌ Access denied |

---

## Enforcement Points

### 1. API Middleware (`get_current_user`)
- After JWT validation, checks `tenant.status`
- `suspended` or `terminated` → immediate `403 Forbidden` on ALL routes

### 2. Outbound Message Guard (`is_subscription_active()`)
- Called in `chats.py` before every manual send
- Called in `sessions.py` AI pipeline before LLM generation
- Returns `False` → raises `HTTP 402 Payment Required`

### 3. Monthly Message Limit Check
- `has_exceeded_message_limit()` called in AI pipeline
- Counts `outbound` messages in current billing period
- Exceeds limit → AI generation skipped (silent drop)

### 4. Celery Worker Campaign Guard
- Each recipient dispatch in `run_campaign_broadcast_task` calls quota check
- Subscription inactive → task aborts, campaign marked `failed`

### 5. WebSocket Expiry Notification
- On subscription expiry detection → publish `subscription_expired` event to tenant channel
- Frontend receives → displays full-screen locked overlay

---

## Billing Flow

### Upgrade Flow
```
Frontend "Upgrade" button
  → POST /api/v1/billing/create-order {plan_tier}
  → Backend creates Razorpay order
  → Returns {razorpay_order_id, amount, currency, razorpay_key_id}
  → Frontend loads checkout.js
  → User completes payment
  → Razorpay callback {payment_id, order_id, signature}
  → POST /api/v1/billing/verify-payment
  → Backend verifies HMAC-SHA256 signature
  → Success → Update subscription {plan_tier, status: active, period_end: +30 days}
  → Reset monthly usage counter
  → WebSocket broadcast → frontend unlocks
```

### Webhook Flow
```
Razorpay server → POST /api/v1/payments/webhook
  → Verify webhook signature (RAZORPAY_WEBHOOK_SECRET)
  → Check idempotency (tx.status == "captured" → skip)
  → Event: payment.captured → Update tx to "captured"
  → Event: order.paid → Extend subscription period
  → Reset usage quota
```

---

## Automated Subscription Management (Celery)

### `check_subscription_expiry_task` (runs on schedule)
- Scans all active tenants
- If `current_period_end < now()` → set status to `expired`
- Sends `subscription_expired` WebSocket notification

### `check_graceful_terminations_task` (runs on schedule)
- Checks tenants in `terminating` state with expired grace period
- Executes Mode 2 termination: deactivates users, severs WhatsApp connections, manages file purges

### `check_subscription_reminders_task`
- Sends renewal reminder messages to tenants approaching expiry

---

## Current Mode
```
PAYMENT_MODE=test
RAZORPAY_KEY_ID=rzp_test_Suof5OJrcLYP9M
```
**⚠️ WARNING**: Test mode active. Real transactions not charged. Must migrate to `rzp_live_*` keys for production revenue.
