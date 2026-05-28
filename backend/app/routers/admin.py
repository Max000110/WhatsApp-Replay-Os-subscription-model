from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.auth.service import get_current_admin
from app.models.all_models import Tenant, User, Subscription, WhatsAppSession, Message, AIUsageLog, CampaignLog, PaymentTransaction
from app.core.websocket import websocket_manager
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import httpx

router = APIRouter(prefix="/admin", tags=["Master Super Admin Dashboard"])

class PlanChangeRequest(BaseModel):
    plan_tier: str
    max_bots: Optional[int] = None
    max_messages: Optional[int] = None
    days: Optional[int] = 30

class MaintenanceBroadcastRequest(BaseModel):
    message: str

@router.get("/tenants")
def get_all_tenants(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Super Admin view of all tenants, subscriptions, and active WhatsApp session status.
    """
    tenants = db.query(Tenant).all()
    results = []
    for t in tenants:
        sub = db.query(Subscription).filter(Subscription.tenant_id == t.id).first()
        sessions = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == t.id).all()
        user_count = db.query(User).filter(User.tenant_id == t.id).count()
        
        results.append({
            "id": str(t.id),
            "name": t.name,
            "subdomain": t.subdomain,
            "created_at": t.created_at,
            "user_count": user_count,
            "subscription": {
                "plan_tier": sub.plan_tier if sub else "free",
                "status": sub.status if sub else "active",
                "max_bots": sub.max_bots if sub else 1,
                "max_messages": sub.max_messages_per_month if sub else 500,
                "current_period_end": sub.current_period_end if sub else None
            },
            "sessions": [{
                "id": str(s.id),
                "name": s.session_name,
                "status": s.status,
                "phone": s.phone_number
            } for s in sessions]
        })
    return results

@router.post("/tenants/{tenant_id}/activate")
def manually_activate_tenant(tenant_id: UUID, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Manually activates or unlocks a tenant's subscription.
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id)
        db.add(sub)
        
    sub.status = "active"
    db.commit()
    db.refresh(sub)
    return {"status": "success", "message": f"Tenant {tenant_id} subscription manually activated."}

@router.post("/tenants/{tenant_id}/suspend")
def manually_suspend_tenant(tenant_id: UUID, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Manually suspends a tenant's access (suspends subscription and deactivates users).
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id)
        db.add(sub)
        
    sub.status = "suspended"
    
    # Deactivate all users under this tenant
    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    for u in users:
        u.is_active = False
        
    db.commit()
    return {"status": "success", "message": f"Tenant {tenant_id} successfully suspended."}

@router.post("/tenants/{tenant_id}/change-plan")
def manually_change_plan(
    tenant_id: UUID, 
    payload: PlanChangeRequest, 
    admin: User = Depends(get_current_admin), 
    db: Session = Depends(get_db)
):
    """
    Super Admin manual override to change a tenant's plan tier and quotas.
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id)
        db.add(sub)
        
    tier = payload.plan_tier.lower()
    from app.routers.billing import PLAN_DETAILS
    if tier not in PLAN_DETAILS:
        raise HTTPException(status_code=400, detail="Invalid plan tier specified.")
        
    plan = PLAN_DETAILS[tier]
    sub.plan_tier = tier
    sub.status = "active"
    sub.max_bots = payload.max_bots if payload.max_bots is not None else plan["max_bots"]
    sub.max_messages_per_month = payload.max_messages if payload.max_messages is not None else plan["max_messages"]
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=payload.days)
    
    # Reactivate users in case they were suspended
    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    for u in users:
        u.is_active = True
        
    db.commit()
    db.refresh(sub)
    return {"status": "success", "subscription": {
        "plan_tier": sub.plan_tier,
        "max_bots": sub.max_bots,
        "max_messages": sub.max_messages_per_month,
        "current_period_end": sub.current_period_end
    }}

@router.get("/payments")
def get_payments_history(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Monitors all payment transaction history and subscription invoices.
    """
    return db.query(PaymentTransaction).order_by(PaymentTransaction.created_at.desc()).all()

@router.get("/usage")
def get_usage_metrics(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Monitors global resource usage metrics including token counts and outbound dispatches.
    """
    # 1. Total chat messages sent
    total_messages = db.query(Message).count()
    outbound_messages = db.query(Message).filter(Message.direction == "outbound").count()
    
    # 2. Token usage aggregations
    token_stats = db.query(
        func.sum(AIUsageLog.tokens_used).label("total_tokens"),
        func.avg(AIUsageLog.latency_ms).label("avg_latency")
    ).first()
    
    # 3. Message count per tenant
    tenant_usage = db.query(
        Message.sender_type,
        func.count(Message.id).label("count")
    ).group_by(Message.sender_type).all()
    
    return {
        "global_usage": {
            "total_messages": total_messages,
            "outbound_messages": outbound_messages,
            "total_ai_tokens": token_stats.total_tokens if token_stats and token_stats.total_tokens else 0,
            "avg_ai_latency_ms": float(token_stats.avg_latency) if token_stats and token_stats.avg_latency else 0.0
        },
        "message_distribution": {row[0]: row[1] for row in tenant_usage}
    }

@router.get("/system-health")
async def get_system_health(admin: User = Depends(get_current_admin)):
    """
    Returns diagnostics info, WhatsApp engine status, and local CPU health metrics.
    """
    import os
    import psutil
    
    # Check WhatsApp engine connectivity
    whatsapp_engine_health = "offline"
    active_sessions = 0
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.WHATSAPP_ENGINE_URL}/health", timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                whatsapp_engine_health = data.get("status", "healthy")
                active_sessions = data.get("activeSessions", 0)
    except Exception as e:
        print("[Admin System Health] Engine diagnostics failed:", e)
        
    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        },
        "services": {
            "whatsapp_engine_status": whatsapp_engine_health,
            "whatsapp_active_sessions": active_sessions
        }
    }

@router.post("/broadcast-maintenance")
async def broadcast_maintenance_alert(payload: MaintenanceBroadcastRequest, admin: User = Depends(get_current_admin)):
    """
    Broadcasts a maintenance notification alert to all active tenant websocket dashboard clients.
    """
    # Publish to all connected websockets via the global ws manager
    await websocket_manager.broadcast_global_event("maintenance_alert", {
        "message": payload.message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return {"status": "success", "message": "Global maintenance alert broadcasted."}
