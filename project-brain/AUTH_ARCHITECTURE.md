# ReplyOS — Authentication & Session Architecture

This document details the token schemas, cryptography parameters, and session isolation standards securing ReplyOS.

---

## 1. Cryptography Standards

* **Password Hashing**: Application passcodes are encrypted using **bcrypt** with a work factor of **12** (managed via Python's `passlib` library with `bcrypt` backend).
* **Token Signatures**: Session tokens are generated as **JSON Web Tokens (JWT)** signed via **HMAC-SHA256** using a cryptographically strong host-level secret `JWT_SECRET`.
* **Session Lifetime**: 
  * Tenant user tokens: 24 Hours.
  * Super Admin tokens: 2 Hours.

---

## 2. Session Isolation & Token Designations

To guarantee strict tenant isolation, sessions are stored in distinct `localStorage` keys and validated against explicit roles:

| Session Portal | Browser Storage Key | Target API Endpoint | Allowed Roles | Scope Claims |
| :--- | :--- | :--- | :--- | :--- |
| **Customer Tenant** | `saas_token` | `/api/v1/auth/login` | `owner`, `member` | `{"sub": user_id, "scopes": ["tenant"]}` |
| **Super Admin** | `replyos_admin_token` | `/api/v1/admin/auth/login` | `admin` | `{"sub": user_id, "scopes": ["super_admin"], "totp_verified": true}` |

---

## 3. End-to-End Authentication Flows

### 3.1 Tenant Login Flow
1. User enters email and password at `http://...:8080/login`.
2. Browser sends POST payload to `/api/v1/auth/login`.
3. Backend retrieves user record. If `user.role == "admin"`, request is blocked with `403 Forbidden` (leak safeguard).
4. Password verified against `user.password_hash`. If correct, updates `user.last_login` and returns JWT containing user ID and tenant ID.
5. Frontend sets local token key `saas_token` and redirects browser to `/dashboard`.

### 3.2 Super Admin Login Flow
1. Admin inputs email/password at `http://...:8080/admin/login`.
2. Browser sends POST payload to `/api/v1/admin/auth/login`.
3. Backend asserts `user.role == "admin"`. Regular roles are rejected with `401 Unauthorized`.
4. If `user.must_change_password` is active (first bootstrap login), backend returns:
   ```json
   {"must_change_password": true, "access_token": "temp_token"}
   ```
   Frontend displays password reset console. Successful change commits new hash and removes flag.
5. If `user.totp_enabled` is active, backend returns:
   ```json
   {"totp_enabled": true, "access_token": "temp_token"}
   ```
   Frontend displays 2FA challenge code page.
6. Once fully authenticated, backend issues `replyos_admin_token` with claims `{"scopes": ["super_admin"], "totp_verified": true}`.
7. Frontend sets `replyos_admin_token` and redirects browser to `/admin`.

---

## 4. CORS & Security Gateways

* **CORS Settings**: Nginx reverse proxy and FastAPI middleware restrict cross-origin access to a whitelist of allowed production domains (`144.24.126.153:8080`, `localhost:8080`, and dev ports).
* **Nginx Security Headers**: Injected on all proxy responses:
  * `Strict-Transport-Security`: Enforces TLS access.
  * `X-Frame-Options: SAMEORIGIN`: Safeguards against clickjacking.
  * `X-Content-Type-Options: nosniff`: Prevents mime sniffing.
  * `Content-Security-Policy`: Restricts scripts and styles to trusted origins.
