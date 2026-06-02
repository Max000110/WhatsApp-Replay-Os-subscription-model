# ReplyOS — WhatsApp Pipeline & Messaging Lifecycle

This document describes the inbound webhook parsing, Celery background tasks, and outbound manual override processes mapping the WhatsApp messaging lifecycle.

---

## 1. Flow Diagram (Inbound & Outbound Pipeline)

```
INBOUND FLOW:
[Customer Phone] ──► [WhatsApp Network] ──► [Baileys Node Engine] ──► [FastAPI Webhook Router]
                                                                                │
                                           ┌────────────────────────────────────┘
                                           ▼
                                [process_ai_reply_task] ──► [Ollama LLM (Qwen)]
                                           │
                                           ▼
                                 [POST /sessions/send] ──► [Baileys Node Engine] ──► [Customer Phone]

OUTBOUND OVERRIDE FLOW:
[Next.js Chat UI] ──► [POST /chats/send] ──► [FastAPI Router]
                                                  │ (Sets `bot_paused_until` + optimistic DB insert)
                                                  ▼
                                        [POST /sessions/send] ──► [Baileys Node Engine] ──► [Customer]
```

---

## 2. Inbound Message Processing Steps

1. **Baileys Event Triggers**:
   - The recipient cell transmits an inbound text message. The Node.js companion engine parses the standard `messages.upsert` socket event.
   - Node triggers an HTTP POST callback carrying the raw JID and text payload to the FastAPI gateway endpoint: `/api/v1/sessions/webhook`.

2. **Ingestion & DB Insertion**:
   - The backend validates the webhook's companion signature.
   - Resolves JID numbers using strict normalizers, queries the `conversations` index, and executes a database insertion for the new `Message` record with `origin = "inbound"`.
   - Broadcasts the message updates in real-time to active UI sessions via WebSockets.

3. **Inference & RAG Dispatch**:
   - If the conversation's `bot_paused_until` timestamp is in the past, the backend spawns a Celery task: `process_ai_reply_task.delay()`.
   - The Celery worker generates the query embeddings, queries the PostgreSQL `kb_document_chunks` table using cosine similarity (`<=>` operator), and retrieves the top 3 RAG context facts.
   - Combines the facts, persona boundaries, and chat history into a system prompt. Calls Ollama (`qwen2.5:1.5b-instruct`) over local HTTP `/api/chat`.
   - The generated response is passed back to the Node.js companion engine: `POST http://whatsapp-engine:3000/sessions/{session_id}/send`.

---

## 3. Outbound Live Agent Override Steps

1. **Manual Interception**:
   - When an agent writes a message inside the client chat dashboard, the frontend calls `POST /api/v1/chats/send`.
   - The backend halts the chatbot for 24 hours by setting `bot_paused_until = func.now() + timedelta(hours=24)` on the conversation row.
   - Inserts an optimistic message row in PostgreSQL with `origin = "outbound"` and status `queued`.

2. **Baileys Dispatch**:
   - FastAPI relays the dispatch request to the Node.js engine `/sessions/send`.
   - Baileys transmits the payload to the WhatsApp cellular network and returns the unique WhatsApp message ID (`whatsapp_message_id`).
   - The backend maps the response ID to the optimistic database row, transitioning the state from `queued` to `sent`.

3. **Receipt Handlers (ACKs)**:
   - When the recipient's phone receives and opens the message, the WhatsApp network fires status callbacks (`sent` -> `delivered` -> `read`).
   - Baileys processes callbacks and updates the database row `messages.ack_state` accordingly.
