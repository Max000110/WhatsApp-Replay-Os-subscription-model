# Razorpay Production Integration & Verification

This guide outlines the production deployment setup, keys, APIs, webhook configurations, and verification routines for Razorpay.

---

## 1. Production API Keys Configuration

Verify these parameters inside `/home/ubuntu/whatsapp-ai-saas/.env`:
*   `RAZORPAY_KEY_ID`: Your production key ID (starts with `rzp_live_`).
*   `RAZORPAY_KEY_SECRET`: Your production key secret.
*   `RAZORPAY_WEBHOOK_SECRET`: Secure webhook verification key.

---

## 2. Order Creation Flow

When a user triggers an upgrade in the UI:
1.  **FastAPI Endpoint**: `POST /api/v1/billing/create-order`
2.  **Request Body**: `{ "plan_tier": "pro" }`
3.  **Razorpay Order Call**: FastAPI calls `POST https://api.razorpay.com/v1/orders` using basic auth:
    ```python
    auth = (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    payload = {
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": f"receipt_{str(tenant_id)[:20]}",
        "notes": {
            "tenant_id": str(tenant_id),
            "plan_tier": plan_tier
        }
    }
    ```
4.  **API Response**: Returns `razorpay_order_id`, `amount`, and `razorpay_key_id` to the frontend dashboard.

---

## 3. Frontend Razorpay Checkout Modal

On the Next.js client, the Razorpay payment modal is opened using the returned parameters:
```javascript
const options = {
  key: data.razorpay_key_id,
  amount: data.amount,
  currency: data.currency,
  name: "ReplyOS WA-SaaS",
  description: `Upgrade to ${planTier.toUpperCase()} Plan`,
  order_id: data.razorpay_order_id,
  handler: async function (response) {
    // Fired upon payment capture success
    const verification = await api.billing.verifyPayment({
      razorpay_order_id: response.razorpay_order_id,
      razorpay_payment_id: response.razorpay_payment_id,
      razorpay_signature: response.razorpay_signature,
      plan_tier: planTier
    });
    alert("Payment verified successfully! Your account has been upgraded.");
  },
  prefill: {
    email: userEmail
  },
  theme: {
    color: "#6D28D9" // ReplyOS Deep Violet theme accent
  }
};

const rzp = new window.Razorpay(options);
rzp.open();
```

---

## 4. Webhook & Signature Verification

FastAPI validates all webhook signals to prevent spoofing:

### A. Webhook Signature Validation Formula
```python
import hmac
import hashlib

def verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    generated_signature = hmac.new(
        secret.encode(), 
        raw_body, 
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(generated_signature, signature_header)
```

### B. Verification Flow
1.  Dispatched payloads contain `event` parameter.
2.  If the event matches `payment.captured` or `order.paid`, we extract metadata:
    - `notes.tenant_id`: Scopes the targeted organization database workspace.
    - `notes.plan_tier`: Mapped subscription targets.
3.  The database `Subscription` record is updated:
    - Status set to `"active"`.
    - Expiration dates pushed out 30 days.
    - Limit counts refreshed.
4.  Saves details in `payment_transactions` and `billing_history` tables.
