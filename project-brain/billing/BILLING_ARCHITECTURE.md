# SaaS Billing & Plan Architecture

This document outlines the ReplyOS monetization model, database schema definitions for payment logs, webhook handlers, and quota resets.

---

## 1. Subscription Tiers & Limits

ReplyOS operates on four subscription tiers, configured inside the billing router module (`PLAN_DETAILS` in `billing.py`):

1. **Free Plan** (`free`):
   - Price: 0 INR
   - Maximum active bots: 1
   - Maximum monthly outbound messages: 500
2. **Starter Plan** (`starter`):
   - Price: 999 INR / month (represented as 99,900 Paise in Razorpay)
   - Maximum active bots: 2
   - Maximum monthly outbound messages: 5,000
3. **Pro Plan** (`pro`):
   - Price: 2,999 INR / month (represented as 299,900 Paise in Razorpay)
   - Maximum active bots: 5
   - Maximum monthly outbound messages: 50,000
4. **Agency Plan** (`agency`):
   - Price: 9,999 INR / month (represented as 999,900 Paise in Razorpay)
   - Maximum active bots: 20
   - Maximum monthly outbound messages: 1,000,000

---

## 2. Relational Schema for Payments & Subscriptions

Extended SQLAlchemy database schemas mapped in `all_models.py`:

### A. Subscriptions (`subscriptions`)
Tracks active plans, states, and payment details:
*   `stripe_subscription_id`: String (legacy support).
*   `razorpay_subscription_id`: String.
*   `razorpay_order_id`: String (matches current order signature).
*   `razorpay_payment_id`: String (last active captured payment).
*   `billing_cycle`: String (default `"monthly"`).
*   `renewal_state`: String (default `"auto"`).
*   `status`: String (`"active"`, `"expired"`, `"suspended"`, `"past_due"`).

### B. Payment Transactions (`payment_transactions`)
Records individual purchase attempts:
*   `order_id`: String (Unique Razorpay Order identifier).
*   `payment_id`: String (Captured transaction ID).
*   `signature`: String (HMAC validation signature).
*   `amount`: Integer (Paise).
*   `status`: String (`"created"`, `"captured"`, `"failed"`).
*   `plan_tier`: String.

### C. Tenant Quotas (`tenant_quotas`)
Caches active quotas to bypass heavy query joins:
*   `max_bots`: Integer.
*   `max_messages`: Integer.
*   `bots_used`: Integer.
*   `messages_used`: Integer.
*   `reset_at`: Timestamp.

---

## 3. Webhook Payment Verification Loop

When a user completes payment via Razorpay, a secure webhook is dispatched from Razorpay to `/api/v1/billing/webhook`:
1. **Signature Verification**: Validates the webhook payload using `hmac.new(webhook_secret, raw_body, sha256)`.
2. **Payload Parsing**: Extracts `notes.tenant_id` and `notes.plan_tier`.
3. **Activation**:
   - Queries or creates the tenant's `Subscription` record.
   - Sets status to `"active"`.
   - Extends the `current_period_end` date by 30 days.
   - Refreshes matching limits in `tenant_quotas`.

---

## 4. Quota Reset Mechanism

A periodic background worker task runs to reset counts:
*   Every tenant has a `reset_at` date in the `tenant_quotas` table.
*   When `now > reset_at`, the worker resets `messages_used` to `0` and sets `reset_at` to `now + 30 days`.
