# AI Agents & Prompt Engineering Architecture

This document describes the orchestration of the AI reply pipeline, chatbot configurations, prompt structure designs, and model instructions.

---

## 1. AI Reply Webhook Processing Flow

The FastAPI backend routes incoming WhatsApp message payloads to the asynchronous Celery pipeline:

```
[Inbound Message Webhook]
           │
           ▼
[FastAPI `sessions.py` -> `route_webhook_event`]
           │ (Checks if bot is active for the target session)
           ▼ (Pushes process task to Redis)
[Celery Worker -> `process_ai_reply_task`]
           │ (1. Pulls conversation history and details)
           │ (2. Retrieves RAG facts from postgres-pgvector)
           │ (3. Constructs System Prompt)
           │ (4. Calls Ollama /api/chat generator)
           ▼ (Dispatches AI text output)
[WhatsApp Engine API `/sessions/send`]
```

---

## 2. Dynamic Prompt Construction Pattern

To ensure highly reliable and factual answers without hallucinations, system prompts are generated dynamically for each inbound customer text message:

```
+-----------------------------------------------------------+
|                       SYSTEM PROMPT                       |
|  - System Role (e.g. Helpful Sales assistant)              |
|  - Custom Chatbot Persona Config                          |
|  - Guardrails (e.g. Be polite, don't mention competitors) |
+-----------------------------------------------------------+
|                    VERIFIABLE RAG FACTS                   |
|  - Match 1: [PDF text content containing pricing]          |
|  - Match 2: [PDF text content containing schedules]        |
+-----------------------------------------------------------+
|                   CONVERSATION HISTORY                    |
|  - Customer: "Hello, how much is the pro plan?"           |
|  - Bot: "Hello! The Pro plan is $79/mo. Can I help?"       |
+-----------------------------------------------------------+
|                       LATEST INPUT                        |
|  - Customer: "What features are included in it?"           |
+-----------------------------------------------------------+
```

---

## 3. Recommended System Prompt Template

The default system prompt configured in `chatbots.system_prompt` is designed to enforce strict boundary guardrails:

```markdown
You are a helpful, professional customer support AI agent representing {{bot_name}}. 
Your primary task is to answer inquiries from customers using strictly the provided facts.

### IMPORTANT SYSTEM BOUNDARIES & RULES:
1. STRICT TRUTH ONLY: If the answer cannot be found in the provided RAG Context section, say: "I am sorry, but I do not have information on that topic. Let me connect you with a live human representative."
2. DO NOT HALLUCINATE: Never invent prices, dates, or specifications that are not explicitly written in the provided RAG Context.
3. WHATSAPP FORMATTING: WhatsApp does not support markdown headings (#, ##). Format your output beautifully using:
   - *bold* for emphasis
   - _italics_ for subtitles
   - ~strikethrough~ where necessary
   - Bullet points using standard hyphens (-)
4. CONCISE RESPONSES: Keep answers short and friendly, fitting mobile chat UI screens (~1 to 4 sentences max).

### RAG CONTEXT FOR THIS RESPONSE:
{{rag_context}}
```

---

## 4. Model Compatibility Settings

The AI service driver in `ai_service.py` is configured to leverage local CPU-optimized LLMs:
* **Default LLM**: `qwen2.5:1.5b-instruct` (High intelligence, fast speed, small footprint, multilingual).
* **Alternative LLM**: `phi3:3.8b-instruct` or `llama3.2:3b-instruct` (Stronger English reasoning skills but higher RAM compilation usage).
* **Temperature Config**: Default `0.3` (Low temperature reduces creative variance and guarantees strict facts adherence).
* **Top-P Config**: Default `0.85` (Maintains fluent sentences while eliminating outlier tokens).
