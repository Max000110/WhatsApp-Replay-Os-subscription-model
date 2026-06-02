# Subscription Engine Forensics — ReplyOS
**Date**: 2026-05-29 | **Prepared by**: Principal Multi-Tenant Systems Architect

---

## 1. Plan Tier Specifications

The subscription engine handles 4 subscription levels. The limits are defined in `PLAN_DETAILS` in `backend/app/routers/billing.py`:

| Plan Tier | Monthly Price (INR) | Max Chatbots | Max Messages / Month |
|:---|:---|:---|:---|
| **Free** | ₹0 | 1 chatbot | 500 messages |
| **Starter** | ₹999 | 2 chatbots | 5,000 messages |
| **Pro** | ₹2,999 | 5 chatbots | 50,000 messages |
| **Agency** | ₹9,999 | 20 chatbots | 1,000,000 messages |

---

## 2. Forensic Analysis of Subscription Flow

### 2.1 Customer-Initiated Subscription (Razorpay checkout)
* **Step 1**: Frontend triggers `POST /api/v1/billing/create-order` with the target `plan_tier`.
* **Step 2**: Backend calls the official `razorpay.Client` to register an order with the appropriate INR price, saving a `PaymentTransaction` row in the DB with status `created`.
* **Step 3**: The user completes payment in the browser.
* **Step 4**: The frontend sends payment proofs (`razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`) to `POST /api/v1/billing/verify-payment`.
* **Step 5**: Backend verifies signature using `client.utility.verify_payment_signature`. Upon success, the `subscriptions` row is updated with the new plan limits and `current_period_end` set to 30 days in the future.

### 2.2 Super Admin Quota Override
* **Endpoint**: `POST /api/v1/admin/tenants/{id}/quotas`
* **Flow**: Overrides default plan tier limits by directly editing custom fields `max_bots` and `max_messages_per_month` in the DB.
* **Verification**: Testing shows that custom overrides take precedence over the generic defaults of the tenant's current plan tier.

### 2.3 System Access Guards (Quota Enforcement)
Outbound message sends check two primary limits:
1. **Subscription Status check** (`is_subscription_active`): Asserts that the subscription row `status == 'active'` and `current_period_end` has not passed.
2. **Monthly Message Limit check** (`has_exceeded_message_limit`): Queries DB to verify total messages sent by this tenant during the current billing cycle is less than `max_messages_per_month`.

---

## 3. Resolution of "Invalid Subscription Tier" Error

* **Root Cause**: During administrative changes, the admin dashboard frontend had a plan selector option `"enterprise"`. However, the backend plan enum validator only supported the keys: `["free", "starter", "pro", "agency"]`. Selecting "enterprise" returned `422 Unprocessable Entity` or threw a validation exception.
* **Resolution**: The frontend dropdown values in `frontend/src/app/admin/page.tsx` were updated to align with the backend's allowed enum identifiers (`free`, `starter`, `pro`, `agency`).
* **Verification**: Succeeded in cycling through all 4 supported tiers via administrative change requests without experiencing errors.
