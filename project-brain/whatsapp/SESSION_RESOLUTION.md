# Baileys Multi-Device Session Storage and Resolution

This document details the architecture and operational guidelines for storing and restoring WhatsApp companion device authorization keys in a multi-tenant PostgreSQL database.

---

## 1. Auth Credentials Lifecycle

To scale out dynamically, the Node.js WhatsApp Engine avoids local filesystem storage, instead persisting Baileys multidevice `AuthenticationState` in a secure PostgreSQL table `whatsapp_sessions`:

```
 [WhatsApp Web QR / Scan]
            │
            ▼
[Baileys Multi-Device Client]
            │
            ▼ (creds.update & keys.set events)
[usePostgresAuthState (session-db-store.ts)]
            │
            ▼ (JSON Serialization + AES-256-GCM Encryption)
 [Database Update (whatsapp_sessions.session_auth_data)]
```

### Encryption Constraints
Auth data is encrypted using **AES-256-GCM** before persistence to PostgreSQL. The key is derived using SHA-256 against the `JWT_SECRET` environment variable.
A backward-compatible decoder layer ensures that unencrypted legacy session states are decrypted safely and seamlessly migrated upon their next database write event.

---

## 2. PostgreSQL Custom State Storage Implementation

The state provider hooks directly into Baileys authorization events:
* **`creds.update`**: Deconstructs and serializes active identity credentials.
* **`keys.set`**: Dynamically writes or clears state parameters (e.g. noise keys, pre-keys, and app state sync values) in a consolidated JSON array.

### Schema Fields
* **`session_auth_data` (JSONB)**: Structured as `{ "encrypted": true, "data": "[hex_iv]:[hex_ciphertext]:[hex_auth_tag]" }`.
* **`status` (VARCHAR)**: Reflects `disconnected`, `scanning`, or `connected`.

---

## 3. Graceful Connection Recovery Loop

If a WhatsApp companion socket disconnects, the connection manager determines the root cause and resolves it automatically:

1. **Logouts (`DisconnectReason.loggedOut`)**: Wipes active database authentication tokens and marks the channel status as `disconnected`.
2. **Temporary Server Failures**: Triggers an incremental jitter backoff reconnection loop.
3. **Infinite Hammering Block**: Caps active retry loops at `5` consecutive failed attempts to avoid hammering the WhatsApp network.

---

## 4. Boot-Up Restorations

Upon container boot-up, the Express control engine queries the database:
```sql
SELECT id FROM whatsapp_sessions WHERE status IN ('connected', 'scanning');
```
It automatically calls `initSession()` in the background to restore connection sockets for all active channels without requiring human operator intervention.
