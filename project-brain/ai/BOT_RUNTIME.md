# AI Bot Runtime & Automation Pipeline

This document defines the execution flow of the AI Chatbot auto-reply pipeline, including agent takeover guards, local LLM inference, and RAG context integration.

---

## 1. Automation Pipeline Architecture

Inbound messages trigger a background event execution pipeline that determines if a response should be automatically generated:

```
[Inbound Message (webhook)]
            │
            ▼
[Subscription Status Check] ──(expired/suspended)──> [Exit & Log]
            │ (active)
            ▼
[Monthly Message Limit Check] ──(limit reached)─────> [Exit & Log]
            │ (under limit)
            ▼
[Agent Takeover Pause Check] ──(bot_paused_until > now)──> [Exit & Bypass Log]
            │ (unpaused)
            ▼
[Fetch Active Session Chatbot] ──(no active bot)───> [Exit]
            │ (bot active)
            ▼
[RAG Knowledge Retrieval] (if enabled)
            │
            ▼
[Inference: Ollama Generator] (qwen2.5:1.5b-instruct)
            │
            ▼
[Persist Outbound message] (status: "queued")
            │
            ▼
[Call Unified Outbound Dispatcher]
```

---

## 2. Agent Takeover Guard (Bot Paused State)

To prevent the AI chatbot from interrupting a live human operator support conversation, the bot is automatically paused upon manual agent activity.

* **Trigger**: Any HTTP post to [POST /api/v1/chats/send](file:///home/ubuntu/whatsapp-ai-saas/backend/app/routers/chats.py#L35) (Live Chat panel manual messages) automatically updates the conversation record.
* **Database Action**: Sets `bot_paused_until = now() + timedelta(minutes=15)`.
* **Webhook Pipeline Check**: In [process_incoming_chat_pipeline](file:///home/ubuntu/whatsapp-ai-saas/backend/app/routers/sessions.py#L236-L252), if `bot_paused_until` is greater than the current time, the incoming message is stored, but chatbot generation is bypassed.

---

## 3. Ollama LLM Inference Configuration

The system performs local inference using Ollama running inside the Docker container stack.

* **Internal Endpoint**: `http://ollama:11434`
* **Default Model**: `qwen2.5:1.5b-instruct` (Configured in the database for the active chatbot)
* **Temperature**: `0.4`
* **Prompt Construction**:
  * System Prompt: Loaded from `chatbot.system_prompt`.
  * Knowledge Context: Appended if RAG is enabled and context chunks match.
  * User Query: Passed as the user prompt.

---

## 4. RAG Context Injection

If the chatbot has `rag_enabled = true`, the system queries the vector database for matching knowledge chunks:

* **Trigger**: [rag_service.fetch_matching_context(db, session_id, query)](file:///home/ubuntu/whatsapp-ai-saas/backend/app/routers/sessions.py#L259)
* **Execution**: Searches embedded documents for the tenant.
* **Prompt Injection**: Matches are concatenated and injected into the chatbot's instructions:
  ```text
  Use the following verified facts to answer the customer request:
  [Context Chunks]

  Important: If the info is not in the context, politely let the customer know.
  ```

---

## 5. Verification Evidence
During pipeline validation, the AI bot successfully triggered local LLM inference and generated replies that were queued and delivered to a real WhatsApp device:
* **Log**: `[Webhook - a14b378d-...] Routing to Chatbot: sale`
* **Log**: `[Webhook - a14b378d-...] AI reply queued for delivery to 917021886525`
* **Database Verification**: Outbound message `9791f950-5592-4d34-8468-105152adb70f` written to database and transitioned to `delivered` status with WhatsApp message ID `3EB03B59760F641355013D`.
