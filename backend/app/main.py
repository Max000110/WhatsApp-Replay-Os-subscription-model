from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
from app.auth import router as auth_router
from app.routers import sessions, bots, chats, knowledge, campaigns

# Auto-create tables on container startup if migration manager is not initialized
try:
    Base.metadata.create_all(bind=engine)
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
