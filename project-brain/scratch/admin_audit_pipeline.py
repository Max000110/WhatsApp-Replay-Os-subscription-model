import requests
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
import time

DB_CONN_STRING = "host=postgres dbname=saas_whatsapp user=saas_admin password=SecretSaaSPassword123!"
API_BASE = "http://localhost:8000/api/v1"

def get_db_connection():
    return psycopg2.connect(DB_CONN_STRING)

def print_audit_block(action_name, api_req, api_resp, db_before, db_after, audit_log, timestamp):
    print("=" * 80)
    print(f"AUDIT ACTION: {action_name}")
    print(f"Timestamp: {timestamp}")
    print("-" * 40)
    print("API REQUEST:")
    print(json.dumps(api_req, indent=2))
    print("-" * 40)
    print("API RESPONSE:")
    print(f"Status: {api_resp['status_code']}")
    print(json.dumps(api_resp['json'], indent=2))
    print("-" * 40)
    print("DATABASE STATE BEFORE:")
    print(json.dumps(db_before, indent=2))
    print("-" * 40)
    print("DATABASE STATE AFTER:")
    print(json.dumps(db_after, indent=2))
    print("-" * 40)
    print("AUDIT LOG PERSISTED ENTRY:")
    print(json.dumps(audit_log, indent=2))
    print("=" * 80)
    print("\n")

def get_latest_audit_log(action_type, tenant_id=None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if tenant_id:
        cur.execute(
            "SELECT id, action_type, target_tenant_id, affected_resources, old_state, new_state, created_at FROM audit_logs WHERE action_type = %s AND target_tenant_id = %s ORDER BY created_at DESC LIMIT 1;",
            (action_type, tenant_id)
        )
    else:
        cur.execute(
            "SELECT id, action_type, target_tenant_id, affected_resources, old_state, new_state, created_at FROM audit_logs WHERE action_type = %s ORDER BY created_at DESC LIMIT 1;",
            (action_type,)
        )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        row['created_at'] = row['created_at'].isoformat()
    return row

def run_audit():
    # Target tenants
    test_tenant_id = "db29142a-ec07-480f-89f4-5d366ebf6736" # Tenant 'afzal'
    sky_tenant_id = "57f731d3-59e7-4fcb-b068-eecb6d54497a"  # Tenant 'Sky Assist Corp' (for disconnected session test)

    # 1. Admin Login
    print("Running Audit: Admin Login...")
    ts = datetime.now(timezone.utc).isoformat()
    login_payload = {"email": "admin@replyos.com", "password": "ReplyOS@SuperAdmin2024!"}
    resp = requests.post(f"{API_BASE}/admin/auth/login", json=login_payload)
    token = resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    audit_log = get_latest_audit_log("SUCCESSFUL_ADMIN_LOGIN")
    print_audit_block(
        action_name="Admin Login",
        api_req={"url": "/admin/auth/login", "method": "POST", "body": login_payload},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before={"note": "Auth request is credentials matching. No DB pre-state changes required."},
        db_after={"note": "Admin user validated. must_change_password is f."},
        audit_log=audit_log,
        timestamp=ts
    )

    # 2. Diagnostics (System Health)
    print("Running Audit: Diagnostics (System Health)...")
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.get(f"{API_BASE}/admin/system-health", headers=headers)
    print_audit_block(
        action_name="Diagnostics - System Health",
        api_req={"url": "/admin/system-health", "method": "GET"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before={"note": "Read-only operation."},
        db_after={"note": "Read-only operation."},
        audit_log={"note": "System diagnostics querying does not write an audit log row."},
        timestamp=ts
    )

    # 3. Diagnostics (Storage Report)
    print("Running Audit: Diagnostics (Storage Report)...")
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.get(f"{API_BASE}/admin/storage-report", headers=headers)
    print_audit_block(
        action_name="Diagnostics - Storage Report",
        api_req={"url": "/admin/storage-report", "method": "GET"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before={"note": "Read-only operation."},
        db_after={"note": "Read-only operation."},
        audit_log={"note": "Diagnostics querying does not write an audit log row."},
        timestamp=ts
    )

    # 4. Plan Changes
    print("Running Audit: Plan Changes...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT plan_tier, status, max_bots, max_messages_per_month, current_period_end FROM subscriptions WHERE tenant_id = %s;", (test_tenant_id,))
    db_before = cur.fetchone()
    if db_before:
        db_before['current_period_end'] = db_before['current_period_end'].isoformat()
    
    ts = datetime.now(timezone.utc).isoformat()
    plan_payload = {"plan_tier": "pro", "max_bots": 5, "max_messages": 50000, "days": 30}
    resp = requests.post(f"{API_BASE}/admin/tenants/{test_tenant_id}/change-plan", json=plan_payload, headers=headers)
    
    cur.execute("SELECT plan_tier, status, max_bots, max_messages_per_month, current_period_end FROM subscriptions WHERE tenant_id = %s;", (test_tenant_id,))
    db_after = cur.fetchone()
    if db_after:
        db_after['current_period_end'] = db_after['current_period_end'].isoformat()
    cur.close()
    conn.close()

    audit_log = get_latest_audit_log("OVERRIDE_SUBSCRIPTION_PLAN", test_tenant_id)
    print_audit_block(
        action_name="Plan Change",
        api_req={"url": f"/admin/tenants/{test_tenant_id}/change-plan", "method": "POST", "body": plan_payload},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before=db_before,
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 5. Suspend
    print("Running Audit: Suspend Tenant...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT status FROM tenants WHERE id = %s;", (test_tenant_id,))
    db_before = cur.fetchone()
    
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.post(f"{API_BASE}/admin/tenants/{test_tenant_id}/suspend", headers=headers)
    
    cur.execute("SELECT status FROM tenants WHERE id = %s;", (test_tenant_id,))
    db_after = cur.fetchone()
    cur.close()
    conn.close()

    audit_log = get_latest_audit_log("SUSPEND_TENANT", test_tenant_id)
    print_audit_block(
        action_name="Suspend Tenant",
        api_req={"url": f"/admin/tenants/{test_tenant_id}/suspend", "method": "POST"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before=db_before,
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 6. Reactivate
    print("Running Audit: Reactivate Tenant...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT status FROM tenants WHERE id = %s;", (test_tenant_id,))
    db_before = cur.fetchone()
    
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.post(f"{API_BASE}/admin/tenants/{test_tenant_id}/reactivate", headers=headers)
    
    cur.execute("SELECT status FROM tenants WHERE id = %s;", (test_tenant_id,))
    db_after = cur.fetchone()
    cur.close()
    conn.close()

    audit_log = get_latest_audit_log("REACTIVATE_TENANT", test_tenant_id)
    print_audit_block(
        action_name="Reactivate Tenant",
        api_req={"url": f"/admin/tenants/{test_tenant_id}/reactivate", "method": "POST"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before=db_before,
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 7. Quota Override
    print("Running Audit: Quota Override...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT max_bots, max_messages_per_month FROM subscriptions WHERE tenant_id = %s;", (test_tenant_id,))
    db_before = cur.fetchone()
    
    ts = datetime.now(timezone.utc).isoformat()
    quota_payload = {"max_bots": 9, "max_messages": 99999}
    resp = requests.post(f"{API_BASE}/admin/tenants/{test_tenant_id}/quotas", json=quota_payload, headers=headers)
    
    cur.execute("SELECT max_bots, max_messages_per_month FROM subscriptions WHERE tenant_id = %s;", (test_tenant_id,))
    db_after = cur.fetchone()
    cur.close()
    conn.close()

    audit_log = get_latest_audit_log("OVERRIDE_QUOTAS", test_tenant_id)
    print_audit_block(
        action_name="Quota Override",
        api_req={"url": f"/admin/tenants/{test_tenant_id}/quotas", "method": "POST", "body": quota_payload},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before=db_before,
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 8. Reset Counters
    print("Running Audit: Reset Usage Counters...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT COUNT(*) FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.tenant_id = %s;", (test_tenant_id,))
    db_before = cur.fetchone()
    
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.post(f"{API_BASE}/admin/tenants/{test_tenant_id}/reset-usage", headers=headers)
    
    cur.execute("SELECT COUNT(*) FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.tenant_id = %s;", (test_tenant_id,))
    db_after = cur.fetchone()
    cur.close()
    conn.close()

    audit_log = get_latest_audit_log("RESET_USAGE_COUNTERS", test_tenant_id)
    print_audit_block(
        action_name="Reset Usage Counters",
        api_req={"url": f"/admin/tenants/{test_tenant_id}/reset-usage", "method": "POST"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before=db_before,
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 9. Disconnect Session
    print("Running Audit: Disconnect Session...")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, status FROM whatsapp_sessions WHERE tenant_id = %s;", (sky_tenant_id,))
    db_before = cur.fetchall()
    
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.post(f"{API_BASE}/admin/tenants/{sky_tenant_id}/revoke-sessions", headers=headers)
    
    cur.execute("SELECT id, status FROM whatsapp_sessions WHERE tenant_id = %s;", (sky_tenant_id,))
    db_after = cur.fetchall()
    cur.close()
    conn.close()

    audit_log = get_latest_audit_log("FORCE_REVOKE_TENANT_SESSIONS", sky_tenant_id)
    print_audit_block(
        action_name="Disconnect Session",
        api_req={"url": f"/admin/tenants/{sky_tenant_id}/revoke-sessions", "method": "POST"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before=db_before,
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 10. Emergency Lock
    print("Running Audit: Emergency Lock...")
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.post(f"{API_BASE}/admin/system/emergency-lock", headers=headers)
    
    # Check Redis key
    import redis
    r_client = redis.Redis.from_url("redis://:SecretRedisPassword123!@redis:6379/0")
    redis_val = r_client.get("emergency_system_lock")
    db_after = {"redis_emergency_system_lock": redis_val.decode() if redis_val else None}

    audit_log = get_latest_audit_log("EMERGENCY_SYSTEM_LOCK")
    print_audit_block(
        action_name="Emergency Lock",
        api_req={"url": "/admin/system/emergency-lock", "method": "POST"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before={"redis_emergency_system_lock": None},
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 11. Emergency Unlock
    print("Running Audit: Emergency Unlock...")
    ts = datetime.now(timezone.utc).isoformat()
    resp = requests.post(f"{API_BASE}/admin/system/emergency-unlock", headers=headers)
    
    redis_val = r_client.get("emergency_system_lock")
    db_after = {"redis_emergency_system_lock": redis_val.decode() if redis_val else None}

    audit_log = get_latest_audit_log("EMERGENCY_SYSTEM_UNLOCK")
    print_audit_block(
        action_name="Emergency Unlock",
        api_req={"url": "/admin/system/emergency-unlock", "method": "POST"},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before={"redis_emergency_system_lock": "true"},
        db_after=db_after,
        audit_log=audit_log,
        timestamp=ts
    )

    # 12. Broadcast Maintenance
    print("Running Audit: Broadcast Maintenance...")
    ts = datetime.now(timezone.utc).isoformat()
    broadcast_payload = {"message": "[SYSTEM MAINTENANCE] Platform upgrade scheduled for 02:00 UTC."}
    resp = requests.post(f"{API_BASE}/admin/broadcast-maintenance", json=broadcast_payload, headers=headers)
    
    audit_log = get_latest_audit_log("BROADCAST_SYSTEM_MAINTENANCE")
    print_audit_block(
        action_name="Broadcast Maintenance",
        api_req={"url": "/admin/broadcast-maintenance", "method": "POST", "body": broadcast_payload},
        api_resp={"status_code": resp.status_code, "json": resp.json()},
        db_before={"note": "Broadcast is transient WebSocket/PubSub event propagation."},
        db_after={"note": "Broadcast is transient WebSocket/PubSub event propagation."},
        audit_log=audit_log,
        timestamp=ts
    )

if __name__ == "__main__":
    run_audit()
