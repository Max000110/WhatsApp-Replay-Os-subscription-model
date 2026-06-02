# Super Admin Authentication & Session Isolation Architecture

This document specifies the session boundary limits, token caching, credential rotation mechanisms, and rate limits safeguarding the Super Admin Control Plane on the ReplyOS Multi-Tenant WhatsApp AI SaaS platform.

---

## 1. Authentication Pipelines Isolation

To prevent privilege escalation and lateral movement, the customer portal and the administrative plane utilize 100% isolated session paths, credentials, and token structures:

```
                  Client Login Request (Browser)
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
      Customer Portal                        Super Admin
   [http://.../login]                    [http://.../admin/login]
            │                                     │
   API: POST /auth/login                 API: POST /admin/auth/login
            │                                     │
   Role Guard: role != 'admin'           Role Guard: role == 'admin'
            │                                     │
   Access Token: saas_token              Access Token: replyos_admin_token
            │                                     │
   Workspace: /dashboard                 Workspace: /admin
```

---

## 2. Hardening Enforcements & Guards

### 2.1 Role Boundaries (FIX-011)
* Regular tenant users (e.g. `owner`, `member`) are explicitly rejected by the admin API `/api/v1/admin/auth/login` with `401 Unauthorized`.
* Super Administrators (accounts with `role == "admin"`) are explicitly rejected by the customer login API `/api/v1/auth/login` with `403 Forbidden`.

### 2.2 Token Separation & Caching
* **Tenant Session**: Stored in browser `localStorage` as `saas_token`. Authorized requests contain `Authorization: Bearer <saas_token>`. Mapped to tenant scopes.
* **Super Admin Session**: Stored in browser `localStorage` as `replyos_admin_token`. Authorized requests contain `Authorization: Bearer <replyos_admin_token>`. Verified for scope `["super_admin"]` and TOTP status.

---

## 3. Brute-Force Rate Limiting (Redis-Backed)

The Super Admin API enforces brute-force prevention using Redis keys:
1. **Attempts Tracker**: Each failed login attempt on `admin/auth/login` increments `admin_failed_login:{email}`. Expire time is set to 1 hour.
2. **Lockout Trigger**: Upon reaching **5 failed attempts**, the system generates a 15-minute lock key: `admin_lockout:{email}`.
3. **Lockout Interception**: Subsequent requests are short-circuited and immediately return `429 Too Many Requests` without checking credentials, shielding the Postgres database from CPU hash depletion.

---

## 4. Multi-Factor TOTP & Credentials Rotation

### 4.1 Credentials Rotation (First-Time Login)
* Admin accounts initialized with temporary passwords have the database flag `must_change_password` set to `True`.
* Initial authentication returns a restricted payload (`must_change_password: True`) and returns a temporary token lacking full `super_admin` scopes.
* The administrator is forced to execute `POST /admin/auth/password-change` to register a strong permanent passcode, which updates the hash in Postgres and clears `must_change_password`.

### 4.2 Time-Based One-Time Password (TOTP)
* Optional TOTP MFA is supported using standard SHA-1 6-digit verification codes.
* Fully authenticated access requires both email/password validation and a subsequent drift-tolerant TOTP challenge verification (`POST /admin/auth/totp/verify`).
