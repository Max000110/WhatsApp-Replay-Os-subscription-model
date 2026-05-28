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

class BotUpdate(BaseModel):
    session_id: Optional[UUID] = None
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    rag_enabled: Optional[bool] = None
    is_active: Optional[bool] = None

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
    created_at: datetime

    class Config:
        from_attributes = True

# Conversation & Chat Schemas
class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    direction: str
    sender_type: str
    content: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    status: str
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
    last_message_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

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

class CampaignResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    session_id: Optional[UUID] = None
    name: str
    template_text: str
    scheduled_time: datetime
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
