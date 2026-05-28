# WhatsApp AI Automation SaaS Platform - Product Roadmap

This document outlines the current feature completion matrix, future capability milestones, and a production readiness checklist for scaling from MVP to an enterprise-grade SaaS platform.

---

## 1. MVP Status & Functional Matrix

All core MVP and SaaS foundation features are fully implemented and verified functional:

| Phase | Module | Status | Details |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Docker Infrastructure | ✅ Complete | Containerized stack using Postgres (pgvector), Redis, FastAPI, Next.js, Ollama. |
| **Phase 2** | DB Schema Design | ✅ Complete | SQL tables with unique composite indices, foreign keys, and multi-tenant partitioning. |
| **Phase 3** | Baileys Socket Engine | ✅ Complete | Dynamic QR generation, database-backed stateless credential persistence. |
| **Phase 4** | FastAPI Backend | ✅ Complete | JWT Auth, Bots, Chats, Campaigns, and Webhook integrations. |
| **Phase 5** | RAG Ingestion Pipeline | ✅ Complete | PDF document uploads, Celery chunking, and pgvector cosine search. |
| **Phase 6** | Frontend Dashboard | ✅ Complete | Premium Next.js UI, Live Override, active conversation flows. |
| **Phase 7** | Real-time Synchronization | ✅ Complete | Reconnected WebSocket connection manager replacing polling entirely. |
| **Phase 8** | Razorpay SaaS Billing | ✅ Complete | Razorpay subscription plans (Starter/Pro/Agency), webhook handlers, dynamic limits (sessions and monthly message caps) and sandbox checkout. |
| **Phase 9** | Cloudflare reverse proxy | ✅ Complete | Nginx updates extracting real client IPs from CF-Connecting-IP headers. |

---

## 2. Incomplete & Missing SaaS Features

To transform the current architectural foundation into a fully commercialized public SaaS product, the following features are planned:

1. **Stripe Billing Gateway Parallel Support**:
   - Introduce Stripe parallel integration for international customers alongside domestic Razorpay routes.
2. **Dynamic Live Chat Search & Quick-Replies**:
   - Live chat contact list search bar and filters (Unread, Bot Controlled, Agent Controlled, Archived).
   - Dynamic templates panel allowing agents to select and send standard quick-replies.
3. **Advanced Analytics & Reports**:
   - Analytics dashboards rendering message throughput, RAG search accuracy ratings, API latencies, and token costs.
   - Campaign conversion rate tracking (Sent vs. Delivered vs. Read metrics).

---

## 3. Future Architecture & Feature Roadmap

```
  [ Q2 2026 ]             [ Q3 2026 ]             [ Q4 2026 ]            [ Q1 2027 ]
  MVP Solidify         Commercialization         Scale & Cluster         Enterprise
 ┌────────────┐        ┌─────────────┐        ┌─────────────┐        ┌──────────────┐
 │ • Live Chat│        │ • Stripe Pay│        │ • Docker    │        │ • Multi-Agent│
 │   Search   │───────>│ • Campaign  │───────>│   Swarm / k8s │───────>│   Seat Roles │
 │ • Templates│        │   Analytics │        │ • Redis     │        │ • Meta API   │
 │   Library  │        │ • WhatsApp  │        │   Sentinel  │        │   Support    │
 └────────────┘        │   Templates │        └─────────────┘        └──────────────┘
                       └─────────────┘
```

### Milestone A: AI Agent & RAG Upgrades (Q2 - Q3 2026)
* **Hybrid Search Support**: Blend SQL full-text search indices with pgvector cosine embeddings to improve RAG lookup accuracy.
* **Complex Multi-Agent Flows**: Introduce LangGraph or AutoGen frameworks allowing bots to hand off complex tasks (like processing invoice generation) to secondary specialist bots.
* **Context Window Truncation Handler**: Programmatically summarize historical customer chat logs when context limits are reached to maintain low token costs.

### Milestone B: Infrastructure & Scaling Upgrades (Q3 - Q4 2026)
* **High Availability Clusters**: Run Celery workers in auto-scaling groups across separate virtual machine clusters to handle high campaign volumes.
* **Session Cache Store Separation**: Migrate Baileys credential buffers from main Postgres instances to active Redis keys to reduce DB read/write IOPS stress.
* **Dedicated Vector Store**: Migrate RAG matching from PostgreSQL pgvector to highly optimized Qdrant or Pinecone clusters.

### Milestone C: Enterprise Offerings (Q4 2026 - Q1 2027)
* **Meta Cloud API driver**: Give enterprise users a driver toggle to switch from WhatsApp web emulation (Baileys) to the official Meta Cloud API to ensure zero ban risk.
* **Granular Role-Based Access Control (RBAC)**: Support multi-agent teams with isolated scopes (e.g. Agent seats can reply to chats, Admin seats can edit Prompts, Owner seats can manage Billing).

---

## 4. Production Readiness Checklist

### Security & Hardening
- [ ] Set `DEBUG=False` and restrict FastAPI OpenAPI documentation route access in production.
- [ ] Change all default credential passwords in `.env` (Postgres, Redis, JWT Secrets).
- [✅] Secure communication by routing all traffic through Cloudflare proxies with active HTTPS SSL configurations.
- [✅] Enforce rate-limits on key API routes using Redis-backed throttling.

### Storage & Backups
- [✅] Set up daily automated cron backups of the database schema and store backups locally.
- [ ] Configure offsite uploads of database back archives to S3/Oracle bucket.
- [ ] Set up automatic vacuum schedules inside PostgreSQL to prevent tables bloat during high message throughput volumes.

### Performance & Scaling
- [✅] Add indexing to foreign keys and composite queries to maintain lightning-fast response latency.
- [✅] Limit Celery concurrency and restrict Docker container resource bounds to prevent CPU thrashing.
- [ ] Configure structured logging outputs inside production containers to route traces cleanly to Datadog or Loki.
