from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Chatbot, WhatsAppSession
from app.schemas.all_schemas import BotCreate, BotUpdate, BotResponse
from uuid import UUID
from typing import List

router = APIRouter(prefix="/bots", tags=["Chatbots"])

@router.get("/", response_model=List[BotResponse])
def list_bots(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves all bots belonging to the active organization tenant"""
    return db.query(Chatbot).filter(Chatbot.tenant_id == tenant_id).all()

@router.post("/", response_model=BotResponse)
def create_bot(payload: BotCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Creates a new chatbot configured with instructions and target sessions"""
    # Verify session JID belongs to same tenant
    if payload.session_id:
        sess = db.query(WhatsAppSession).filter(
            WhatsAppSession.id == payload.session_id,
            WhatsAppSession.tenant_id == tenant_id
        ).first()
        if not sess:
            raise HTTPException(status_code=400, detail="Invalid target WhatsApp session JID.")
            
        # Deactivate any active bot currently mounted to same session JID to prevent loops
        db.query(Chatbot).filter(
            Chatbot.session_id == payload.session_id,
            Chatbot.is_active == True
        ).update({"is_active": False})
        db.commit()

    new_bot = Chatbot(
        tenant_id=tenant_id,
        session_id=payload.session_id,
        name=payload.name,
        system_prompt=payload.system_prompt,
        model_name=payload.model_name,
        temperature=payload.temperature,
        rag_enabled=payload.rag_enabled,
        is_active=True
    )
    db.add(new_bot)
    db.commit()
    db.refresh(new_bot)
    return new_bot

@router.get("/{bot_id}", response_model=BotResponse)
def get_bot(bot_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves config for a single chatbot"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")
    return bot

@router.patch("/{bot_id}", response_model=BotResponse)
def update_bot(bot_id: UUID, payload: BotUpdate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Updates chatbot settings"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")

    for field, val in payload.dict(exclude_unset=True).items():
        setattr(bot, field, val)

    db.commit()
    db.refresh(bot)
    return bot

@router.delete("/{bot_id}")
def delete_bot(bot_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Deletes a chatbot config"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")
    db.delete(bot)
    db.commit()
    return {"message": "Chatbot successfully deleted."}
