import re

def normalize_jid(jid_or_phone: str, default_country_code: str = "91") -> str:
    """
    Normalize a phone number or WhatsApp JID into the canonical
    customer identity: [number]@<domain>.

    Now accepts a `default_country_code` parameter, allowing each tenant to
    configure their region (e.g. "1" for US, "44" for UK, "91" for India).
    This fixes BUG-002 where all bare 10-digit inputs were forced to Indian (+91).

    Domain rules:
      @s.whatsapp.net  — standard personal phone number
      @lid             — WhatsApp Line Identity (new protocol)
      @g.us            — Group JID

    Rejects:
      - Guest / temp / anonymous / unknown identifiers
      - Multi-domain JIDs
      - Non-numeric user parts
      - Numbers with <= 2 unique digits (robotic/test patterns)
      - Numbers outside 7–20 digit length bounds

    Examples:
      normalize_jid("+91 9137730283")           -> "919137730283@s.whatsapp.net"
      normalize_jid("7021886525")               -> "917021886525@s.whatsapp.net"  (India default)
      normalize_jid("4155552671", "1")          -> "14155552671@s.whatsapp.net"   (US tenant)
      normalize_jid("7911123456", "44")         -> "447911123456@s.whatsapp.net"  (UK tenant)
      normalize_jid("917021886525:12@s...")     -> "917021886525@s.whatsapp.net"
      normalize_jid("185654373789739@lid")      -> "185654373789739@lid"
    """
    if not jid_or_phone:
        raise ValueError("JID is required")

    raw = str(jid_or_phone).strip()
    lowered = raw.lower()
    if any(marker in lowered for marker in ("guest", "temp", "temporary", "anonymous", "unknown")):
        raise ValueError(f"Rejected non-customer identifier: {raw}")

    clean = re.sub(r"[\s\+\-\(\)]", "", raw)
    if clean.count("@") > 1:
        raise ValueError(f"Malformed JID contains multiple domains: {raw}")

    domain = "s.whatsapp.net"
    if "@" in clean:
        user, domain = clean.split("@", 1)
        domain = domain.lower()
        if domain not in ("s.whatsapp.net", "lid", "g.us"):
            raise ValueError(f"Unsupported WhatsApp JID domain: {domain}")
    else:
        user = clean

    # Strip companion device suffix (e.g. :12)
    user = user.split(":", 1)[0]
    if not user or not user.isdigit():
        raise ValueError(f"JID user part must be numeric: {raw}")

    # Sanitize country code input — digits only, 1–4 chars
    cc = re.sub(r"\D", "", str(default_country_code))
    if not cc or len(cc) > 4:
        cc = "91"  # Safe fallback

    # Strip accidental duplicated country-code prefixes (e.g. 9191...)
    double_cc = cc + cc
    while user.startswith(double_cc) and len(user) > len(cc) + 7:
        user = user[len(cc):]

    # Auto-prepend country code to bare local numbers (7–11 digits without cc prefix)
    if not user.startswith(cc):
        # Bare local number length heuristic: 7–11 digits means no country code yet
        if 7 <= len(user) <= 11:
            user = cc + user

    # Indian mobile number strict validation (12 digits: 91 + 10 digit mobile)
    if cc == "91" and user.startswith("91") and len(user) == 12:
        if not re.fullmatch(r"91[6-9]\d{9}", user):
            raise ValueError(f"Rejected malformed Indian mobile JID: {raw}")
        if len(set(user[-10:])) <= 2:
            raise ValueError(f"Rejected duplicated-digit phone number: {raw}")
    else:
        # General international: 7–20 digits total
        if not re.fullmatch(r"\d{7,20}", user):
            raise ValueError(f"Rejected malformed/unsupported JID user part: {raw}")
        # Sanity: reject all-same-digit numbers globally
        if len(set(user)) <= 2 and len(user) >= 10:
            raise ValueError(f"Rejected duplicated-digit phone number: {raw}")

    return f"{user}@{domain}"
