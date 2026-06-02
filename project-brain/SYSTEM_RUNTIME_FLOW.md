# SYSTEM RUNTIME FLOWS — ReplyOS

This document details the E2E runtime execution flows across the React/Next.js frontend, the FastAPI backend, the Baileys WhatsApp Node Engine, the PostgreSQL/pgvector database, the Redis message queue, and the Ollama AI inference engine.

---

## 1. Frontend Execution Flow (UI to API Gateway)

```mermaid
sequenceDiagram
    autonumber
    actor User as Client / Administrator
    participant UI as Next.js (Port 3000)
    participant Nginx as saas_nginx (Port 8080)
    participant API as FastAPI Backend (Port 8000)

    User->>UI: Interacts with Dashboard / Admin Panel
    UI->>UI: Client-Side State validation / Auth Check (JWT)
    UI->>Nginx: HTTP Request (e.g., GET /api/v1/bots)
    Note over Nginx: Dynamic Upstream DNS Resolution (Docker 127.0.0.11)<br/>Rate Limiting (10 req/s, burst=20)
    Nginx->>API: Proxy Forward to http://backend:8000/api/v1/bots
    API-->>Nginx: Returns JSON Response (HTTP 200/400/403)
    Nginx-->>UI: Proxy response back
    UI-->>User: Render state update (React transition)
```

---

## 2. Backend Routing Flow (Request Processing Pipeline)

When FastAPI receives a request:

```mermaid
graph TD
    A[Incoming HTTP Request] --> B{Nginx Proxy Gateway}
    B -->|Route Check| C[FastAPI Uvicorn Handler]
    C --> D[Auth Middleware / JWT Validation]
    D -->|Invalid Token / Expired| E[HTTP 401 Unauthorized]
    D -->|Valid JWT Scope checks| F[Tenant Identity Extraction]
    F --> G{Is Protected Tenant / System Operations?}
    G -->|Yes & Destructive Request| H[HTTP 400 Bad Request Safeguard]
    G -->|No / Safe Read Request| I[Session Router Activation]
    I --> J[AI Service & pgvector Lookup]
    J --> K[PostgreSQL Schema Transaction]
    K --> L[HTTP Response Return]
```

---

## 3. End-to-End AI Routing Flow (Webhook to LLM Response)

This flowchart illustrates the AI reasoning path starting from an incoming WhatsApp webhook:

```mermaid
graph TD
    A[Incoming WhatsApp Message] --> B[whatsapp-engine Webhook Dispatch]
    B --> C[FastAPI sessions.py Webhook Endpoint]
    C --> D[Session Router & Tenant Lookup]
    D --> E[Is User JID Blacklisted / Bot Paused?]
    E -->|Yes| F[Ignore message / Operator Mode]
    E -->|No| G[Fetch Chatbot Configuration]
    G --> H[Retrieve Sentiment & Memory History]
    H --> I[Retrieve pgvector RAG Knowledge Base Docs]
    I --> J[15-Layer Prompt Builder Assembly]
    J --> K[Model Router Endpoint Check]
    K --> L{Select Model / Ollama / OpenRouter}
    L -->|Ollama local| M[Local Inference saas_ollama:11434]
    L -->|OpenRouter remote| N[Remote Inference Request]
    M --> O[Generate Chatbot Response String]
    N --> O
    O --> P[Durable Response Formatting]
```

---

## 4. WhatsApp Message Pipeline & Anti-Ban Flow

Tracks incoming data payloads, queuing dispatches via the Anti-Ban Redis list, and outbound delivery status updates:

```mermaid
sequenceDiagram
    autonumber
    actor Customer as WhatsApp Client
    participant Engine as saas_whatsapp_engine
    participant Backend as saas_backend
    participant Redis as saas_redis (AntiBanQueue)

    Customer->>Engine: Send WhatsApp Message (Socket)
    Engine->>Backend: Webhook Post /api/v1/sessions/webhook (JID normalized)
    Backend->>Backend: AI Pipeline Processing (Prompt compiled -> Inference)
    Backend->>Redis: Queue response in whatsapp_queue_{session_id}
    Note over Engine: Anti-Ban Queue Worker actively polling Redis
    Redis-->>Engine: Pop response payload
    Note over Engine: Apply random human delay (2s to 5s)
    Engine->>Customer: Socket Send Message (Durable delivery)
    Customer-->>Engine: Message Received (ACK Status = delivered)
    Engine->>Backend: POST Webhook Status Callback (delivered/read)
    Backend->>Backend: Mutate Postgres Message ACK State
```
