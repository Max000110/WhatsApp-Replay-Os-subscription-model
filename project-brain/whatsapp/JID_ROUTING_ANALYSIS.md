# JID Routing Analysis — ReplyOS
**Last Updated**: 2026-05-29T19:27:25+05:30

---

## Current Canonical JID Standard

All customer phone numbers and WhatsApp JIDs are stored and processed exclusively in canonical format: `[digits]@s.whatsapp.net`

### Central Normalizer: `backend/app/core/jid.py::normalize_jid()`

```python
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

## Normalization Rules

### Input → Output Mapping

| Input | Output | Note |
|---|---|---|
| `7021886525` | `917021886525@s.whatsapp.net` | 10-digit Indian → auto-prepend 91 |
| `917021886525` | `917021886525@s.whatsapp.net` | Already full Indian number |
| `+917021886525` | `917021886525@s.whatsapp.net` | Strip + prefix |
| `917021886525@s.whatsapp.net` | `917021886525@s.whatsapp.net` | Already canonical |
| `917021886525:12@s.whatsapp.net` | `917021886525@s.whatsapp.net` | Strip companion device suffix |
| `185654373789739@s.whatsapp.net` | `185654373789739@s.whatsapp.net` | International — preserved as-is |
| `185654373789739@lid` | `185654373789739@lid` | LID format — preserved |
| `1234567890@g.us` | `1234567890@g.us` | Group JID — preserved |

### Rejected Inputs (raise ValueError)
- Empty string
- `guest-*` prefixed strings
- `temp*` prefixed strings
- Strings with repeated `@s.whatsapp.net@s.whatsapp.net`
- Repeated-digit fake numbers (e.g., `111111111111`)

---

## Integration Points

### Backend Callers
| File | Location | Action |
|---|---|---|
| `sessions.py` | `process_incoming_chat_pipeline` | Normalize inbound webhook JID |
| `chats.py` | `send_agent_message` | Normalize outbound target JID |
| `chats.py` | `merge_conversations` | Normalize merge target JID |
| `campaigns.py` | `create_campaign` | Normalize recipient list |
| `worker/tasks.py` | `run_campaign_broadcast_task` | Normalize each recipient |
| `worker/tasks.py` | `check_subscription_reminders_task` | Normalize reminder targets |

### Node.js Engine (TypeScript)
**Inbound JID parsing** (`baileys-manager.ts`):
```typescript
const from = remoteJid?.split("@")[0].split(":")[0] || "";
```

**Outbound JID guard** (`anti-ban.ts`):
```typescript
let cleanJid = to.trim().replace(/\s+/g, "").replace("+", "");
if (cleanJid.includes("@")) {
  const [user, domain] = cleanJid.split("@");
  cleanJid = `${user.split(":")[0]}@${domain}`;
} else {
  cleanJid = `${cleanJid.split(":")[0]}@s.whatsapp.net`;
}
// Validation: /\d{7,20}/.test(cleanJid.split("@")[0]) must be true
```

---

## Database Schema

```sql
-- conversations table
customer_phone VARCHAR(100)  -- stores full JID: "917021886525@s.whatsapp.net"

-- Unique constraint preventing duplicate conversations
UNIQUE(tenant_id, customer_phone)  -- uq_tenant_customer_phone
```

---

## Known JID Failure History

### Incident: Companion Device JID `185654373789739@s.whatsapp.net`
- **Source**: Baileys `remoteJid` for paired companion device (iPad/secondary phone)
- **Pattern**: Device JID format is `phone:device_index@s.whatsapp.net`
- **Example**: `18565437378:9739@s.whatsapp.net` → base number is `18565437378`
- **Resolution**: Strip everything after `:` before `@`
- **Status**: ✅ Fixed in both backend normalizer and Node engine

### Incident: Raw Digits vs Full JID Split Thread
- **Source**: Manual override sent to `917021886525` (raw), inbound received as `917021886525@s.whatsapp.net`
- **Resolution**: Normalizer appends `@s.whatsapp.net` to all bare number inputs
- **Status**: ✅ Fixed

### Incident: Over-Strict Normalizer Blocking International Numbers
- **Date**: 2026-05-29
- **Source**: Strict JID normalizer version only accepted 10-digit Indian numbers
- **Resolution**: Added support for arbitrary-length international numbers, `@lid` and `@g.us` domains
- **Status**: ✅ Fixed

---

## Pending JID Work

- [ ] Per-tenant country code configuration for non-Indian deployments (currently hardcoded to `91`)
- [ ] Handling of new WhatsApp protocol changes (new JID formats not yet catalogued)
- [ ] Group message handling (`@g.us` JIDs) — inbound routed but group reply not implemented
