# Billing Architecture — ReplyOS
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## Plan Pricing (INR)

| Plan | Monthly Limit | Sessions | Bots | Amount (paise) |
|---|---|---|---|---|
| free | 500 messages | 1 | 1 | 0 |
| starter | 5,000 messages | 2 | 2 | 99,900 |
| pro | 50,000 messages | 5 | 5 | 299,900 |
| agency | 1,000,000 messages | 20 | 20 | 999,900 |

---

## Order Creation Pipeline

```
"Upgrade Plan" click
        │
        ▼
POST /api/v1/billing/create-order {plan_tier}
        │
        ▼
FastAPI queries PLAN_DETAILS pricing config
        │
        ▼
razorpay.Client.order.create({amount, currency: "INR", payment_capture: 1})
        │
        ▼
INSERT payment_transactions (status: "created")
        │
        ▼
Return {razorpay_order_id, amount, razorpay_key_id}
        │
        ▼
Frontend loads checkout.js with order_id
        │
        ▼
User completes payment → Razorpay callback
```

---

## Signature Verification Loop

```
Razorpay callback: {razorpay_payment_id, razorpay_order_id, razorpay_signature}
        │
        ▼
POST /api/v1/billing/verify-payment
        │
        ▼
client.utility.verify_payment_signature(params)
        │
  Signature valid?
  ├─ No  → HTTP 400 signature mismatch
  │
  └─ Yes → UPDATE payment_transactions SET status="captured"
           UPDATE subscriptions SET plan_tier, status="active", period_end=now()+30d
           Reset monthly usage counter
           WebSocket broadcast: subscription_updated
```

---

## Webhook Pipeline

```
Razorpay server → POST /api/v1/payments/webhook
        │
        ▼
Parse raw body (for HMAC) + verify signature
        │
        ▼
Idempotency check: if tx.status == "captured" → skip (already processed)
        │
        ▼
Event: payment.captured / order.paid
  → Update tx to "captured"
  → Extend subscription period
  → Reset quota
```

---

## Database Tables

### `payment_transactions`
```sql
id          UUID PRIMARY KEY
tenant_id   UUID REFERENCES tenants
order_id    VARCHAR   -- razorpay order ID
payment_id  VARCHAR   -- razorpay payment ID (set after capture)
signature   VARCHAR   -- HMAC signature
amount      INTEGER   -- paise
status      VARCHAR   -- created → captured
plan_tier   VARCHAR
created_at  TIMESTAMP
updated_at  TIMESTAMP
```

### `subscriptions` (on `tenants`)
```sql
plan_tier           VARCHAR  -- free/starter/pro/agency
status              VARCHAR  -- active/expired/suspended/terminated
current_period_end  TIMESTAMP
monthly_message_count INTEGER
max_monthly_messages  INTEGER
max_sessions          INTEGER
max_bots              INTEGER
```

---

## Security Controls

- `RAZORPAY_KEY_SECRET` — backend only, never exposed to frontend
- Public key provisioned dynamically from API response (not hardcoded in frontend build)
- Webhook HMAC verified using `RAZORPAY_WEBHOOK_SECRET` before any processing
- Idempotency: duplicate payment events ignored if already `captured`

---

## Known Issues

1. **INC-011 OPEN**: `PAYMENT_MODE=test` active — no real money collected
2. Webhook endpoint not yet registered in Razorpay production dashboard
3. Production keys (`rzp_live_*`) not yet provisioned
