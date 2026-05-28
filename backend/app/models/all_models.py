from sqlalchemy import Column, String, Boolean, Integer, Float, ForeignKey, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    name = Column(String(255), nullable=False)
    subdomain = Column(String(100), unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    sessions = relationship("WhatsAppSession", back_populates="tenant", cascade="all, delete-orphan")
    bots = relationship("Chatbot", back_populates="tenant", cascade="all, delete-orphan")
    kbs = relationship("KnowledgeBase", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(50), default="member")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="users")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    stripe_subscription_id = Column(String(255))
    razorpay_subscription_id = Column(String(255))
    razorpay_payment_id = Column(String(255))
    razorpay_order_id = Column(String(255))
    billing_cycle = Column(String(50), default="monthly")
    renewal_state = Column(String(50), default="auto")
    plan_tier = Column(String(50), default="free")
    status = Column(String(50), default="active")
    max_bots = Column(Integer, default=1)
    max_messages_per_month = Column(Integer, default=500)
    current_period_end = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class WhatsAppSession(Base):
    __tablename__ = "whatsapp_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    phone_number = Column(String(20))
    session_name = Column(String(100), nullable=False)
    status = Column(String(50), default="disconnected")
    qr_code = Column(Text)
    session_auth_data = Column(JSON)
    reconnect_attempts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="sessions")
    bots = relationship("Chatbot", back_populates="session")
    conversations = relationship("Conversation", back_populates="session", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="session")

class Chatbot(Base):
    __tablename__ = "chatbots"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("whatsapp_sessions.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    system_prompt = Column(Text, nullable=False)
    model_name = Column(String(100), default="qwen2.5:1.5b-instruct")
    temperature = Column(Float, default=0.4)
    rag_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="bots")
    session = relationship("WhatsAppSession", back_populates="bots")

class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="kbs")
    documents = relationship("KBDocument", back_populates="kb", cascade="all, delete-orphan")

class KBDocument(Base):
    __tablename__ = "kb_documents"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    kb_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512))
    status = Column(String(50), default="processing")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    kb = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("KBDocumentChunk", back_populates="document", cascade="all, delete-orphan")

class KBDocumentChunk(Base):
    __tablename__ = "kb_document_chunks"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    document_id = Column(UUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    # Stored as standard list/vector format. pgvector support via SQL operations.
    from sqlalchemy.types import UserDefinedType
    class VectorType(UserDefinedType):
        def get_col_spec(self, **kw):
            return "vector(384)"
    embedding = Column(VectorType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("KBDocument", back_populates="chunks")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("whatsapp_sessions.id", ondelete="CASCADE"), nullable=False)
    customer_phone = Column(String(30), nullable=False)
    customer_name = Column(String(255))
    is_archived = Column(Boolean, default=False)
    bot_paused_until = Column(DateTime(timezone=True), nullable=True)
    last_message_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="conversations")
    session = relationship("WhatsAppSession", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String(10), nullable=False)  # inbound, outbound
    sender_type = Column(String(20), nullable=False)  # user, bot, customer
    content = Column(Text, nullable=False)
    media_url = Column(String(512))
    media_type = Column(String(50))
    status = Column(String(50), default="queued")
    whatsapp_message_id = Column(String(100), unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("whatsapp_sessions.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    template_text = Column(Text, nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(50), default="scheduled")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tenant = relationship("Tenant", back_populates="campaigns")
    session = relationship("WhatsAppSession", back_populates="campaigns")
    logs = relationship("CampaignLog", back_populates="campaign", cascade="all, delete-orphan")

class CampaignLog(Base):
    __tablename__ = "campaign_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    recipient_phone = Column(String(30), nullable=False)
    status = Column(String(50), default="pending")
    error_message = Column(Text)
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))
    whatsapp_message_id = Column(String(100), unique=True, index=True, nullable=True)

    campaign = relationship("Campaign", back_populates="logs")

class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    chatbot_id = Column(UUID(as_uuid=True), ForeignKey("chatbots.id", ondelete="SET NULL"))
    tokens_used = Column(Integer, default=0)
    model_name = Column(String(100), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SubscriptionEvent(Base):
    __tablename__ = "subscription_events"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(String(255), unique=True, nullable=False)
    payment_id = Column(String(255))
    signature = Column(String(255))
    amount = Column(Integer, nullable=False)
    status = Column(String(50), default="created")
    plan_tier = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class TenantQuota(Base):
    __tablename__ = "tenant_quotas"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    max_bots = Column(Integer, default=1)
    max_messages = Column(Integer, default=500)
    bots_used = Column(Integer, default=0)
    messages_used = Column(Integer, default=0)
    reset_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class UsageMetric(Base):
    __tablename__ = "usage_metrics"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    metric_type = Column(String(100), nullable=False)
    quantity = Column(Integer, default=1)
    metric_metadata = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class BillingHistory(Base):
    __tablename__ = "billing_history"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("payment_transactions.id", ondelete="SET NULL"))
    amount = Column(Integer, nullable=False)
    plan_tier = Column(String(50), nullable=False)
    invoice_number = Column(String(100))
    paid_at = Column(DateTime(timezone=True), server_default=func.now())

class AutopayToken(Base):
    __tablename__ = "autopay_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    gateway = Column(String(50), default="razorpay")
    customer_id = Column(String(255), nullable=False)
    token_id = Column(String(255), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class RenewalJob(Base):
    __tablename__ = "renewal_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.uuid_generate_v4())
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="pending")
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    executed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
