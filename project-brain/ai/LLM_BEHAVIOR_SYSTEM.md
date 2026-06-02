# AI LLM Behavior System

This document specifies the architecture, prompt constraints, and local LLM runtime execution parameters for generating human-like business responses.

---

## 1. Local Inference Runtime

To ensure privacy, multi-tenant isolation, and cost-effectiveness, the system uses a localized **Ollama** service:
* **Docker Container**: `saas_ollama` running on port `11434`.
* **Standard Model**: `qwen2.5:1.5b-instruct` (lightweight, conversational instruction-following LLM).
* **Alternative Options**: Custom models are configurable per chatbot (e.g. Qwen, Llama).
* **Generation Parameters**: Default temperature is set to `0.4` to maintain factual stability while preserving response fluidness.

---

## 2. Agent Takeover Guard (Takeover Pauses)

To maintain high support quality, AI replies are automatically blocked when a human operator intervenes:
* **Trigger**: Manual agent dispatches to `/chats/send` set a `bot_paused_until` timestamp.
* **Duration**: Bypasses AI auto-reply on that conversation for a cooldown period of **15 minutes**.
* **Flow**: Webhook events register conversation history during the pause, but LLM generation is completely bypassed.

---

## 3. RAG Facts Context Merging

If a chatbot has `rag_enabled = true`, query processing undergoes dynamic context injection:

1. The customer message is vectorized using Ollama embeddings (`all-minilm:latest`).
2. A cosine-similarity similarity search matches the top 3 document fragments in PostgreSQL pgvector.
3. Relevant facts are formatted and dynamically injected into the LLM system prompt:

```text
[System Prompt / Business Persona]

Use the following verified facts to answer the customer request:
- [Fact Chunk 1]
- [Fact Chunk 2]

Important: If the info is not in the context, politely let the customer know.
```

---

## 4. Human-like Conversational Guardrails

To prevent typical robotic AI responses and maintain business styles:
* **Conciseness**: Keep replies short, conversational, and direct (suitable for WhatsApp bubbles).
* **No AI Disclaimers**: Strict prompt parameters block boilerplate disclaimers (e.g. "As an AI language model...").
* **Brand Voice**: The LLM adopts the tone, business style, and product pricing details configured in the chatbot's system instructions.
