from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any

# Authentication & Registration Schemas
class TenantCreate(BaseModel):
    name: str
    subdomain: Optional[str] = None

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    tenant_name: str
    subdomain: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    tenant_id: UUID

# Session Schemas
class SessionCreate(BaseModel):
    session_name: str

class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    phone_number: Optional[str] = None
    session_name: str
    status: str
    qr_code: Optional[str] = None
    reconnect_attempts: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Webhook payload structures (used internally)
class WebhookData(BaseModel):
    qr: Optional[str] = None
    phone: Optional[str] = None
    messageId: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")
    rawRemoteJid: Optional[str] = None
    rawParticipant: Optional[str] = None
    pushName: Optional[str] = None
    body: Optional[str] = None
    timestamp: Optional[int] = None
    error: Optional[str] = None
    whatsappMessageId: Optional[str] = None
    status: Optional[str] = None

class EngineWebhookPayload(BaseModel):
    sessionId: str
    event: str
    data: WebhookData

# AI Bot Schemas
class BotCreate(BaseModel):
    session_id: Optional[UUID] = None
    name: str
    system_prompt: str
    model_name: Optional[str] = "qwen2.5:1.5b-instruct"
    temperature: Optional[float] = 0.4
    rag_enabled: Optional[bool] = False
    personality: Optional[str] = "Friendly"
    company_name: Optional[str] = None
    services: Optional[str] = None
    products: Optional[str] = None
    pricing: Optional[str] = None
    policies: Optional[str] = None
    location: Optional[str] = None
    working_hours: Optional[str] = None
    contact_details: Optional[str] = None
    custom_instructions: Optional[str] = None
    memory_enabled: Optional[bool] = False

class BotUpdate(BaseModel):
    session_id: Optional[UUID] = None
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    rag_enabled: Optional[bool] = None
    is_active: Optional[bool] = None
    personality: Optional[str] = None
    company_name: Optional[str] = None
    services: Optional[str] = None
    products: Optional[str] = None
    pricing: Optional[str] = None
    policies: Optional[str] = None
    location: Optional[str] = None
    working_hours: Optional[str] = None
    contact_details: Optional[str] = None
    custom_instructions: Optional[str] = None
    memory_enabled: Optional[bool] = None

class BotResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    session_id: Optional[UUID] = None
    name: str
    system_prompt: str
    model_name: str
    temperature: float
    rag_enabled: bool
    is_active: bool
    personality: str
    company_name: Optional[str] = None
    services: Optional[str] = None
    products: Optional[str] = None
    pricing: Optional[str] = None
    policies: Optional[str] = None
    location: Optional[str] = None
    working_hours: Optional[str] = None
    contact_details: Optional[str] = None
    custom_instructions: Optional[str] = None
    memory_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Conversation & Chat Schemas
class MessageResponse(BaseModel):
    id: UUID
    client_uuid: Optional[UUID] = None
    conversation_id: UUID
    tenant_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    direction: str
    origin: Optional[str] = None
    sender_type: str
    content: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    status: str
    ack_state: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    session_id: UUID
    customer_phone: str
    customer_name: Optional[str] = None
    is_archived: bool
    customer_preferences: Optional[str] = None
    past_interactions_summary: Optional[str] = None
    open_tickets: Optional[str] = None
    lead_status: Optional[str] = "cold"
    
    # Handoff & Memory fields
    handoff_status: Optional[str] = "AI_ACTIVE"
    assigned_agent_id: Optional[UUID] = None
    last_purchase: Optional[str] = None
    lead_stage: Optional[str] = "cold"
    
    last_message_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationUpdate(BaseModel):
    customer_preferences: Optional[str] = None
    past_interactions_summary: Optional[str] = None
    open_tickets: Optional[str] = None
    lead_status: Optional[str] = None
    is_archived: Optional[bool] = None

class SendMessageRequest(BaseModel):
    session_id: UUID
    to_phone: str
    content: str
    client_uuid: Optional[UUID] = None

# RAG & Knowledge Base Schemas
class KBCreate(BaseModel):
    name: str
    description: Optional[str] = None

class KBResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentResponse(BaseModel):
    id: UUID
    kb_id: UUID
    filename: str
    file_path: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Campaigns
class CampaignCreate(BaseModel):
    session_id: UUID
    name: str
    template_text: str
    scheduled_time: datetime
    recipient_phones: List[str]
    recurring_interval: Optional[str] = "none" # none, hourly, daily, weekly

class CampaignResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    session_id: Optional[UUID] = None
    name: str
    template_text: str
    scheduled_time: datetime
    recurring_interval: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Prompt Testing Console Schemas
class PromptTestRequest(BaseModel):
    test_question: str
    conversation_id: Optional[UUID] = None

class PromptTestResponse(BaseModel):
    constructed_prompt: str
    retrieved_context: str
    llm_response: str

# Google Auth
class GoogleAuthRequest(BaseModel):
    id_token: str

# Human Handoff
class HandoffStatusUpdate(BaseModel):
    status: str  # AI_ACTIVE, WAITING_AGENT, HUMAN_ACTIVE, RESOLVED
    notes: Optional[str] = None

# Support Agents
class SupportAgentCreate(BaseModel):
    name: str
    email: EmailStr
    department: str  # Support, Sales, Billing, Technical
    skills: Optional[str] = None
    status: Optional[str] = "available"

class SupportAgentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    email: str
    department: str
    skills: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# Google Calendar Booking
class BookingCreate(BaseModel):
    customer_phone: str
    customer_email: EmailStr
    booking_date: str  # YYYY-MM-DD
    booking_time: str  # HH:MM
    notes: Optional[str] = None

class BookingResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    booking_id: str
    calendar_event_id: str
    customer_phone: str
    customer_email: str
    booking_date: str
    booking_time: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
