# Master Admin Panel — Consolidated Specification
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## Access Points
| URL | Purpose |
|---|---|
| `http://144.24.126.153:8080/admin/login` | Super Admin Login |
| `http://144.24.126.153:8080/admin` | Super Admin Control Plane |

---

## Authentication Pipeline

```
POST /admin/auth/login
        │
   Credentials valid?
        │ Yes
   must_change_password?
   ├─ Yes → return force_password_change (temp token)
   │         POST /admin/auth/password-change
   │
   totp_enabled?
   ├─ Yes → return totp_required (temp token)
   │         POST /admin/auth/totp/verify
   │
   └─ No  → Issue final JWT (scopes: ["super_admin"], totp_verified: True)
             → Navigate to /admin
```

---

## Control Plane Tabs

### Tab 1: Tenant Lifecycle Registry
- Lists all tenants with subdomain, user count, message usage, session count, plan tier, status
- Actions per tenant:
  - Suspend (immediate) / Reactivate
  - Change plan tier
  - Override quotas (max bots, max monthly messages)
  - Reset monthly usage counter
  - Mode 1 termination (instant cascade delete)
  - Mode 2 termination (graceful 24h window)
  - Configure data retention policy (archive or delete)
  - Hard purge (cascade DB + disk + Redis)
  - Impersonate (generate tenant JWT for debugging)

### Tab 2: System Realtime Diagnostics
Hardware vitals from `psutil`:
- CPU usage %
- RAM usage %
- Disk usage %

Service connectivity:
- PostgreSQL (`SELECT 1` ping)
- Redis (PING + latency ms)
- WhatsApp Engine (HTTP `/health`)
- Ollama AI (HTTP `/` ping)
- WebSocket (active connection count)
- Celery Worker (`inspect().ping()` — real heartbeat)

Queue telemetry:
- Active outbound queue sizes (`whatsapp_queue_*`)
- Failed message count
- Failed campaign count
- Failed payment count

### Tab 3: Permanent Administrative Audit
- Read-only log of all admin actions
- Columns: timestamp, admin email, target tenant, resource, action, JSON state
- Persisted permanently in `audit_logs` PostgreSQL table
- Cannot be modified or deleted

### Tab 4: Control Plane Hardening
Security observability:
- Locked accounts (brute-force lockouts)
- Active IP bans (`ip_ban:*` Redis keys)
- Rate limit violations (`rate_limit_violation:*` Redis keys)
- Recent failed login attempts

Maintenance broadcast:
- Send real-time alert to all active tenant dashboards via WebSocket

### Tab 5: Operational Settings
- Password rotation
- Email/username update
- TOTP 2FA setup (setup → enable → recovery codes)
- Active session revocation (Redis blacklist)

---

## REST API Reference

| Endpoint | Method | Guard | Description |
|---|---|---|---|
| `/admin/auth/login` | POST | None | Credential + 2FA flow |
| `/admin/auth/password-change` | POST | basic | Force password rotation |
| `/admin/auth/totp/setup` | POST | full | Generate TOTP secret |
| `/admin/auth/totp/enable` | POST | full | Activate 2FA + recovery codes |
| `/admin/auth/totp/verify` | POST | basic | Complete 2FA login |
| `/admin/auth/revoke-session` | POST | full | Blacklist current JWT |
| `/admin/tenants` | GET | full | List all tenants |
| `/admin/tenants/{id}/suspend` | POST | full | Suspend tenant |
| `/admin/tenants/{id}/reactivate` | POST | full | Reactivate tenant |
| `/admin/tenants/{id}/terminate` | POST | full | Mode 1 or Mode 2 termination |
| `/admin/tenants/{id}/retention-policy` | POST | full | Set archive/delete policy |
| `/admin/tenants/{id}/purge` | DELETE | full | Hard cascade purge |
| `/admin/tenants/{id}/change-plan` | POST | full | Override plan tier |
| `/admin/tenants/{id}/quotas` | POST | full | Override quotas |
| `/admin/tenants/{id}/reset-usage` | POST | full | Reset monthly usage |
| `/admin/tenants/{id}/impersonate` | POST | full | Generate tenant JWT |
| `/admin/system-health` | GET | full | CPU/RAM/PG/Redis/Ollama/WA |
| `/admin/monitoring` | GET | full | Queue sizes + violations |
| `/admin/audit-logs` | GET | full | Read audit trail |
| `/admin/security-center` | GET | full | IP bans + locked accounts |
| `/admin/broadcast-maintenance` | POST | full | Push WS alert to all tenants |

---

## Token Architecture

- **Admin Token Key**: `replyos_admin_token` (localStorage)
- **Admin Tenant ID Key**: `replyos_admin_tenant_id` (localStorage)
- **Admin Role Key**: `replyos_admin_role` (localStorage)
- **Token Scope**: `scopes: ["super_admin"]`, `totp_verified: True`
- **Token Expiry**: 2 hours
- **Revocation**: Redis blacklist with 7-day TTL

## Isolation Guarantees
- Admin routes completely separate from customer routes (`/admin/*`)
- Admin token namespace separate from customer token namespace
- No customer can discover, enumerate, or call admin endpoints
- Admin JWT is rejected by customer-facing endpoints and vice versa
