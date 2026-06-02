# Security Hardening, Isolation, and Rate Limiting

This document specifies the security controls, tenant isolation guidelines, and API protection frameworks deployed across the SaaS WhatsApp pipeline.

---

## 1. Rate Limiting and Brute Force Protections

* **Mechanism**: Redis-backed sliding-window rate limiter.
* **IP Throttling**: Tracks request frequency per client IP.
* **Progressive Bans**: Reaching request rate limits triggers escalating IP cooldown blocks:
  - Phase 1: 5-minute warning cooldown.
  - Phase 2: Complete 24-hour block for persistent brute-force threats.
* **Audit Triggers**: Blocks write security audit logs to track anomalies.

---

## 2. Multi-Tenant Cryptographic Isolation

* **Database Layer**: Every record is strictly bound to a `tenant_id` UUID column. All select, update, and delete queries enforce strict tenant bounds in their SQL `WHERE` clauses.
* **WebSocket Isolation**: Handshakes authenticate JWT tokens. Active sessions are stored in memory lists grouped strictly by `tenant_id`, ensuring clients can never listen to or broadcast messages across tenant boundaries.

---

## 3. Core API Hardening and Protections

* **JWT Authentications**: Authenticates JWT tokens signed with a high-entropy key secret. Session validation checks tenant state and expiration bounds on every request.
* **SQL Injection & XSS Guards**: Uses SQLAlchemy ORM to sanitize parameter inputs. Content-Security-Policy headers restrict unauthorized asset executions.
* **CSRF Mitigations**: Protected endpoints parse secure headers and enforce strict cookie handling parameters.
* **Data Masking**: Passwords are securely hashed using `bcrypt` and are never serialized or returned.

---

## 4. Role-Based Access Control (RBAC) & Audit Logs

* **Tenant Owner**: Full access to settings, billing, campaigns, RAG data, and chatbot sessions.
* **Operator (Member)**: Live overrides, chat history viewing, manual overrides, session connection status.
* **Super Admin**: Master Super Admin Panel with full override quotas, impersonation, tenant suspension, billing audits, and emergency shutdowns.
* **Auditing**: Session changes, quota modifications, and suspicious rate-limit violations are logged dynamically.
