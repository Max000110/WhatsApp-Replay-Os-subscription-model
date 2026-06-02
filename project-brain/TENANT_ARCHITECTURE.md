# ReplyOS — Multi-Tenant & Isolation Architecture

This document describes the multi-tenant model, database level constraints, API middleware checks, and subdomain resolution mapping the platform's isolation architecture.

---

## 1. Multi-Tenant Model Structure

ReplyOS is designed as a single-database, multi-tenant (shared schema) platform. Tenant spaces are segregated using a primary UUID column:

```
                  +-----------------------+
                  |        Tenants        | (id, name, subdomain, status)
                  +-----------------------+
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
        +-------+     +---------------+     +-------+
        | Users |     | Chatbots/KBs  |     | Chats |
        +-------+     +---------------+     +-------+
    (tenant_id)         (tenant_id)        (tenant_id)
```

Every secondary table contains a `tenant_id` column configured with a foreign key constraint pointing to `tenants.id`.

---

## 2. API Level Tenant Isolation (Middleware Guards)

To prevent data leaks, the FastAPI request pipeline resolves tenant context dynamically through JWT token claims:

1. **Authorization Middleware** (`get_current_user` in `auth/service.py`):
   - Extracts the JWT `saas_token` from the incoming request's `Authorization` header.
   - Validates the token's cryptographic signature.
   - Restricts API requests if the tenant is flagged as `suspended` or `terminated`.
   - Returns the active `User` object bound to their resolved `tenant_id`.

2. **Scoped Database Queries**:
   - Every API router endpoint (e.g., chats, sessions, chatbots) filters database queries using the authenticated user's `tenant_id`:
     ```python
     chats = db.query(Conversation).filter(Conversation.tenant_id == current_user.tenant_id).all()
     ```
   - This prevents tenant A from querying, modifying, or deleting records belonging to tenant B.

---

## 3. Database Constraints & Deletion Cascade

* **Cascade purges**: All secondary tables are configured with SQL foreign key cascades:
  ```python
  tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
  ```
  When a tenant is terminated, the database engine transactionally deletes all associated users, chatbots, sessions, conversations, and campaign metrics in a single cascade.
* **JID deduplication**: Deduplication inside conversations is enforced at the database level with a unique constraint:
  ```sql
  ALTER TABLE conversations ADD CONSTRAINT uq_tenant_customer_phone UNIQUE (tenant_id, customer_phone);
  ```

---

## 4. Subdomain-Ready Infrastructure Architecture

Future transition to subdomains (`app.domain.com`, `admin.domain.com`, `api.domain.com`) will maintain security isolation:
1. **Routing**: Wildcard domains (`*.domain.com`) map to the Nginx reverse proxy.
2. **Context Resolution**: The FastAPI backend inspects the `Host` header of incoming requests to extract the subdomain (e.g., `acme.domain.com` resolves to `acme`). The system queries the `tenants` table for matching `subdomain` to establish the tenant context before proceeding with query filters.
