# ReplyOS — Subscription & Billing Engine Architecture

This document describes the billing tiers, API quota enforcement rules, Razorpay webhook validation, and automated grace-period execution.

---

## 1. Plan Tiers & Resource Quotas

The database table `subscriptions` enforces resource restrictions based on plan tiers:

| Plan Tier | Monthly Message Cap | Active Bot Cap | Support Level | Reconnection Retries |
| :--- | :--- | :--- | :--- | :--- |
| **free** | 500 | 1 | Basic | 3 |
| **starter** | 5,000 | 5 | Standard | 5 |
| **pro** | 50,000 | 10 | Premium | 10 |
| **agency** | Unlimited | Unlimited | Dedicated | Unlimited |

---

## 2. API Quota Enforcement (Billing Controls)

Before processing message callbacks or generating AI chatbot replies, the backend verifies subscription states:
1. **Verification Middleware**: The core function `is_subscription_active(tenant_id, db)` queries the `subscriptions` table.
2. **Interception**: If `subscription.status != "active"`, the system:
   - Blocks outbound campaign sends.
   - Short-circuits inbound AI reply generation (chatbot ignores the message or replies with: "This account has reached its plan limit.").
3. **Usage Incrementing**: Every successful outbound message increments the usage metric:
   ```python
   # Increments current month's usage count
   db.execute(
       text("UPDATE usage_metrics SET message_count = message_count + 1 WHERE tenant_id = :id AND billing_period = :period"),
       {"id": tenant_id, "period": current_period}
   )
   ```

---

## 3. Razorpay Subscription & Webhook Pipeline

* **Checkout Hook**: The Next.js frontend redirects clients to the Razorpay hosted payment page.
* **Webhook Ingestion**: Post-payment, Razorpay dispatches events (`subscription.activated`, `payment.captured`) to the backend endpoint `/api/v1/payments/webhook`.
* **HMAC Signature Check**: Every payload signature is verified:
  ```python
  # Confirms payload source using the SHA-256 webhook secret
  expected_sig = hmac.new(webhook_secret.encode(), payload_body, hashlib.sha256).hexdigest()
  if not hmac.compare_digest(expected_sig, incoming_sig):
      raise HTTPException(status_code=400, detail="Invalid signature.")
  ```
* **Idempotency Check**: Updates are committed only if `tx.status == "captured"` is verified, preventing double-processing on delivery retries.

---

## 4. Automated Grace Period Suspension Daemon

The Celery scheduler executes a periodic worker task `check_graceful_terminations_task` to enforce billing cycles:
1. **Suspension Check**: Queries subscriptions past their `current_period_end` date without successful renewals.
2. **Grace Timer**: Sets tenant status to `PENDING_TERMINATION` and initiates a 24-hour countdown.
3. **Enforcement Execution**: Upon grace timer expiration:
   - Sets tenant status to `suspended`.
   - Modifies user tables: `is_active = False` for all linked members.
   - Severing connections: Disconnects the WhatsApp companion engine socket dynamically.
