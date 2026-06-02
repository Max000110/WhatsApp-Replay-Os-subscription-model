# Baileys Runtime Execution Specs

This document defines the runtime environment, configuration parameters, and lifecycle events for the `@whiskeysockets/baileys` node connection engine.

---

## 1. Dynamic Web Version Resolving

To prevent `405 Method Not Allowed / Outdated Protocol` rejections on startup, the engine queries the latest WhatsApp Web build version dynamically:
* **Function**: `fetchLatestBaileysVersion()`
* **Fallback Config**: `[2, 3000, 1017539703]` (high fallback parameters)
* **Application Point**: Executed during socket creation in [initSession()](file:///home/ubuntu/whatsapp-ai-saas/whatsapp-engine/src/baileys-manager.ts#L26-L61).

---

## 2. WebSocket Connection Lifecycle & Reconnection Loop

The engine handles transport state updates synchronously through `connection.update` hooks:

* **`scanning` / `qr`**: Generated when credentials are unauthenticated. Saves the base64 QR code to PostgreSQL to allow frontend scanning.
* **`connected` / `open`**: Emitted when authentication resolves successfully. Extracts the bot's own phone number from the credentials JID (`socket.user.id.split(":")[0]`) and updates the state.
* **`disconnected` / `close`**: Triggered when the WebSocket drops.
  * **Disconnect Reason Code 401 (Logged Out)**: Wipes auth keys from database and terminates session gracefully.
  * **Other Connection Closes**: Initiates connection reconnects with an incremental backoff delay (capped at 5 attempts before safety throttling triggers).

---

## 3. Worker Threads & Execution Context

* **Runtime Container**: `saas_whatsapp_engine` (Node.js 18 alpine stack).
* **Multi-Tenant State Management**: Active socket objects are mapped dynamically by `sessionId` inside `activeSockets` (a memory map). Authentication records are stored in PostgreSQL using `usePostgresAuthState` to prevent state loss across container restarts.
