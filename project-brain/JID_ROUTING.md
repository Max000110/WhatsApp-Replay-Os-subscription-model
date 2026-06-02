# ReplyOS — JID Routing & Normalization Architecture

This document specifies the formatting protocols, device-stripping utilities, and outbound regex validations ensuring JID routing stability.

---

## 1. Supported JID Formats

WhatsApp maps routing destinations to standard Jabber Identifiers (JIDs):

| Format Type | Domain Suffix | Sample Identifier | Usage Profile |
| :--- | :--- | :--- | :--- |
| **Standard Mobile** | `@s.whatsapp.net` | `917021886525@s.whatsapp.net` | Standard customer phone numbers |
| **Group Chat** | `@g.us` | `1203632194857@g.us` | WhatsApp group conversations |
| **LID Format** | `@lid` | `185654373789739@lid` | Modern anonymized JID contacts |

---

## 2. Dynamic Companion Device Stripping

When a user logs in with multiple devices, the Baileys socket receives callbacks containing device qualifiers:
* **Malformed Format**: `917021886525:2@s.whatsapp.net` or `917021886525:device_id@s.whatsapp.net`
* **Threat**: Storing these raw suffixes in the database bypasses UNIQUE constraints, creating duplicate conversation threads for a single customer.
* **Resolution**: The system applies regex stripping:
  ```python
  # Strips colon and suffix digits before mapping domain
  clean_jid = re.sub(r':\d+', '', raw_jid)
  ```

---

## 3. Central Normalizer (`backend/app/core/jid.py`)

All incoming phone numbers or destination targets are passed through `normalize_jid()` before database operations or outbound queue insertion:

```python
def normalize_jid(phone: str) -> str:
    """
    Cleans raw strings and resolves them to canonical XMPP JIDs.
    """
    if not phone:
        return ""
        
    phone = phone.strip()
    
    # 1. Bypass if already a correct JID format
    if "@" in phone:
        local_part, domain = phone.split("@", 1)
        # Strip companion device digits
        local_part = local_part.split(":")[0]
        # Keep if valid domain
        if domain in ["s.whatsapp.net", "lid", "g.us"]:
            return f"{local_part}@{domain}"
            
    # 2. Extract digits only for raw phone inputs
    digits = re.sub(r"\D", "", phone)
    
    # 3. Default Indian mobile prefix parsing (10-digit auto-prepend)
    if len(digits) == 10:
        digits = "91" + digits
        
    if len(digits) >= 11 and len(digits) <= 15:
        return f"{digits}@s.whatsapp.net"
        
    return ""
```

---

## 4. Outbound Anti-Ban Validation Check

Before dispatching manual override or chatbot messages, the Node companion (`whatsapp-engine/src/anti-ban.ts`) executes a regex validation:
* **Regex**: `/^\d{7,20}@(s\.whatsapp\.net|lid|g\.us)$/`
* **Outcome**: Rejects formatting errors or companion device traces to protect the WhatsApp account from bans caused by sending to malformed domains.
