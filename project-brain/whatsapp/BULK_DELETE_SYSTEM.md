# Bulk Delete System Specifications

This document defines the database transaction boundaries, cascade constraint resolutions, and frontend sync logic of the ReplyOS Bulk Deletion Engine.

## Deletion Pipeline Architecture

```mermaid
graph TD
    A[Frontend Dashboard Inbox] -->|Multi-Select Conversations| B[Selected Set: selectedConvIds]
    B -->|Click soft/hard bulk delete| C[POST /api/v1/chats/bulk-delete]
    C -->|Pydantic BulkDeleteRequest payload| D[FastAPI async def Route]
    D -->|BEGIN TRANSACTION| E[SQL SELECT: Filter by ID List and tenant_id]
    E --> F{Ownership Valid?}
    F -->|No| G[HTTP 401 Unauthorized / db.rollback()]
    F -->|Yes| H{delete_type}
    H -->|hard| I[SQL DELETE: Cascade orphan message removal]
    H -->|soft/archive| J[SQL UPDATE: Mark is_archived = True]
    I --> K[db.commit()]
    J --> K
    K -->|Success| L[Await websocket_manager.publish_event]
    K -->|Failure| M[db.rollback() / HTTP 500 Error]
    L --> N[WebSocket broadcast: conversations_bulk_deleted]
    N --> O[UI updates Map states in real-time]
```

---

## 1. Transactional CRUD Operations

To guarantee consistency and protect against constraint violations:
* **Asynchronous Scoping**: The `/chats/bulk-delete` endpoint is declared as an `async def` route. Database writes and WebSocket triggers run on the main asyncio thread pool, preventing uvicorn event loop blockage or worker thread-pool starvations.
* **Atomic Rollback**: If any cascading constraint or database lock fails, the `db.rollback()` routine executes immediately to reset session state.
* **Cascade Message Purging**: The SQLAlchemy `Conversation.messages` relationship uses `cascade="all, delete-orphan"`. Hard-deleting conversations automatically clears dependent messages cleanly without orphaned database records.

---

## 2. Pydantic Payload Validation

```python
from uuid import UUID
from typing import List
from pydantic import BaseModel

class BulkDeleteRequest(BaseModel):
    conversation_ids: List[UUID]
    delete_type: str = "soft"  # soft, hard, archive
```

---

## 3. Real-Time Front-End De-indexing

When the frontend receives the `conversations_bulk_deleted` WebSocket notification, it removes the matching channels from state in O(1) time:

```typescript
else if (type === 'conversations_bulk_deleted') {
  setConversationsMap((prev) => {
    const nextMap = new Map(prev);
    const deletedIds = new Set(data.ids);
    for (const [jid, conv] of nextMap.entries()) {
      if (deletedIds.has(conv.id)) {
        nextMap.delete(jid);
      }
    }
    return nextMap;
  });
  if (activeConvRef.current && new Set(data.ids).has(activeConvRef.current.id)) {
    setActiveConv(null);
  }
}
```

---

> [!WARNING]
> Do not bypass the `tenant_id` query constraints on bulk mutations. Database filtering must always cross-reference `Conversation.tenant_id == tenant_id` to guarantee robust multi-tenant tenant isolation.
