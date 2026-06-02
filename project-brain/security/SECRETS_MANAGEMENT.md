# Secrets Management & Verification

## 1. Secrets Propagation Strategy
* **Host environment mapping**: Secrets are loaded on startup from the host `.env` file and passed into the environment context of the corresponding container services in `docker-compose.yml`.
* **Exclusion from VCS**: `.env` is kept strictly within `.gitignore` to prevent committing live production keys to version control.
* **SDK Credentials Binding**: Secrets are read exclusively at runtime from container environment keys to initialize `razorpay.Client(auth=(key_id, key_secret))` on backend and worker services.

## 2. Active Credentials Configuration
* **Active key ID**: `rzp_test_Suof5OJrcLYP9M` (starts with `rzp_test_`, indicating Test Mode environment).
* **Payment Mode switch**: `PAYMENT_MODE=test`
* **Verified client public key**: `NEXT_PUBLIC_RAZORPAY_KEY` is synced to prevent mismatch.

## 3. Webhook Cryptographic Integrity
* Webhook payloads are verified using standard HMAC-SHA256 digests against `RAZORPAY_WEBHOOK_SECRET` before updating database transaction status or user plan limits.
