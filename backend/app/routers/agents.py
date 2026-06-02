from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Conversation, SupportAgent
from app.schemas.all_schemas import SupportAgentCreate, SupportAgentResponse, ConversationResponse
from app.core.websocket import websocket_manager
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["Support Agent & Department Management"])

class AgentAssignRequest(BaseModel):
    conversation_id: UUID
    agent_id: UUID

class AgentTransferRequest(BaseModel):
    conversation_id: UUID
    target_agent_id: Optional[UUID] = None
    target_department: Optional[str] = None # Support, Sales, Billing, Technical

class ChatStateRequest(BaseModel):
    conversation_id: UUID

@router.get("", response_model=List[SupportAgentResponse])
def list_agents(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Lists all support agents assigned to this tenant organization"""
    return db.query(SupportAgent).filter(SupportAgent.tenant_id == tenant_id).all()

@router.post("", response_model=SupportAgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(payload: SupportAgentCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Registers a new Support Agent within a specific department"""
    valid_depts = ["Support", "Sales", "Billing", "Technical"]
    if payload.department not in valid_depts:
        raise HTTPException(status_code=400, detail=f"Invalid department: {payload.department}. Must be one of {valid_depts}")

    # Check if agent already exists
    existing = db.query(SupportAgent).filter(
        SupportAgent.tenant_id == tenant_id,
        SupportAgent.email == payload.email
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="An agent with this email is already registered.")

    agent = SupportAgent(
        tenant_id=tenant_id,
        name=payload.name,
        email=payload.email,
        department=payload.department,
        skills=payload.skills,
        status=payload.status
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent

async def trigger_live_agent_override(conversation_id: str, agent_id: str, db: Session, tenant_id: str):
    """Flush internal bot context instantly when human agent connects"""
    db.execute(
        text("UPDATE conversations SET handoff_status = 'HUMAN_ACTIVE', bot_override = TRUE WHERE id = :id"),
        {"id": conversation_id}
    )
    db.commit()
    # Force transmission of green-state active flag via WebSockets
    await websocket_manager.publish_event(
        str(tenant_id),
        "conversation",
        {
            "id": conversation_id,
            "status": "CONNECTED_GREEN",
            "agent": agent_id,
            "handoff_status": "HUMAN_ACTIVE",
            "bot_override": True
        }
    )

@router.post("/assign", response_model=ConversationResponse)
async def assign_conversation(payload: AgentAssignRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Assigns an open WhatsApp conversation thread to a support agent"""
    conv = db.query(Conversation).filter(
        Conversation.id == payload.conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation thread not found.")

    agent = db.query(SupportAgent).filter(
        SupportAgent.id == payload.agent_id,
        SupportAgent.tenant_id == tenant_id
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Support agent not found.")

    # Call dynamic live agent handoff logic override from session_service
    from app.services.session_service import session_service
    await session_service.trigger_live_agent_override(str(conv.id), str(agent.id), db, str(tenant_id))
    
    # Reload and bind ORM object fields
    db.refresh(conv)
    conv.assigned_agent_id = agent.id
    db.commit()
    db.refresh(conv)
    return conv

@router.post("/transfer", response_model=ConversationResponse)
async def transfer_conversation(payload: AgentTransferRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Transfers conversation ownership to another agent or department"""
    conv = db.query(Conversation).filter(
        Conversation.id == payload.conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation thread not found.")

    if payload.target_agent_id:
        agent = db.query(SupportAgent).filter(
            SupportAgent.id == payload.target_agent_id,
            SupportAgent.tenant_id == tenant_id
        ).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Target agent not found.")
        conv.assigned_agent_id = agent.id
        # Automatically align department if transferred to a specific agent
        if not payload.target_department:
            payload.target_department = agent.department
            
    if payload.target_department:
        valid_depts = ["Support", "Sales", "Billing", "Technical"]
        if payload.target_department not in valid_depts:
            raise HTTPException(status_code=400, detail="Invalid target department.")
        # If transferring only to department, clear current agent assignment so it can be picked up
        if not payload.target_agent_id:
            conv.assigned_agent_id = None
        conv.lead_stage = payload.target_department # Using lead_stage or similar metadata to track active department scope

    conv.handoff_status = "WAITING_AGENT" if not conv.assigned_agent_id else "HUMAN_ACTIVE"
    conv.bot_override = True if conv.assigned_agent_id else False
    db.commit()
    db.refresh(conv)
    
    # Broadcast transfer status
    conv_data = {
        "id": str(conv.id),
        "tenant_id": str(conv.tenant_id),
        "session_id": str(conv.session_id),
        "customer_phone": conv.customer_phone,
        "customer_name": conv.customer_name,
        "is_archived": conv.is_archived,
        "handoff_status": conv.handoff_status,
        "bot_override": conv.bot_override,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
    }
    await websocket_manager.publish_event(str(tenant_id), "conversation", conv_data)
    
    return conv

@router.post("/close", response_model=ConversationResponse)
async def close_conversation(payload: ChatStateRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Closes conversation, marking the issue as resolved and releasing back to AI bot"""
    conv = db.query(Conversation).filter(
        Conversation.id == payload.conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation thread not found.")

    conv.handoff_status = "RESOLVED"
    conv.bot_paused_until = None
    conv.assigned_agent_id = None
    conv.bot_override = False
    db.commit()
    db.refresh(conv)
    
    # Broadcast close status
    conv_data = {
        "id": str(conv.id),
        "tenant_id": str(conv.tenant_id),
        "session_id": str(conv.session_id),
        "customer_phone": conv.customer_phone,
        "customer_name": conv.customer_name,
        "is_archived": conv.is_archived,
        "handoff_status": conv.handoff_status,
        "bot_override": conv.bot_override,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
    }
    await websocket_manager.publish_event(str(tenant_id), "conversation", conv_data)
    
    return conv

@router.post("/reopen", response_model=ConversationResponse)
async def reopen_conversation(payload: ChatStateRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Reopens a closed thread, changing status back to WAITING_AGENT to halt AI bot responses"""
    conv = db.query(Conversation).filter(
        Conversation.id == payload.conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation thread not found.")

    conv.handoff_status = "WAITING_AGENT"
    conv.bot_override = True
    db.commit()
    db.refresh(conv)
    
    # Broadcast reopen status
    conv_data = {
        "id": str(conv.id),
        "tenant_id": str(conv.tenant_id),
        "session_id": str(conv.session_id),
        "customer_phone": conv.customer_phone,
        "customer_name": conv.customer_name,
        "is_archived": conv.is_archived,
        "handoff_status": conv.handoff_status,
        "bot_override": conv.bot_override,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
    }
    await websocket_manager.publish_event(str(tenant_id), "conversation", conv_data)
    
    return conv
