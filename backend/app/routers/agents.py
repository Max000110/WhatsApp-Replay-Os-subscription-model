from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Conversation, SupportAgent
from app.schemas.all_schemas import SupportAgentCreate, SupportAgentResponse, ConversationResponse
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

@router.post("/assign", response_model=ConversationResponse)
def assign_conversation(payload: AgentAssignRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
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

    conv.assigned_agent_id = agent.id
    conv.handoff_status = "HUMAN_ACTIVE" # Automatic handoff takeover when assigned
    db.commit()
    db.refresh(conv)
    return conv

@router.post("/transfer", response_model=ConversationResponse)
def transfer_conversation(payload: AgentTransferRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
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
    db.commit()
    db.refresh(conv)
    return conv

@router.post("/close", response_model=ConversationResponse)
def close_conversation(payload: ChatStateRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
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
    db.commit()
    db.refresh(conv)
    return conv

@router.post("/reopen", response_model=ConversationResponse)
def reopen_conversation(payload: ChatStateRequest, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Reopens a closed thread, changing status back to WAITING_AGENT to halt AI bot responses"""
    conv = db.query(Conversation).filter(
        Conversation.id == payload.conversation_id,
        Conversation.tenant_id == tenant_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation thread not found.")

    conv.handoff_status = "WAITING_AGENT"
    db.commit()
    db.refresh(conv)
    return conv
