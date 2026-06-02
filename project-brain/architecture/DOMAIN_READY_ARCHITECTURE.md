# Future Domain Readiness & Multi-Tenant Routing Blueprint

This document details the architectural blueprint for transitioning the ReplyOS SaaS platform to subdomain-based multi-tenant routing (`app.domain.com`, `admin.domain.com`, etc.).

---

## 1. Domain Namespace Mapping

| Subdomain | Target Frontend / Backend | Authentication Token | Session Scope |
| :--- | :--- | :--- | :--- |
| **`api.replyos.com`** | backend container (FastAPI) | `Authorization: Bearer <token>` | Shared API Gateway |
| **`admin.replyos.com`** | frontend container (Next.js) | Cookie `replyos_admin_token` | Super Admin Controls |
| **`app.replyos.com`** | frontend container (Next.js) | Cookie `saas_token` | Customer Console (Fallback) |
| **`{tenant}.replyos.com`** | frontend container (Next.js) | Cookie `saas_token` | Dynamic Tenant Workspace |

---

## 2. Nginx Subdomain Routing Strategy

To achieve this, the production Nginx gateway (`saas_nginx`) must be configured with multiple server blocks:

```nginx
# 1. API gateway
server {
    server_name api.replyos.com;
    location / {
        proxy_pass http://backend:8000;
        # Standard proxy parameters
    }
}

# 2. Super Admin Control Plane
server {
    server_name admin.replyos.com;
    location / {
        proxy_pass http://frontend:3000;
        # Restrict headers to avoid leakage
    }
}

# 3. Dynamic Multi-Tenant Client workspaces (Wildcard)
server {
    server_name ~^(?<tenant>[a-zA-Z0-9\-]+)\.replyos\.com$;
    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header X-Tenant-Context $tenant;
    }
}
```

---

## 3. Cookie and Session Isolation

1. **Cookie Scoping**: Authentication tokens must be set as cookies rather than localStorage, scoped to the specific host subdomains to prevent cross-login boundary leaks:
   * Admin token: `Domain=admin.replyos.com; Secure; HttpOnly; SameSite=Strict`
   * Tenant token: `Domain={tenant}.replyos.com; Secure; HttpOnly; SameSite=Lax`
2. **Context Extraction**: The backend resolves the active tenant dynamically. Instead of relying on payloads, it extracts the target subdomain from the request Host header:
   ```python
   def resolve_tenant_from_header(request: Request, db: Session = Depends(get_db)):
       host = request.headers.get("host", "")
       subdomain = host.split(".")[0]
       tenant = db.query(Tenant).filter(Tenant.subdomain == subdomain).first()
       if not tenant:
           raise HTTPException(status_code=404, detail="Tenant workspace not found.")
       return tenant.id
   ```
   This enforces automatic scoping at the query level!
