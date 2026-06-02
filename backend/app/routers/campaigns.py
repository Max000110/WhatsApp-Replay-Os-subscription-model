from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Campaign, CampaignLog, WhatsAppSession
from app.schemas.all_schemas import CampaignCreate, CampaignResponse
from uuid import UUID
from typing import List

router = APIRouter(prefix="/campaigns", tags=["Marketing Campaigns"])

@router.get("/", response_model=List[CampaignResponse])
def list_campaigns(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves all broadcast campaigns created by the active tenant"""
    return db.query(Campaign).filter(Campaign.tenant_id == tenant_id).all()

@router.post("/", response_model=CampaignResponse)
def create_campaign(payload: CampaignCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Creates a campaign and delegates dispatch operations to Celery worker threads.
    """
    # Verify session scope
    sess = db.query(WhatsAppSession).filter(
        WhatsAppSession.id == payload.session_id,
        WhatsAppSession.tenant_id == tenant_id
    ).first()
    if not sess:
        raise HTTPException(status_code=400, detail="Invalid WhatsApp sender session.")

    # 1. Create primary Campaign catalog
    new_campaign = Campaign(
        tenant_id=tenant_id,
        session_id=payload.session_id,
        name=payload.name,
        template_text=payload.template_text,
        scheduled_time=payload.scheduled_time,
        recurring_interval=payload.recurring_interval or "none",
        status="scheduled"
    )
    db.add(new_campaign)
    db.commit()
    db.refresh(new_campaign)

    # 2. Bulk insert recipient records to dynamic dispatch log
    from app.core.jid import normalize_jid
    for phone in payload.recipient_phones:
        try:
            recipient_phone = normalize_jid(phone)
        except ValueError as err:
            db.rollback()
            print(f"[Campaigns] Rejected campaign recipient '{phone}': {err}")
            raise HTTPException(status_code=400, detail=f"Invalid campaign recipient '{phone}': {err}")
        log = CampaignLog(
            campaign_id=new_campaign.id,
            recipient_phone=recipient_phone,
            status="pending"
        )
        db.add(log)
    db.commit()

    # 3. Queue the broadcast Celery pipeline task
    try:
        from worker.celery_app import celery
        from datetime import datetime, timezone
        
        now_utc = datetime.now(timezone.utc)
        sched_time = new_campaign.scheduled_time
        if sched_time.tzinfo is None:
            sched_time = sched_time.replace(tzinfo=timezone.utc)
            
        if sched_time > now_utc:
            # Schedule for future execution in Celery using ETA
            celery.send_task(
                "worker.tasks.run_campaign_broadcast_task",
                args=[str(new_campaign.id)],
                eta=sched_time
            )
            print(f"[Router] Scheduled future Celery campaign task ETA: {sched_time}")
        else:
            # Send immediately
            celery.send_task("worker.tasks.run_campaign_broadcast_task", args=[str(new_campaign.id)])
    except Exception as err:
        print("[Router] Failed dispatching Celery campaign task:", err)
        # Proceed with scheduled status; background workers will catch it on boot
        
    return new_campaign
