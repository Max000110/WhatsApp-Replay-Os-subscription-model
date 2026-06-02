import asyncio
import time
from sqlalchemy import text
from app.database import SessionLocal
from app.config import settings
import redis
import httpx

async def test_health():
    print("--- Diagnostics Verification ---")
    
    # 1. PostgreSQL DB Status
    db_status = "offline"
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_status = "online"
        print("PostgreSQL: ONLINE")
    except Exception as e:
        print("PostgreSQL: OFFLINE", e)
    finally:
        db.close()
        
    # 2. Redis Cache Status
    redis_status = "offline"
    redis_ping_ms = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        start = time.time()
        r.ping()
        redis_ping_ms = int((time.time() - start) * 1000)
        redis_status = "online"
        print(f"Redis: ONLINE ({redis_ping_ms}ms)")
    except Exception as e:
        print("Redis: OFFLINE", e)
        
    # 3. WhatsApp Node Engine Status
    whatsapp_engine_status = "offline"
    active_sessions = 0
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.WHATSAPP_ENGINE_URL}/health", timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                whatsapp_engine_status = data.get("status", "healthy")
                active_sessions = data.get("activeSessions", 0)
                print(f"WhatsApp Engine: {whatsapp_engine_status.upper()} (Sessions: {active_sessions})")
            else:
                print(f"WhatsApp Engine: Degraded status {res.status_code}")
    except Exception as e:
        print("WhatsApp Engine: OFFLINE", e)
        
    # 4. Ollama AI Runtime status
    ai_status = "offline"
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.OLLAMA_HOST}/", timeout=3.0)
            if res.status_code == 200:
                ai_status = "online"
                print("Ollama AI: ONLINE")
            else:
                ai_status = "degraded"
                print(f"Ollama AI: DEGRADED status {res.status_code}")
    except Exception as e:
        print("Ollama AI: OFFLINE", e)
        
    # 5. WebSockets Realtime status
    from app.core.websocket import websocket_manager
    active_ws_tenants = len(websocket_manager.active_connections)
    active_ws_sockets = sum(len(conns) for conns in websocket_manager.active_connections.values())
    print(f"WebSockets: Tenants: {active_ws_tenants}, Connections: {active_ws_sockets}")
    
    # 6. Celery Worker Queue status
    celery_status = "offline"
    celery_queue_size = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        celery_queue_size = r.llen("celery")
        
        from worker.celery_app import celery
        inspect = celery.control.inspect(timeout=2.0)
        active_workers = inspect.ping()
        if active_workers:
            celery_status = "online"
        print(f"Celery Workers: {celery_status.upper()} (Queue: {celery_queue_size}) (Workers response: {active_workers})")
    except Exception as e:
        print("Celery Workers: OFFLINE", e)

if __name__ == "__main__":
    asyncio.run(test_health())
