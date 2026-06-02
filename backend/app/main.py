from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
from app.auth import router as auth_router
from app.routers import sessions, bots, chats, knowledge, campaigns, websockets, billing, admin, settings as settings_router, agents, bookings
from app.routers.billing import payments_router

from sqlalchemy import text

# Auto-create tables on container startup if migration manager is not initialized
try:
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS whatsapp_message_id VARCHAR(100) UNIQUE;"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS client_uuid UUID;"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS tenant_id UUID;"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS session_id UUID;"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS origin VARCHAR(50) DEFAULT 'outbound';"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS ack_state VARCHAR(50) DEFAULT 'queued';"))
        conn.execute(text("ALTER TABLE campaign_logs ADD COLUMN IF NOT EXISTS whatsapp_message_id VARCHAR(100) UNIQUE;"))
        conn.execute(text("ALTER TABLE conversations ALTER COLUMN customer_phone TYPE VARCHAR(100);"))
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS bot_paused_until TIMESTAMP WITH TIME ZONE;"))
        conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS razorpay_subscription_id VARCHAR(255);"))
        conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR(255);"))
        conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR(255);"))
        conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS billing_cycle VARCHAR(50) DEFAULT 'monthly';"))
        conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS renewal_state VARCHAR(50) DEFAULT 'auto';"))
        conn.execute(text("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS recurring_interval VARCHAR(50) DEFAULT 'none';"))
        
        # Phase 1: Google OAuth
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_email VARCHAR(255);"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_avatar VARCHAR(512);"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50) DEFAULT 'local';"))
        
        # Phase 2 & 7: Human Handoff & Memory
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS handoff_status VARCHAR(50) DEFAULT 'AI_ACTIVE';"))
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS assigned_agent_id UUID;"))
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_purchase VARCHAR(255);"))
        conn.execute(text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS lead_stage VARCHAR(50) DEFAULT 'cold';"))
        
        conn.commit()
    print("[FastAPI] Database structures synchronized successfully.")
except Exception as e:
    print("[FastAPI] Warning: DB sync encountered exception (checking tables exist):", e)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

# Robust CORS Configuration to support Frontend browser queries
import os

cors_origins = [
    "http://localhost:8080",
    "http://144.24.126.153:8080",
    "http://localhost:30000",
    "http://144.24.126.153:30000",
    "http://localhost:3000",
]

env_origins = os.getenv("CORS_ORIGINS", "")
if env_origins:
    cors_origins.extend([origin.strip() for origin in env_origins.split(",")])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount core routers
app.include_router(auth_router.router, prefix=settings.API_V1_STR)
app.include_router(sessions.router, prefix=settings.API_V1_STR)
app.include_router(bots.router, prefix=settings.API_V1_STR)
app.include_router(chats.router, prefix=settings.API_V1_STR)
app.include_router(knowledge.router, prefix=settings.API_V1_STR)
app.include_router(campaigns.router, prefix=settings.API_V1_STR)
app.include_router(websockets.router, prefix=settings.API_V1_STR)
app.include_router(billing.router, prefix=settings.API_V1_STR)
app.include_router(payments_router, prefix=settings.API_V1_STR)
app.include_router(admin.router, prefix=settings.API_V1_STR)
app.include_router(settings_router.router, prefix=settings.API_V1_STR)
app.include_router(agents.router, prefix=settings.API_V1_STR)
app.include_router(bookings.router, prefix=settings.API_V1_STR)

@app.get("/api/v1")
def home():
    return {
        "service": settings.PROJECT_NAME,
        "status": "online",
        "version": "1.0.0",
        "api_docs": "/api/v1/docs"
    }

@app.get("/api/v1/health")
def health_check():
    return {"status": "healthy"}
