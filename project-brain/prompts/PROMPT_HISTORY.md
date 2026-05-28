# Prompt History & System Instruction Log

This document records the core prompt instructions, design directives, and engineering guidelines governing the developer AI agents during the implementation of the WhatsApp AI SaaS Platform (ReplyOS).

---

## 1. Global SRE Engineering Directives

### Principal Architecture Alignment
* **Role**: Principal SRE, SaaS Architect, Distributed Systems Engineer.
* **Core Rule**: Do NOT rebuild infrastructure, do NOT restart architecture planning, and do NOT write toy systems. Maintain strict production standards.
* **Continuous Persistence**: All major states, runtime evidence, patch diffs, and lessons learned must be documented into markdown files inside `/project-brain`.

---

## 2. Branding Guidelines

### Directives
* **Name Removal**: Wipe all instances of `Antigravity Flow` and `Antigravity` from metadata, frontend title headers, and Baileys browser logs.
* **New Brand**: **ReplyOS**
* **Theme Styling**: Approved premium dark UI style (dark-violet backgrounds,Outfit/Inter fonts, emerald check accents, clean spacing). Do NOT redesign layout panels.

---

## 3. Engineering Priorities List

### Phase 1: Real-Time Synchronization
* **Directive**: Eliminate REST-based polling intervals (3s/5s) in Next.js frontend pages.
* **Implementation**: Deploy a Redis Pub/Sub Connection Manager backend and a reconnecting WebSocket client frontend to broadcast status updates instantly.

### Phase 2: Reliable Outbound ACK Status Pipeline
* **Directive**: Move beyond binary status tracking. Map the full sequence: `queued` -> `sending` -> `sent` -> `delivered` -> `read` -> `failed`.
* **Implementation**: Return WhatsApp server message IDs on sent socket callbacks, update states in DB, and push status changes instantly to clients via WebSockets.

### Phase 3: Bot Overrides & Pauses
* **Directive**: Inhibit bot auto-replies when human agents manually type overrides.
* **Implementation**: Set conversation-level `bot_paused_until` duration limits (15 minutes lock) triggered by manual chat transmissions.

### Phase 4: Razorpay Subscriptions & Upgrade Sandbox
* **Directive**: Implement multi-tenant billing restricting bot connections and outbound cap allowances based on current plan tiers.
* **Implementation**: Build Razorpay order endpoints, signature validator webhooks, and a frontend subscription settings tab equipped with a Sandbox Payment simulation modal.

### Phase 5: Cloudflare Nginx Reverse IP Forwarding
* **Directive**: Preserve accurate visitor IP coordinates for backend rate limiters.
* **Implementation**: Extract client IP from Cloudflare's `CF-Connecting-IP` header inside the reverse proxy gateway settings.
