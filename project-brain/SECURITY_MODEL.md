# Security Model — ReplyOS
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## 1. Authentication Layers

### Customer Auth (Tenant Users)
- JWT via `POST /api/v1/auth/login` with email + password
- Token stored in `localStorage['saas_token']`
- Expiry: 2 hours
- Explicit Guard: Blocks user accounts with `role == "admin"`. Any attempt to log in to the customer portal using Super Admin credentials returns `403 Forbidden`.
- Client-Side UI Isolation: The customer dashboard (`frontend/src/app/dashboard/page.tsx`) contains 0 administrative markup elements, states, or queries. All master admin panels are strictly isolated to `/admin`.
- All protected routes use `Depends(get_current_user)` middleware
- Middleware checks: JWT valid → tenant active → user active

### Super Admin Auth (SaaS Owner Only)
- 3-phase login flow:
  1. `POST /api/v1/admin/auth/login` — credential validation
  2. Forced password rotation if `must_change_password = True`
  3. TOTP 2FA if `totp_enabled = True`
- Final JWT contains `scopes: ["super_admin"]` + `totp_verified: True`
- Token stored in `localStorage['replyos_admin_token']`
- All admin routes use `Depends(get_current_super_admin)` middleware
- Brute-force protection: Redis counter `admin_fail:{email}`, lockout after N failures

---

## 2. Token Isolation Model

| Context | localStorage Key | Token Scope | Auth Middleware |
|---|---|---|---|
| Customer | `saas_token` | User JWT | `get_current_user` |
| Super Admin | `replyos_admin_token` | `scopes: ["super_admin"]` | `get_current_super_admin` |

The `api.ts::getToken()` function selects the correct key based on `window.location.pathname.startsWith('/admin')`. This prevents cross-contamination between customer and admin sessions.

---

## 3. Cryptographic Token Specifications (Native JWT)

Following the decommissioning of Google OAuth, the platform enforces a pure self-hosted JSON Web Token (JWT) signature architecture.
- **Signing Algorithm**: HMAC-SHA256 (`HS256`)
- **Key Derivation**: Cryptographically signed using standard HMAC key derived from `JWT_SECRET` environment parameter.
- **Expiration Policy**: Tokens expire dynamically in `60` minutes (configured via `ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Claim Structure**:
  - `sub`: Stores the immutable unique identifier (`user.id`) of the authenticated user.
  - `exp`: Unix timestamp indicating token expiration time.
- **Frontend Storage & Binding**:
  - Customer Portal: Stored securely in `localStorage['saas_token']`.
  - Administrative Portal: Stored securely in `localStorage['replyos_admin_token']`.
  - Attached to all outgoing API queries via `Authorization: Bearer <token>` request header.

---

## 4. Brute Force Protection

### Customer Login
- Redis sliding window rate limiter on all public routes
- Key pattern: `rate_limit:{ip}:{minute}`
- After threshold: Redis key `ip_ban:{ip}` with TTL
- Progressive ban durations

### Admin Login
- Failed attempt counter: `admin_fail:{email}` in Redis
- Lockout threshold enforced with TTL-based expiry
- Blocked accounts return `403 Forbidden` immediately

---

## 5. Payment Security

### Order Creation
- HMAC-SHA256 verification on all payment callbacks
- `RAZORPAY_KEY_SECRET` never exposed to frontend or Next.js container
- Public key provisioned dynamically from `/billing/create-order` response

### Webhook Verification
```python
client.utility.verify_webhook_signature(
    raw_body.decode("utf-8"),
    signature,
    settings.RAZORPAY_WEBHOOK_SECRET
)
```

### Idempotency
- Check `tx.status == "captured"` before processing any webhook event
- Prevents duplicate quota credits from Razorpay retries

---

## 6. WhatsApp Session Encryption

- Baileys auth credentials (multi-device keys) stored in PostgreSQL
- Encrypted at rest using AES-256-GCM
- Key derived from `ENCRYPTION_KEY` environment variable
- Legacy unencrypted records migrated on first read: `"Legacy unencrypted data: read directly and mark for encryption on next write"`

---

## 7. Nginx Security Headers

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self' ..." always;
```

### Timeout Hardening (Slowloris Protection)
```nginx
client_body_timeout 10s;
client_header_timeout 10s;
keepalive_timeout 15s;
send_timeout 10s;
client_max_body_size 10M;
```

---

## 8. TOTP 2FA Architecture (Admin Only)

- Secret: 20-byte cryptographically secure random key, Base32 encoded
- URI: `otpauth://totp/ReplyOS-Admin:[email]?secret=[secret]&issuer=ReplyOS`
- Drift compensation: ±30 seconds (1 time-step offset allowed)
- Recovery: 8 single-use 8-character hexadecimal codes
- Recovery code consumption: marks as used in DB, cannot be reused

### Endpoints
| Endpoint | Purpose |
|---|---|
| `POST /admin/auth/totp/setup` | Generate secret + otpauth URI |
| `POST /admin/auth/totp/enable` | Validate code, activate 2FA, return recovery codes |
| `POST /admin/auth/totp/verify` | Verify during login, issue final JWT |

---

## 9. Session Revocation

- Admin session revocation via `POST /admin/auth/revoke-session`
- JWT signature blacklisted in Redis with 7-day TTL
- All subsequent requests with that token return `401 Unauthorized` immediately
- Customer logout clears `localStorage` and redirects to `/login`

---

## 10. Audit Trail

All Super Admin actions are permanently logged in `audit_logs` PostgreSQL table:
- Timestamp
- Administrator email
- Target tenant ID/subdomain
- Resource modified
- JSON state trace (before/after)
- Cannot be deleted by normal admin operations
