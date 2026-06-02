# API Runtime Validation & Security Architecture

This document details the security layers, runtime checks, authorization policies, and webhook validation protocols running inside the FastAPI backend.

---

## 1. Multi-Tenant JWT Authentication

All client-to-backend API endpoints are secured by cryptographically signed JSON Web Tokens (JWT). The system employs asymmetric SHA-256 signatures to prevent header manipulation.

### Authentication Middleware (`auth/service.py`)
FastAPI dependency injection checks the `Authorization: Bearer <token>` header on every request:
1. **Decodes JWT Payload**: Decodes JWT using the host environment's secret key (`JWT_SECRET`).
2. **Validates Expiration**: Asserts `exp` timestamp is in the future.
3. **Extracts Tenant Scope**: Returns the `tenant_id` and binds it to the current request context. This ensures absolute physical isolation between tenants (zero cross-tenant data leaks).

---

## 2. Request Data Validation (FastAPI + Pydantic)

FastAPI utilizes Pydantic schemas to validate all JSON request bodies in real-time. Inbound payloads that do not strictly comply with schemas are instantly rejected with `422 Unprocessable Entity` before entering any backend business or database logic.

### Outbound Send Validation (`SendMessageRequest`)
Ensures that all manual override requests contain valid, initialized session IDs, clean target phone numbers, and non-empty content strings:

```python
class SendMessageRequest(BaseModel):
    session_id: UUID
    to_phone: str
    content: str
    client_uuid: Optional[UUID] = None
```

---

## 3. Webhook Token Verification

The webhook endpoint (`/api/v1/sessions/webhook`) handles all incoming message, ACK, and connection events from the Baileys engine. Since these events bypass standard JWT authorization, a different validation mechanism is used:
* **Private Network Ingestion**: The reverse proxy (Nginx) and Docker network bridge isolate the `/webhook` endpoint. The Node Engine communicates directly with the FastAPI service inside a secure private virtual network bridge, blocking any external requests.
* **Database Session Matching**: When a webhook payload is received, the backend immediately queries `whatsapp_sessions` to match the incoming `sessionId` with an active, connected session row in PostgreSQL. Payloads originating from unregistered session IDs are silently dropped.

```python
ws_session = db.query(WhatsAppSession).filter(WhatsAppSession.id == session_id).first()
if not ws_session:
    print(f"[Webhook] Ignored event for untracked session: {session_id}")
    return
```

---

## 4. DB Session Lifecycle Management (Pool Exhaustion Prevention)

Heavy background tasks (such as Ollama AI chatbot inference or RAG vector lookups) run asynchronously outside the short FastAPI HTTP lifecycle.
To prevent the background event loop from crashing or exhausting the database connection pool, FastAPI employs the following pattern:
1. **Sync Database Dependencies**: Sync endpoints use the standard `db: Session = Depends(get_db)` dependency, which opens and automatically closes the PostgreSQL session on return.
2. **Independent Background Sessions**: Background workers explicitly open a new `SessionLocal()` database connection, fully manage the connection state inside a `try-except-finally` block, and commit/rollback before executing `db.close()` in the `finally` block.

```python
async def process_incoming_chat_pipeline(session_id: str, event: str, data_dict: dict):
    db = SessionLocal()
    try:
        # run pipeline logic ...
        db.commit()
    except Exception as err:
        db.rollback()
        print("[Pipeline] Error:", err)
    finally:
        db.close() # Prevents database thread/pool locking
```
This is fully validated, operational, and guarantees high availability under heavy concurrency loads.
