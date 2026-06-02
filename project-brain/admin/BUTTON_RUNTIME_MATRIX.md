# Control Plane Button Runtime Matrix

This document maps and validates the end-to-end execution path for every administrative button in the ReplyOS Super Admin dashboard.

---

## 1. Action Execution Paths

All 13 buttons have been verified to execute transactionally without orphaned data or partial mutations.

| # | Button Label | Frontend Click Action | API Request | Backend Route | DB Mutation / Engine Call | UI Post-Action | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Edit Plan** | Submits edit plan form modal | `POST /admin/tenants/{id}/change-plan` | `change_plan_tier()` | Updates plan tier in `subscriptions` table. Reactivates tenant status. | Reloads registry dataset. | ✅ Functional |
| 2 | **Suspend** | Triggers tenant suspend action | `POST /admin/tenants/{id}/suspend` | `suspend_tenant()` | Sets status to `suspended` in `tenants`, `users`, & `subscriptions`. | Reloads registry dataset. | ✅ Functional |
| 3 | **Archive Mode / Delete Mode** | Toggles archive/delete policy | `POST /admin/tenants/{id}/retention-policy` | `set_retention_policy()` | Updates `data_retention_policy` to `archive`/`delete` in `tenants`. | Policy status text toggles. | ✅ Functional |
| 4 | **Quota** | Submits quotas form modal | `POST /admin/tenants/{id}/quotas` | `override_tenant_quotas()` | Overwrites `max_bots` and `max_messages_per_month` columns in DB. | Reloads registry dataset. | ✅ Functional |
| 5 | **Reset Counters** | Triggers reset counters confirmation | `POST /admin/tenants/{id}/reset-usage` | `reset_usage_counters()` | Deletes rows from `messages` registered within current billing month. | Reloads registry dataset. | ✅ Functional |
| 6 | **Disconnect Sessions** | Triggers disconnect confirmation | `POST /admin/tenants/{id}/revoke-sessions` | `force_revoke_tenant_sessions()` | Sets status to `disconnected` in DB. Sends DELETE to WhatsApp Node Engine. | Session status turns red. | ✅ Functional |
| 7 | **Terminate Tenant** | Submits terminate modal (grace/instant) | `POST /admin/tenants/{id}/terminate` | `terminate_tenant()` | Sets status to `TERMINATED` (instant) or `PENDING TERMINATION` (graceful). | Reloads registry dataset. | ✅ Functional |
| 8 | **Restore Tenant** | Triggers Reactivate action | `POST /admin/tenants/{id}/reactivate` | `reactivate_tenant()` | Sets status to `active` in `tenants` and resets user active flags to `True`. | Status turns green. | ✅ Functional |
| 9 | **Renew Subscription** | Triggers Edit Plan modal (preset days) | `POST /admin/tenants/{id}/change-plan` | `change_plan_tier()` | Extends `current_period_end` date in `subscriptions` table. | Expiry date updates in table. | ✅ Functional |
| 10 | **Grant Access** | Triggers Grant Access action | `POST /admin/tenants/{id}/grant-access` | `grant_tenant_access()` | Sets `is_active = True` for all tenant members in `users` table. | Reloads registry dataset. | ✅ Functional |
| 11 | **Revoke Access** | Triggers Revoke Access action | `POST /admin/tenants/{id}/revoke-access` | `revoke_tenant_access()` | Sets `is_active = False` for all tenant members in `users` table. | Reloads registry dataset. | ✅ Functional |
| 12 | **Emergency Lock** | Triggers Lock confirmation | `POST /admin/system/emergency-lock` | `emergency_lock_system()` | Sets `emergency_system_lock = "true"` key in Redis database. | Lockdown status turns RED. | ✅ Functional |
| 13 | **Emergency Unlock** | Triggers Unlock confirmation | `POST /admin/system/emergency-unlock` | `emergency_unlock_system()` | Deletes `emergency_system_lock` key from Redis database. | Lockdown status turns GREEN.| ✅ Functional |

---

## 2. Audit Trail Proof (AuditLog Examples)

Audit records are committed transactionally to the database for every action:

```json
{
  "timestamp": "2026-05-29T20:45:00Z",
  "admin_email": "admin@replyos.com",
  "target_tenant_name": "Antigravity Inc",
  "action_type": "OVERRIDE_SUBSCRIPTION_PLAN",
  "affected_resources": "subscription, tenant, users",
  "new_state": { "plan_tier": "pro", "days_added": 30 }
}
```
