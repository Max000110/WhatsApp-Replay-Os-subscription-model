# Billing & Subscription Integration Architecture

This document describes the billing model, subscription tier limits, Stripe integration flow, and database schema mappings for the WhatsApp AI SaaS platform.

---

## 1. Stripe Checkout Integration Flow

The billing system manages customer subscriptions using Stripe Checkout Portals:

```
[User Dashboard]
       │ (Clicks "Upgrade to Pro")
       ▼ (Request URL)
[FastAPI /billing/create-checkout]
       │ (Calls Stripe SDK to generate Session URL)
       ▼ (Redirects User)
  [Stripe Checkout Page] 
       │ (User completes payment)
       ▼ (Redirects back)
[User Dashboard (Success Banner)]
```

---

## 2. Webhook Event Management

Stripe dispatches events to the FastAPI backend webhook route (`/api/v1/billing/webhook`):

```
       [Stripe Servers]
              │ (POST Webhook Payload)
              ▼
[FastAPI /billing/webhook]
              │ (Validates stripe signature header)
              ▼
[Update DB `subscriptions` Table]
```

### Actionable Stripe Webhooks Checklist
1. **`customer.subscription.created`**:
   - Create a corresponding row in the `subscriptions` database table. Mapped to the tenant ID using Stripe's `client_reference_id` or custom metadata.
2. **`invoice.payment_succeeded`**:
   - Update `current_period_end` timestamps and set subscription status to `active`.
3. **`customer.subscription.deleted`**:
   - Trigger subscription status set to `canceled`. Remove bot processing configurations or downgrade tenant sessions to `free` limits.
4. **`customer.subscription.updated`**:
   - Catches tier upgrade/downgrade modifications (e.g., Starter -> Pro).

---

## 3. Subscription Pricing & Tier Limits Configuration

The platform restricts active resources inside backend route dependencies based on the user's active subscription tier.

```python
# File Reference Concept: backend/app/core/billing_guard.py

from fastapi import HTTPException, Depends
from app.database import get_db
from app.models.all_models import Subscription, WhatsAppSession

async def verify_tenant_limits(tenant_id: str, db = Depends(get_db)):
    sub = db.query(Subscription).filter_by(tenant_id=tenant_id, status="active").first()
    active_sessions_count = db.query(WhatsAppSession).filter_by(tenant_id=tenant_id, status="connected").count()

    if not sub:
        # Free Tier Defaults
        if active_sessions_count >= 1:
            raise HTTPException(status_code=403, detail="Free tier is limited to 1 active session. Please upgrade your plan.")
        return

    tier_limits = {
        "free": 1,
        "starter": 2,
        "pro": 5,
        "enterprise": 999
    }

    allowed_sessions = tier_limits.get(sub.plan_tier, 1)
    if active_sessions_count >= allowed_sessions:
        raise HTTPException(
            status_code=403, 
            detail=f"Subscription tier '{sub.plan_tier}' is capped at {allowed_sessions} sessions. Upgrade required."
        )
```
