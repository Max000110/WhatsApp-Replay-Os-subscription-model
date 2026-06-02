# WhatsApp Socket State Validation

This document defines the runtime constraints and telemetry assertions used to monitor, validate, and preserve the Baileys WebSocket transport layer.

---

## 1. Socket Connection Verification

Before executing any outbound message dispatch, the engine verifies the health and activity of the Baileys socket using three primary parameters:

1. **`sock.user`**: Confirms that authentication credentials are loaded and that the connection belongs to an active, registered WhatsApp account.
2. **`sock.ws.readyState`**: Asserts the direct status of the underlying Node WebSocket connection. It MUST match `WebSocket.OPEN` (value `1`).
3. **`connection === "open"`**: Validates that the Baileys library event-loop states are fully synchronized and capable of transmitting payloads.

---

## 2. Pre-Send Diagnostics Log

Every outbound message execution generates a structured telemetry payload capturing socket and route metadata to prevent silent failures:

```json
{
  "jid": "18565437378@s.whatsapp.net",
  "normalized_jid": "18565437378@s.whatsapp.net",
  "socket_connected": true,
  "ws_state": 1,
  "session_id": "a14b378d-4971-4263-bbe0-b8c63aba71be",
  "tenant_id": "eee18224-de89-41c3-9fb3-e4fdebb532eb"
}
```

---

## 3. Post-Send Assertion Schema

To ensure that messages are successfully pushed to the WhatsApp transport layer, the engine verifies the return output of `socket.sendMessage()`. Any payload missing these fields indicates a dispatch failure:

* **`key.id`**: The server-assigned message identifier (e.g. `3EB052D1F55BC40B33A51C`).
* **`messageTimestamp`**: Server epoch time indicating ingestion.
* **`status`**: Current transport status (defaults to `1` indicating sent).
* **`remoteJid`**: Verified recipient JID (e.g. `18565437378@s.whatsapp.net`).
* **`participant`**: Present on group channels to indicate the message sender device.
