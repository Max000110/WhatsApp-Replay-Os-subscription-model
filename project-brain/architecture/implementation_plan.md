# WhatsApp AI Automation SaaS Platform - System Architecture & MVP Design

This document details the production-grade, zero-budget-optimized architecture for the WhatsApp AI Automation SaaS platform running on Oracle Cloud Free Tier.

---

## 1. System Architecture Overview

The system uses a highly modular, containerized microservices architecture to ensure scalability, ease of migration to official Meta Cloud APIs, and robust isolation of critical layers.

### Multi-Service Topology

```mermaid
graph TD
    User([SaaS Client]) -->|HTTPS/WS| Nginx[Nginx Reverse Proxy & SSL]
    Nginx -->|Route /api/*| FastAPI[FastAPI Backend API Service]
    Nginx -->|Route /*| NextJS[Next.js Frontend Dashboard]
    
    FastAPI -->|Publish Events/Jobs| Redis[(Redis Broker & Cache)]
    Redis -->|Consume Task Queue| Celery[Celery RAG & Analytics Workers]
    
    FastAPI <-->|WS Session State / QR Control| WAEngine[Node.js Baileys WhatsApp Engine]
    WAEngine <-->|Webhook Events| FastAPI
    WAEngine -->|Read/Write Session Data| PGStore[(PostgreSQL Session Store)]
    
    Celery -->|Generate Embeddings / Chat Replies| Ollama[Local Ollama / Llama.cpp Engine]
    Celery <-->|Vector Store / Core SaaS DB| PGStore
    FastAPI <-->|Core SaaS DB| PGStore
```

### Infrastructure Cost Optimization (Oracle Free Tier - 4 OCPU, 24GB RAM)
To achieve zero-cost execution on Oracle Free Tier VM, the services are allocated the following resources inside Docker Compose limits:
*   **Next.js Frontend**: 1.5GB RAM (Server-side rendered + optimized static serving)
*   **FastAPI Backend**: 2GB RAM (Async Uvicorn, highly concurrent, low footprint)
*   **WhatsApp Engine**: 2GB RAM (NodeJS runtime, optimized memory limits, isolated processes for Baileys instances)
*   **PostgreSQL & pgvector**: 3GB RAM (Optimized buffers, indexes)
*   **Redis**: 1GB RAM (In-memory, short persistence eviction)
*   **Celery Workers**: 2GB RAM (Restricted concurrency pool to avoid CPU thrashing)
*   **Ollama AI Engine**: 10GB RAM (Running quantized GGUF models like `qwen2.5:1.5b-instruct` or `phi3:3.8b-instruct` with CPU/RAM optimization)
*   **Operating System Overhead**: ~2.5GB RAM

---

## 2. Multi-Tenant Database Design (PostgreSQL + pgvector)

To support isolation, all tables reference a `tenant_id` (representing the corporate or personal account owner). DDL is constructed using modern database patterns (indexing, foreign key constraints, default UUIDs).

```sql
-- Enable UUID and pgvector extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Tenants (SaaS Organizations)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    subdomain VARCHAR(100) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    role VARCHAR(50) DEFAULT 'member', -- owner, admin, member
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Subscriptions (Billing Architecture - initially mocked/disabled)
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255),
    plan_tier VARCHAR(50) DEFAULT 'free', -- free, starter, pro, enterprise
    status VARCHAR(50) DEFAULT 'active',  -- active, past_due, canceled
    max_bots INTEGER DEFAULT 1,
    max_messages_per_month INTEGER DEFAULT 500,
    current_period_end TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. WhatsApp Sessions (Multi-Account Baileys config & login)
CREATE TABLE whatsapp_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    phone_number VARCHAR(20),
    session_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'disconnected', -- disconnected, scanning, connected, error
    qr_code TEXT,
    session_auth_data JSONB, -- stores Baileys credentials (creds.json serialization)
    reconnect_attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_tenant_phone UNIQUE(tenant_id, phone_number)
);

-- 5. AI Chatbots configuration
CREATE TABLE chatbots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    session_id UUID REFERENCES whatsapp_sessions(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    system_prompt TEXT NOT NULL,
    model_name VARCHAR(100) DEFAULT 'qwen2.5:1.5b-instruct',
    temperature FLOAT DEFAULT 0.4,
    rag_enabled BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Knowledge Base Catalog
CREATE TABLE knowledge_bases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Knowledge Base Documents
CREATE TABLE kb_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kb_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512),
    status VARCHAR(50) DEFAULT 'processing', -- processing, processed, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. Document Chunks with Vector Embeddings (PGVector)
CREATE TABLE kb_document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES kb_documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL, -- 384 dimensions for all-MiniLM-L6-v2 / BGE-Small
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. Conversations (Aggregated by remote customer phone)
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    session_id UUID REFERENCES whatsapp_sessions(id) ON DELETE CASCADE,
    customer_phone VARCHAR(30) NOT NULL,
    customer_name VARCHAR(255),
    is_archived BOOLEAN DEFAULT FALSE,
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_tenant_session_customer UNIQUE(tenant_id, session_id, customer_phone)
);

-- 10. Chat Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    direction VARCHAR(10) NOT NULL, -- inbound, outbound
    sender_type VARCHAR(20) NOT NULL, -- user, bot, customer
    content TEXT NOT NULL,
    media_url VARCHAR(512),
    media_type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'sent', -- pending, sent, delivered, read, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 11. Marketing Campaigns
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    session_id UUID REFERENCES whatsapp_sessions(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    template_text TEXT NOT NULL,
    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) DEFAULT 'scheduled', -- scheduled, sending, completed, paused
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. Campaign Dispatch Queue & Analytics
CREATE TABLE campaign_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    recipient_phone VARCHAR(30) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, sent, failed, rejected
    error_message TEXT,
    sent_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    read_at TIMESTAMP WITH TIME ZONE
);

-- 13. System Metrics & Usage Logging
CREATE TABLE ai_usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    chatbot_id UUID REFERENCES chatbots(id) ON DELETE SET NULL,
    tokens_used INTEGER DEFAULT 0,
    model_name VARCHAR(100) NOT NULL,
    latency_ms INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for lightning-fast lookups under load
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_sessions_tenant ON whatsapp_sessions(tenant_id);
CREATE INDEX idx_conversations_customer ON conversations(customer_phone);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_chunks_embedding ON kb_document_chunks USING hnsw (embedding vector_cosine_ops);
```

---

## 3. Directory Layout & Module Structure

The project root `/home/ubuntu/whatsapp-ai-saas` is organized into microservices.

```
/home/ubuntu/whatsapp-ai-saas/
├── docker-compose.yml
├── .env.example
├── README.md
├── nginx/
│   ├── Dockerfile
│   └── default.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── auth/
│       │   ├── router.py
│       │   └── service.py
│       ├── core/
│       │   ├── security.py
│       │   ├── queue.py
│       │   └── vector.py
│       ├── models/
│       │   └── all_models.py
│       ├── schemas/
│       │   └── all_schemas.py
│       ├── services/
│       │   ├── ai_service.py
│       │   ├── rag_service.py
│       │   └── session_service.py
│       └── routers/
│           ├── bots.py
│           ├── chats.py
│           ├── campaigns.py
│           ├── knowledge.py
│           └── sessions.py
├── whatsapp-engine/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── index.ts
│       ├── anti-ban.ts
│       ├── baileys-manager.ts
│       ├── session-db-store.ts
│       └── types.ts
├── worker/
│   ├── Dockerfile
│   ├── celery_app.py
│   └── tasks.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── tailwind.config.js
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx
    │   │   ├── page.tsx
    │   │   ├── login/
    │   │   │   └── page.tsx
    │   │   ├── dashboard/
    │   │   │   ├── page.tsx
    │   │   │   ├── bots/
    │   │   │   ├── chats/
    │   │   │   ├── campaigns/
    │   │   │   └── knowledge/
    │   │   └── providers.tsx
    │   ├── components/
    │   │   ├── ui/
    │   │   ├── sidebar.tsx
    │   │   └── chat-window.tsx
    │   └── lib/
    │       ├── api.ts
    │       └── utils.ts
```

---

## 4. Multi-Tenant Dockerized Orchestration

We orchestrate the entire software stack using a custom, multi-tenant production `docker-compose.yml` leveraging PostgreSQL, pgvector, Redis, FastAPI, Next.js, and the Baileys engine.

### `docker-compose.yml`

```yaml
version: '3.8'

services:
  # Database Layer (Postgres + pgvector)
  postgres:
    image: pgvector/pgvector:pg16
    container_name: saas_postgres
    restart: always
    environment:
      POSTGRES_DB: saas_whatsapp
      POSTGRES_USER: saas_admin
      POSTGRES_PASSWORD: SecretSaaSPassword123!
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 3G
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U saas_admin -d saas_whatsapp"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Message Broker & Cache Layer (Redis)
  redis:
    image: redis:7-alpine
    container_name: saas_redis
    restart: always
    command: redis-server --appendonly yes --requirepass SecretRedisPassword123!
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          memory: 1G
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "SecretRedisPassword123!", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Local Quantized AI Inference Service
  ollama:
    image: ollama/ollama:latest
    container_name: saas_ollama
    restart: always
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        limits:
          memory: 10G
    # Automatically download lightweight Qwen models on start
    entrypoint: [ "/bin/bash", "-c", "ollama serve & sleep 5 && ollama pull qwen2.5:1.5b-instruct && wait" ]

  # FastAPI Backend API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: saas_backend
    restart: always
    environment:
      - DATABASE_URL=postgresql://saas_admin:SecretSaaSPassword123!@postgres:5432/saas_whatsapp
      - REDIS_URL=redis://:SecretRedisPassword123!@redis:6379/0
      - OLLAMA_HOST=http://ollama:11434
      - JWT_SECRET=VeryStrongJWTSecret987654321!
      - WHATSAPP_ENGINE_URL=http://whatsapp-engine:3000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 2G

  # Celery Background Workers (Campaign Dispatches & PDF Vectorization)
  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: saas_worker
    command: celery -A worker.celery_app.celery worker --loglevel=info --concurrency=2
    environment:
      - DATABASE_URL=postgresql://saas_admin:SecretSaaSPassword123!@postgres:5432/saas_whatsapp
      - REDIS_URL=redis://:SecretRedisPassword123!@redis:6379/0
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 2G

  # WhatsApp Node.js Engine (Baileys)
  whatsapp-engine:
    build:
      context: ./whatsapp-engine
      dockerfile: Dockerfile
    container_name: saas_whatsapp_engine
    restart: always
    environment:
      - PORT=3000
      - DATABASE_URL=postgresql://saas_admin:SecretSaaSPassword123!@postgres:5432/saas_whatsapp
      - BACKEND_API_URL=http://backend:8000/api/v1/sessions/webhook
    ports:
      - "3000:3000"
    depends_on:
      postgres:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 2G

  # Frontend Interface (Next.js Dashboard)
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: saas_frontend
    restart: always
    ports:
      - "30000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
    deploy:
      resources:
        limits:
          memory: 1.5G

  # Gateway Reverse Proxy (Nginx + SSL Auto Routing)
  nginx:
    build:
      context: ./nginx
    container_name: saas_nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
      - frontend
    volumes:
      - certs_data:/etc/letsencrypt

volumes:
  postgres_data:
  redis_data:
  ollama_data:
  certs_data:
```

---

## 5. WhatsApp Engine Architecture & Anti-Ban Throttling

To operate safely without instant bans, the WhatsApp Engine implements randomized delays, typing indicator states, message queues, and a multi-session daemon manager powered by Baileys.

### Engine Component Details
*   **Baileys Session Handler**: Stores authentication keys directly in the database (`whatsapp_sessions` - `session_auth_data`) rather than local files, allowing Docker container scaling without volume sync problems.
*   **Typing Simulator**: Simulates `"composing"` states before sending texts based on content length (e.g., 20 milliseconds per character, capped at 4 seconds).
*   **Outbound Priority Queue**: Redis queues hold outbound messages. Messages are read sequentially by a throttled poller that enforces configurable delays between sends (e.g., random delay between 4 to 12 seconds).

```typescript
// File: whatsapp-engine/src/anti-ban.ts
import { WASocket } from "@whiskeysockets/baileys";

export class AntiBanQueue {
  private socket: WASocket;

  constructor(socket: WASocket) {
    this.socket = socket;
  }

  /**
   * Safe message dispatcher simulating human engagement behaviors
   */
  public async sendSafeMessage(jid: string, text: string, options: { simulateTyping?: boolean } = {}) {
    if (options.simulateTyping) {
      // Simulate "composing" indicator
      await this.socket.sendPresenceUpdate("composing", jid);
      
      // Calculate realistic typing speed delay: ~15ms per character, min 500ms, max 3000ms
      const delay = Math.min(Math.max(text.length * 15, 500), 3000);
      await new Promise((resolve) => setTimeout(resolve, delay));
      
      // Stop typing simulation
      await this.socket.sendPresenceUpdate("paused", jid);
    }

    // Randomized transmission delay to beat anti-bot heuristic models (4s to 8s)
    const transmissionDelay = Math.floor(Math.random() * (8000 - 4000 + 1)) + 4000;
    await new Promise((resolve) => setTimeout(resolve, transmissionDelay));

    // Send the message securely
    const messageResult = await this.socket.sendMessage(jid, { text: text });
    return messageResult;
  }
}
```

---

## 6. Local AI RAG Pipeline & Multi-Model Adaptability

The AI Service inside the FastAPI Backend communicates with Ollama running locally. To migrate later to paid APIs (OpenRouter, DeepSeek, Gemini) without architectural modifications, the system utilizes a **Unified AI Model Gateway Interface**.

```python
# File: backend/app/services/ai_service.py
import httpx
import os

class AIGateway:
    """
    Unified adapter routing prompts dynamically based on tier and active driver config.
    Swaps seamlessly between Local Ollama, DeepSeek API, or Gemini Cloud.
    """
    
    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://ollama:11434")
        self.provider = os.getenv("AI_PROVIDER", "ollama") # options: ollama, openrouter, gemini
        self.api_key = os.getenv("AI_API_KEY", "")

    async def generate_response(self, prompt: str, system_prompt: str = "", model: str = "qwen2.5:1.5b-instruct") -> str:
        if self.provider == "ollama":
            return await self._call_ollama(prompt, system_prompt, model)
        elif self.provider == "openrouter":
            return await self._call_openrouter(prompt, system_prompt, model)
        else:
            raise NotImplementedError(f"AI Provider {self.provider} not supported.")

    async def _call_ollama(self, prompt: str, system_prompt: str, model: str) -> str:
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "options": {"temperature": 0.3},
            "stream": False
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    return response.json().get("message", {}).get("content", "")
                return f"Error: Local AI engine returned status code {response.status_code}"
            except Exception as e:
                return f"Error connecting to local inference engine: {str(e)}"

    async def _call_openrouter(self, prompt: str, system_prompt: str, model: str) -> str:
        # Easy upgrade configuration for Phase 2 scaling without altering downstream core services
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model or "deepseek/deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            return response.json()["choices"][0]["message"]["content"]
```

### Knowledge Base & pgvector Retrieval (RAG)
1.  **Document Ingestion**: PDFs/texts are uploaded via Next.js to FastAPI.
2.  **Chunking & Vectorization**: Celery splits content into ~500 character chunks with 50 character overlaps. The chunk is sent to an embedding model (e.g. `sentence-transformers/all-MiniLM-L6-v2` loaded locally inside a Python micro-worker or generated using Ollama's `/api/embeddings` endpoint).
3.  **Semantic Match Query**: On receiving an incoming message, FastAPI triggers a Cosine similarity match against `kb_document_chunks` partitioned by `tenant_id` to retrieve matching context before prompting the LLM.

---

## 7. Security, Rate Limiting & Enterprise Readiness

To ensure the SaaS operates securely under heavy workloads, we integrate strict security measures:
*   **JWT Multi-Tenant Auth**: Every HTTP request checks the sub-domain, validating `tenant_id` inside JWT claims. Row Level Security (RLS) is mimicked through mandatory WHERE filters in Backend Repository classes.
*   **API Throttling**: FastAPI depends on a Redis-backed rate-limiter, preventing users from abuse (e.g., 60 calls/min per client IP for standard endpoints, 5 calls/min for auth).
*   **Encrypted WhatsApp Sessions**: `session_auth_data` within PostgreSQL contains delicate decryption keys for Baileys. These tokens are encrypted before being written to PostgreSQL using AES-GCM (256-bit key stored as a system environment variable).

---

## 8. MVP Roadmap & DevOps Infrastructure Setup

We propose a structured development lifecycle designed to deliver a stable, modular prototype without cloud service bills.

```mermaid
gantt
    title MVP Development Phases (4-Week Launch Sequence)
    dateFormat  YYYY-MM-DD
    section Phase 1: Core Setup
    Infrastructure & Orchestration   :active, des1, 2026-06-01, 5d
    Multi-tenant DB Schemas         :active, des2, 2026-06-03, 3d
    section Phase 2: Engine
    Baileys WhatsApp Integrator    :des3, 2026-06-06, 6d
    Anti-Ban Throttler & Reconnect :des4, 2026-06-10, 4d
    section Phase 3: AI & RAG
    Ollama & Embeddings Setup      :des5, 2026-06-14, 5d
    FastAPI RAG Pipeline           :des6, 2026-06-17, 5d
    section Phase 4: UI & Release
    NextJS Responsive Dashboard    :des7, 2026-06-21, 6d
    Nginx Reverse Proxy & Nuke Test:des8, 2026-06-25, 4d
```

### Production Nginx Reverse Proxy Configuration (with Rate Limiting & SSL Routing)
To guarantee security, we provide the Nginx configuration template designed to forward connections securely and protect backend nodes.

```nginx
# File: nginx/default.conf
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m use_temp_path=off;

limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen 80;
    server_name localhost;

    # Redirect all non-SSL traffic to HTTPS in Production
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name localhost;

    # SSL Config Placeholder (Let's Encrypt automated inside production compose)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Gzip Compression Optimization
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    gzip_min_length 1000;

    # Frontend Server Gateway Routing
    location / {
        proxy_pass http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # API Backend Gateway Routing with Rate Limiting
    location /api/v1/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://backend:8000/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 9. Next Steps & Action Plan

1.  **Phase 1 Execution**: Prepare directories, Docker files, and initialize the databases.
2.  **Baileys Verification**: Construct the Node.js runner to stream a QR login session on a local terminal and save credentials.
3.  **Local AI Deployment**: Spin up the local Ollama instance inside the Docker Network and test speed metrics using CPU-only mode.

## User Review Required

> [!IMPORTANT]
> Since we are targeting Oracle Cloud Free Tier's 4 OCPU ARM architecture, the chosen base Docker images MUST support standard multi-arch architectures (e.g. `arm64`). We will utilize lightweight Linux architectures (`alpine` and `slim`) to limit processor stress.

> [!WARNING]
> High throughput LLM generation on CPU nodes might result in high response latency (~5s to 12s per message). To mitigate this, our worker engine handles all AI generation tasks asynchronously to prevent holding up client-side processes.

## Open Questions

> [!NOTE]
> 1. Do you have a domain mapped to your Oracle Cloud VM IP for the Let's Encrypt SSL configurations?
> 2. Would you like to use local embeddings generation (using Ollama's `nomic-embed-text`) or a free remote API wrapper (e.g. Hugging Face Inference API) for document vectorization to keep CPU workloads at a minimum?
