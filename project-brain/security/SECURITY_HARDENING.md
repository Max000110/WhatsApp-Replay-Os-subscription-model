# Security Hardening & Isolation

## 1. Credentials Isolation & API Security
* **No Client Secrets Leakage**: `RAZORPAY_KEY_SECRET` is kept strictly on the backend (`saas_backend`) and Celery background workers (`saas_worker`). It is never exposed, mounted, or sent to the frontend Next.js container or client browser.
* **Dynamic Frontend Key Provisioning**: The public key `NEXT_PUBLIC_RAZORPAY_KEY` (or `razorpay_key_id`) is retrieved dynamically from the `/billing/create-order` response to avoid hardcoding it in the static frontend build.
* **Authentication Barrier**: All billing and order creation routes are guarded by strict JWT validation mapping to active, un-suspended Tenant and User database rows.

## 2. Payment Spoofing & Replay Attack Protections
* **Cryptographic Signature Verification**: The backend strictly validates payment signatures on `/billing/verify-payment` using the official SDK signature utility:
  ```python
  client.utility.verify_payment_signature({
      'razorpay_order_id': order_id,
      'razorpay_payment_id': payment_id,
      'razorpay_signature': signature
  })
  ```
* **Webhook HMAC Signature Verification**: Both the `/payments/webhook` and backup `/billing/webhook` endpoints parse raw request bodies and verify them using HMAC-SHA256 with the private `RAZORPAY_WEBHOOK_SECRET`:
  ```python
  client.utility.verify_webhook_signature(
      raw_body.decode("utf-8"),
      signature,
      settings.RAZORPAY_WEBHOOK_SECRET
  )
  ```
  This guarantees that all upgrade and quota update operations originate exclusively from verified Razorpay servers.

## 3. Webhook Idempotency & Replay Protection
* **Captured Filter**: In `process_webhook_payload`, we check if the transaction is already marked as `captured` before applying DB updates:
  ```python
  if order_id:
      tx = db.query(PaymentTransaction).filter(PaymentTransaction.order_id == order_id).first()
      if tx and tx.status == "captured":
          return
  ```
  This blocks duplicate payload processing (e.g., if Razorpay retries webhook deliveries or sends redundant `order.paid` and `payment.captured` events).

## 4. Nginx Gateway Security Hardening
* **Security Headers**: Injected global headers:
  - `Strict-Transport-Security "max-age=31536000; includeSubDomains"`
  - `X-Frame-Options "SAMEORIGIN"`
  - `X-Content-Type-Options "nosniff"`
  - `Referrer-Policy "strict-origin-when-cross-origin"`
  - `Content-Security-Policy` limits resource loading to secure, trusted origins.
* **Slowloris & Timeout Mitigations**:
  - `client_body_timeout 10s`, `client_header_timeout 10s`, `keepalive_timeout 15s`, `send_timeout 10s`.
  - Body sizes are restricted via `client_max_body_size 10M`.

## 5. Storage State Encryption
* **Baileys Credentials Encryption**: Node.js WhatsApp Engine uses AES-256-GCM to encrypt all multi-device sessions and database tokens, preventing unauthorized credential theft.
