# System Walkthrough & Handoff: WhatsApp AI SaaS Platform

This document summarizes the complete implementation of our multi-tenant, production-grade WhatsApp AI Automation SaaS platform optimized for zero-cost execution on Oracle Cloud Free Tier.

---

## 1. Codebase Directory Map

All modules have been created under `/home/ubuntu/whatsapp-ai-saas/`:

```
/home/ubuntu/whatsapp-ai-saas/
├── docker-compose.yml              # Main docker coordinator
├── .env                            # Environment configurations
├── .env.example                    # Env configurations template
├── postgres-init/
│   └── init.sql                    # pgvector multi-tenant schema DDL
├── nginx/
│   ├── Dockerfile                  # Reverse proxy image
│   └── default.conf                # Gzip, rate limit & route mappings
├── whatsapp-engine/
│   ├── Dockerfile                  # Node engine image
│   ├── package.json                # Dependencies configuration
│   ├── tsconfig.json               # TS configuration
│   └── src/
│       ├── index.ts                # Express gateway listener
│       ├── types.ts                # Type boundaries
│       ├── anti-ban.ts             # Composing simulator & queue
│       ├── session-db-store.ts     # Stateless Postgres creds store
│       └── baileys-manager.ts      # Multi-instance Baileys socket pool
├── backend/
│   ├── Dockerfile                  # FastAPI image
│   ├── requirements.txt            # Python dependencies
│   ├── app/
│   │   ├── main.py                 # FastAPI app orchestrator
│   │   ├── config.py               # Constants configurations
│   │   ├── database.py             # SQLAlchemy session builder
│   │   ├── core/
│   │   │   └── security.py         # Bcrypt & JWT tokens signer
│   │   ├── auth/
│   │   │   ├── router.py           # Multi-tenant registrations
│   │   │   └── service.py          # Scope auth filters
│   │   ├── models/
│   │   │   └── all_models.py       # DB schemas matching SQL DDL
│   │   ├── schemas/
│   │   │   └── all_schemas.py      # Pydantic validation scopes
│   │   ├── services/
│   │   │   ├── ai_service.py       # Ollama AI model gateway
│   │   │   ├── rag_service.py      # pgvector similarity searches
│   │   │   └── session_service.py  # WhatsApp engine integrator
│   │   └── routers/
│   │       ├── sessions.py         # Bot webhook message logic
│   │       ├── bots.py             # Bots CRUD panel
│   │       ├── chats.py            # Live agent overrides JID send
│   │       ├── campaigns.py        # Marketing schedules
│   │       └── knowledge.py        # PDF RAG file uploads
│   └── worker/
│       ├── __init__.py             # Module marker
│       ├── celery_app.py           # Redis task broker setup
│       └── tasks.py                # Ingestion PDF & campaign dispatches
└── frontend/
    ├── Dockerfile                  # Next.js image
    ├── package.json                # Front dependencies
    ├── tsconfig.json               # TS parameters
    ├── tailwind.config.js          # Dark theme colors config
    ├── postcss.config.js           # PostCSS compiler config
    ├── next.config.js              # Next compiler rules
    └── src/
        ├── lib/
        │   └── api.ts              # Fetch request client
        └── app/
            ├── globals.css         # Tailwind loaders
            ├── layout.tsx          # Global HTML template
            ├── page.tsx            # Redirection gatekeeper
            ├── login/
            │   └── page.tsx        # Modern dynamic auth forms
            └── dashboard/
                └── page.tsx        # High-premium SaaS workspace
```

---

## 2. Dynamic Component Architectures

### stateless Multi-Session credentials Store
By default, the `@whiskeysockets/baileys` library serializes authentication states to local files. To achieve high availability and container independence:
1.  **State Serializer**: The [session-db-store.ts](file:///home/ubuntu/whatsapp-ai-saas/whatsapp-engine/src/session-db-store.ts) uses Baileys' `BufferJSON.replacer` and `BufferJSON.reviver` to transform socket credentials (containing dynamic prekeys and E2E keys) into plain JSON.
2.  **Stateless Sync**: The state updates are written back directly to the `session_auth_data` column in the PostgreSQL table `whatsapp_sessions`. On crash or scaling, the new container pulls the authentication payload, restoring JID sessions without QR rescans.

### Anti-Ban queue & Human Composing Simulator
To minimize WhatsApp automated bot blockages:
1.  **Typing Latency**: The [anti-ban.ts](file:///home/ubuntu/whatsapp-ai-saas/whatsapp-engine/src/anti-ban.ts) service evaluates text length (length * 20 milliseconds) and triggers a `"composing"` socket indicator before switching to `paused` and sending the message.
2.  **Queue Jitter Throttling**: Messages are pushed to Redis. A poller reads them sequentially and injects randomized delays (4s to 8s) to disrupt rigid automation fingerprints.

### pgvector Semantic RAG search (all-minilm)
To support localized context answering without OpenAI bills:
1.  **Ingestion PDF Task**: The Celery task in [tasks.py](file:///home/ubuntu/whatsapp-ai-saas/backend/worker/tasks.py) chunks document pages, makes a vectorization call to local Ollama (pulling `all-minilm`), and inserts the vector representation into Postgres.
2.  **pgvector Matching**: When a customer sends a message, FastAPI triggers a raw Cosine similarity search (`<=>`) against `kb_document_chunks` scoped strictly by the chatbot organization tenant:
    ```sql
    SELECT content, embedding <=> :vector_str AS distance
    FROM kb_document_chunks chunk
    JOIN kb_documents doc ON chunk.document_id = doc.id
    WHERE doc.kb_id = :kb_id
    ORDER BY distance ASC LIMIT 3;
    ```
3.  **Local LLM Prompt Injection**: The resulting chunks are concatenated as verifiable facts in the system prompt before calling Qwen-Coder or Phi-3.

---

## 3. How to Launch & Spin Up (Step-by-Step Commands)

To run the entire system on your Oracle Cloud VM:

### Step 1: Install Docker & Docker-Compose (if not already set up)
Ensure Docker daemon is active on your Ubuntu VM:
```bash
sudo apt update && sudo apt install -y docker.io docker-compose
```

### Step 2: Open Ports in VM & Oracle Cloud Subnet Rules
To access Nginx and API routes, open Ports 80, 443, 8000, and 30000 in your VM firewalls:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 30000/tcp
```

### Step 3: Spin Up Containers in Background Mode
Navigate to your project root and start the orchestration:
```bash
cd /home/ubuntu/whatsapp-ai-saas
docker-compose up --build -d
```

### Step 4: Monitor Log Progress
Watch models download progress inside Ollama (`all-minilm` + `qwen2.5:1.5b`):
```bash
docker logs -f saas_ollama
```

Verify that all service containers are healthy and running:
```bash
docker ps
```

---

## 4. Scaling & Enterprise Upgrades Strategy
When moving from free limits to enterprise environments:
*   **API Swapping**: Seamlessly toggle the `AI_PROVIDER` flag inside `.env` from `ollama` to `openrouter` (with your custom token) to route LLM pipelines to Groq/Claude/Gemini/DeepSeek instantly.
*   **Meta Cloud API Migration**: The engine acts as a webhook parser. Swap out the Baileys socket hooks inside `baileys-manager.ts` and point outbound dispatches to standard Meta endpoint payloads. The core database schema and conversation loops will remain intact.
*   **Active Worker Clusters**: Move Celery workers to independent CPU instances and utilize Amazon RDS / Supabase for Postgres pooling.
