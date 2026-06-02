# Authentication Boundary Audit — ReplyOS
**Date**: 2026-05-29 | **Prepared by**: Principal FastAPI Architect

---

## 1. Cryptographic Configuration

ReplyOS authentication enforces high-security cryptography standards:
* **Algorithm**: HMAC-SHA256 for signing JSON Web Tokens (JWT).
* **Work Factor**: bcrypt work factor of 12 for password hashing, defending against offline brute-force attacks.
* **Token Lifetimes**:
  * Tenant user tokens: 24 Hours.
  * Super Admin tokens: 2 Hours.

---

## 2. Token Layout & Claims Structure

Tenant tokens and Super Admin tokens are structurally isolated, preventing token substitution or privilege escalation:

### 2.1 Customer/Tenant JWT Claims
```json
{
  "sub": "user_id",
  "exp": 1780677279,
  "tenant_id": "eee18224-de89-41c3-9fb3-e4fdebb532eb"
}
```
*Note: Tenant tokens do NOT contain admin-related claims or scopes.*

### 2.2 Super Admin JWT Claims
```json
{
  "sub": "admin_user_id",
  "exp": 1780079686,
  "scopes": ["super_admin"],
  "totp_verified": true
}
```
*Note: Contains the `scopes` claim set to `["super_admin"]` and the `totp_verified` flag.*

---

## 3. Boundary & Isolation Verification

### 3.1 Portal Isolation (Cross-Login Rejection)
* **Safeguard**: The customer portal login endpoint `/auth/login` checks the role of the user. If the user has `role == "admin"`, it returns a `403 Forbidden` response.
* **Verification Proof**: Running a POST to `/api/v1/auth/login` using super admin credentials (`admin@replyos.com`) yields:
  ```http
  HTTP/1.1 403 Forbidden
  {"detail": "Super Administrators are not permitted to log in via the customer portal."}
  ```

### 3.2 Tenant Context Isolation
* **Access Control**: All customer APIs require the `get_current_tenant_id` dependency, which extracts the `tenant_id` from the JWT token.
* **Database Isolation**: All SQL queries inside tenant routers (e.g. `chats.py`, `bots.py`, `campaigns.py`) filter records strictly by `tenant_id == active_tenant_id`. It is mathematically impossible for a tenant to view or modify another tenant's resources.

### 3.3 Super Admin Isolation & Guards
* **Access Control**: All routes inside `routers/admin.py` are guarded by the `get_current_super_admin` dependency.
* **Required Checks**:
  1. Decodes JWT token and asserts user role is `"admin"`.
  2. Asserts `must_change_password` flag is `False`.
  3. Asserts `totp_verified` claim is `True` if 2FA is active.
* **Bypass Attempt Proof**: Attempting to query `/api/v1/admin/tenants` using a customer tenant JWT token yields:
  ```http
  HTTP/1.1 403 Forbidden
  {"detail": "Requires Super Admin permissions."}
  ```

### 3.4 Web Interface Isolation
* **Dashboard Cleanliness**: The frontend page `frontend/src/app/dashboard/page.tsx` contains no administrative sidebar elements, gauges, or states.
* **Control Plane Isolation**: Admin operations are exclusively rendered inside `frontend/src/app/admin/page.tsx`, which uses local storage key `replyos_admin_token` instead of `saas_token`.
