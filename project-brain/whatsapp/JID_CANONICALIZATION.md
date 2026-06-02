# JID Canonicalization & Identity Resolution

## 2026-05-29 Strict Canonicalization Revision

The previous implementation was too permissive and accepted the malformed runtime ID `185654373789739@s.whatsapp.net`. The active rule is now strict:

* `+91 9137730283` -> `919137730283@s.whatsapp.net`
* `9137730283` -> `919137730283@s.whatsapp.net`
* `7021886525` -> `917021886525@s.whatsapp.net`
* `919137730283:12@s.whatsapp.net` -> `919137730283@s.whatsapp.net`

Rejected before DB/websocket/render:

* `185654373789739@s.whatsapp.net`
* `guest-*`
* `temp*`
* duplicated `@s.whatsapp.net@s.whatsapp.net`
* unsupported domains such as `@lid`
* repeated-digit fake numbers

Central utility: `backend/app/core/jid.py::normalize_jid()`. It raises `ValueError` on invalid input; callers must reject and log.

Patched callers:

* `backend/app/routers/sessions.py::process_incoming_chat_pipeline`
* `backend/app/routers/chats.py::send_agent_message`
* `backend/app/routers/chats.py::merge_conversations`
* `backend/app/routers/campaigns.py::create_campaign`
* `backend/worker/tasks.py::run_campaign_broadcast_task`
* `backend/worker/tasks.py::check_subscription_reminders_task`

Defensive engine guard: `whatsapp-engine/src/anti-ban.ts::queueMessage` rejects any outbound target that is not `91[6-9][0-9]{9}@s.whatsapp.net`.

This document details the diagnostic findings, root cause, and architectural resolution for WhatsApp Conversation Identity Mismatches and JID Routing failures.

---

## 1. Mismatches & Mapped Identities
Previously, the system stored customer identities using a mixture of raw phone numbers, leading plus signs, and companion device JIDs. This created duplicate conversation entities for the same physical user:

* **Identity A**: Raw digits (e.g. `917021886525`) — Created during manual override dispatches.
* **Identity B**: Plus prefixes or device suffixes (e.g. `+185654373789739` or `18565437378:9739`) — Created during incoming webhooks or companion device events.

These differences caused:
1. **Thread Dispersal**: Inbound customer messages routed to separate threads from manual operator overrides.
2. **AI Bot Failure**: The AI bot was triggered on one identity while the manual overrides occurred on the other, creating bot pause mismatch locks.

---

## 2. Canonical JID Normalization Strategy

To establish a single source of truth, **all conversations** now utilize a unified `normalized_jid` as their database identifier (`customer_phone`).

### Normalization Rules
The central utility function `normalize_jid` processes incoming values as follows:
1. **Sanitize Characters**: Strip whitespaces, plus signs (`+`), hyphens, and parenthesis.
2. **Remove Suffixes**: Split the user part by `:` to strip device/agent indices.
3. **Canonical Domain**: Formulate as `[clean_number]@s.whatsapp.net` (or preserve `@g.us` domains for group flows).
4. **Country Code Auto-Prepending**: Automatically prepends `91` to raw 10-digit Indian phone numbers (starting with 6, 7, 8, 9) to ensure valid WhatsApp network delivery.

```python
# python normalizer logic
# app.core.jid
import re

def normalize_jid(jid_or_phone: str) -> str:
    if not jid_or_phone:
        return ""
    clean = re.sub(r'[\s\+\-\(\)]', '', jid_or_phone.strip())
    if "@" in clean:
        user, domain = clean.split("@", 1)
        user_clean = user.split(":", 1)[0]
        if len(user_clean) == 10 and user_clean[0] in '6789':
            user_clean = '91' + user_clean
        return f"{user_clean}@{domain}"
    else:
        user_clean = clean.split(":", 1)[0]
        if len(user_clean) == 10 and user_clean[0] in '6789':
            user_clean = '91' + user_clean
        return f"{user_clean}@s.whatsapp.net"
```

---

## 3. Database Schema & Migration

### Schema Modification
The field type limit of `customer_phone` inside the `conversations` table was increased to support JID lengths up to 100 characters:
```sql
ALTER TABLE conversations ALTER COLUMN customer_phone TYPE VARCHAR(100);
```

### De-duplication and Merge Script
A Python script was run directly against the PostgreSQL container to migrate existing records. It identifies duplicate conversations under the same normalized JID, transfers all message records to the oldest (canonical) conversation, deletes the duplicate conversation, and updates the `customer_phone` identifier to the canonical JID format.

* **Initial Migration**:
  ```text
  Found 2 conversations to process.
  Normalizing conversation e1403aed-6f36-4779-bb45-a78ab1aab49e: 185654373789739 -> 185654373789739@s.whatsapp.net
  Normalizing conversation 6a17920e-9b77-49d6-85dd-6064d94dfe23: 917021886525 -> 917021886525@s.whatsapp.net
  Migration finished successfully!
  ```

* **Companion Device JID Merging Script (merge_duplicates.py)**:
  Run successfully inside the backend container to resolve companion JID duplicates:
  ```text
  [Migration] Starting conversation deduplication and merging...
  [Migration] Mapping duplicate companion JID '185654373789739@s.whatsapp.net' to canonical '18565437378@s.whatsapp.net'
  [Migration] Canonical conversation for '18565437378@s.whatsapp.net' is e1403aed-6f36-4779-bb45-a78ab1aab49e
  [Migration] Merging duplicate conversation cfaab00c-7a4d-487a-a942-02b2e7ffbd16 into canonical e1403aed-6f36-4779-bb45-a78ab1aab49e...
  [Migration] Deduplication and merge finished successfully!
  ```


---

## 4. End-to-End Verification Proof

Testing with the real customer JID `917021886525@s.whatsapp.net` verified:
1. Inbound webhook processed with `from = 917021886525@s.whatsapp.net`.
2. Located conversation `6a17920e-9b77-49d6-85dd-6064d94dfe23` successfully.
3. AI Bot `sale` triggered and generated response.
4. Auto-reply delivered to the device, updating status to `delivered` under the same JID thread.
