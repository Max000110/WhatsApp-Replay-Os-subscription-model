# WebSocket Sync

## 2026-05-29 JID Corruption Finding

The websocket layer did not generate `185654373789739@s.whatsapp.net`; it broadcast the already-corrupted `conv_data.customer_phone` created by `sessions.py`.

Bad sequence:

```text
sessions.py creates Conversation(customer_phone='185654373789739@s.whatsapp.net')
publish_tenant_event_sync(..., "message", inbound_msg_data)
publish_tenant_event_sync(..., "conversation", conv_data)
frontend conversationsMap.set(c.customer_phone, c)
```

Fix:

* Inbound webhook rejects invalid JIDs before DB insert.
* No `message` or `conversation` websocket event is emitted for rejected identifiers.
* Frontend reducer remains unchanged visually and behaviorally; it receives only canonical backend rows after this patch.

Validated rejection:

```text
[Webhook - 61b8e755-2b65-428a-9d49-de6c4206aa80] Rejected inbound message with invalid JID source from='185654373789739@s.whatsapp.net' rawRemoteJid='185654373789739@s.whatsapp.net' rawParticipant='': Rejected malformed/non-Indian mobile JID
```

DB count for that JID after probe: `0`.
