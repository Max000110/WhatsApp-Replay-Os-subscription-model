# Master Admin Panel Access & Endpoint Specifications

This document outlines the access rules, authentication states, and server endpoints for the ReplyOS Master Super Admin Control Plane.

---

## 1. Role-Based Access Control (RBAC) & Boundaries

The Super Admin Control Plane is completely isolated from all standard tenant dashboards. It utilizes a separate authentication system to guarantee that no normal tenant admin or customer can discover, enumerate, or access these routes.

### Client-Side Boundary
* **Isolated Page Route**: Served at `/admin` (Dashboard) and `/admin/login` (Authentication).
* **Sidebar Isolation**: The dashboard sidebar is reserved exclusively for the Super Admin panel. Standard tenant users cannot access or view this workspace.
* **Distinct Token Storage**: Admin sessions store their token in local storage under the isolated key `'replyos_admin_token'`. This prevents session crosstalk with standard client tokens (`'saas_token'`).

### Server-Side Boundary
* **FastAPI Router**: Mounts endpoints under `backend/app/routers/admin.py` with prefix `/api/v1/admin`.
* **Restricted Auth Middleware**: Guards all general admin routes via `Depends(get_current_super_admin)`.
* **Scope Claims Check**: Asserts that the incoming Bearer JWT includes the strict scope claim: `scopes: ["super_admin"]` and `totp_verified: True`. Normal tenant tokens are instantly rejected with a `401 Unauthorized` block.

---

## 2. Server Authentication States

Access to the admin control plane is granted through the following authentication pipeline:

```text
Login Request (POST /admin/auth/login)
       |
  Credentials OK?  ---> No  ---> Increment fails, block/lockout
       |
  Yes -> must_change_password? ---> Yes ---> return status:force_password_change (Temp Token)
       |
       No -> totp_enabled?     ---> Yes ---> return status:totp_required (Temp Token)
       |
       No ---> Success! Issue final admin token (scopes: ["super_admin"], totp_verified: True)
```

1. **Forced Password Rotation**:
   * Initial bootstrap user (`admin@replyos.com`) is seeded with `must_change_password = True`.
   * Access to general endpoints is fully blocked until the operator rotates their credentials via `POST /admin/auth/password-change` using the temporary token.

2. **drift-Aware TOTP 2FA Verification**:
   * If TOTP is enabled on the account, logins trigger a `totp_required` response with a temporary token.
   * Access is cleared only after submitting a valid 6-digit authenticator code or single-use recovery code to `/admin/auth/totp/verify`.

3. **Session Revocation**:
   * Super Admins can revoke their active session instantly via `/admin/auth/revoke-session`.
   * This blacklists their JWT signature in Redis for 7 days, causing subsequent requests to be instantly blocked.

---

## 3. Server Endpoints Registry (`backend/app/routers/admin.py`)

| REST Endpoint | HTTP Method | Guard Middleware | Request Body | Description |
| :--- | :--- | :--- | :--- | :--- |
| `/admin/auth/login` | `POST` | *None* | `AdminLoginRequest` | Verifies credentials, processes temporary password/2FA challenges. |
| `/admin/auth/password-change`| `POST` | `get_current_super_admin_basic` | `AdminPasswordChangeRequest` | Enforces first-time password rotation. |
| `/admin/auth/totp/setup` | `POST` | `get_current_super_admin` | *None* | Generates a 16-character base32 secret and otpauth URI. |
| `/admin/auth/totp/enable` | `POST` | `get_current_super_admin` | `AdminTotpVerifyRequest` | Validates code, activates 2FA, and returns 8 single-use recovery codes. |
| `/admin/auth/totp/verify` | `POST` | `get_current_super_admin_basic` | `AdminTotpVerifyRequest` | Validates code/recovery code, issues final fully authorized JWT token. |
| `/admin/auth/revoke-session`| `POST` | `get_current_super_admin` | *None* | Blacklists active token in Redis to terminate the session instantly. |
| `/admin/tenants` | `GET` | `get_current_super_admin` | *None* | Lists all tenants, subdomains, user counts, message usage, and sessions. |
| `/admin/tenants/{id}/suspend`| `POST` | `get_current_super_admin` | *None* | Suspends tenant, deactivates users, and blocks campaign/AI actions. |
| `/admin/tenants/{id}/reactivate`| `POST` | `get_current_super_admin` | *None* | Reactivates tenant and restores user accounts to active. |
| `/admin/tenants/{id}/terminate`| `POST` | `get_current_super_admin` | `TerminationRequest` | Triggers Mode 1 (Instant) or Mode 2 (Graceful 24h grace window) workflows. |
| `/admin/tenants/{id}/retention-policy`| `POST` | `get_current_super_admin` | `RetentionPolicyRequest` | Configures data policy for termination (`"archive"` or `"delete"`). |
| `/admin/tenants/{id}/purge` | `DELETE`| `get_current_super_admin` | *None* | Transactional hard purge (cascade DB delete + disk files + Redis keys). |
| `/admin/tenants/{id}/change-plan`| `POST` | `get_current_super_admin` | `PlanChangeRequest` | Manually overrides pricing tier and resets subscription duration. |
| `/admin/tenants/{id}/quotas` | `POST` | `get_current_super_admin` | `QuotaOverrideRequest` | Sets custom quotas for concurrent bots and monthly messages. |
| `/admin/tenants/{id}/reset-usage`| `POST` | `get_current_super_admin` | *None* | Resets monthly usage counters to 0. |
| `/admin/tenants/{id}/impersonate`| `POST` | `get_current_super_admin` | *None* | Generates a valid customer JWT token to debug tenant issues. |
| `/admin/system-health` | `GET` | `get_current_super_admin` | *None* | Telemetry status gauges for PG, Redis, Ollama, WA Engine, and queues. |
| `/admin/monitoring` | `GET` | `get_current_super_admin` | *None* | Metrics for failed messages, IP bans, socket counts, and failed bills. |
| `/admin/audit-logs` | `GET` | `get_current_super_admin` | *None* | Queries permanently stored administrative audit logs in PostgreSQL. |
| `/admin/security-center` | `GET` | `get_current_super_admin` | *None* | Telemetry for locked accounts, brute-force logs, and rate-limit violations. |
| `/admin/broadcast-maintenance`| `POST` | `get_current_super_admin` | `MaintenanceBroadcastRequest` | Dispatches real-time maintenance warning alerts to active dashboards. |
