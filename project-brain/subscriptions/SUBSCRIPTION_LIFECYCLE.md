# Tenant Subscription Lifecycle & Reminder System

This document outlines the state transition map, automated payment renewals, reminder notifications, and billing enforcement middleware.

---

## 1. Subscription State Transition Matrix

```
       [ Free Tier Signup ]
                │
                ▼
      ┌───────────────────┐
      │   Status: Active  │ <─────────────────────┐
      └─────────┬─────────┘                       │
                │                                 │ (User pays signature verify /
                │ (Days Left == 0 /               │  Admin manual override)
                │  Auto-Pay Charge Fails)         │
                ▼                                 │
      ┌───────────────────┐                       │
      │ Status: Past_Due  │ (Grace Period: 3 days)│
      └─────────┬─────────┘                       │
                │                                 │
                │ (Grace Period Exceeds /         │
                │  Manual Suspend)                │
                ▼                                 │
      ┌───────────────────┐                       │
      │ Status: Expired   ├───────────────────────┘
      │   or Suspended    │
      └───────────────────┘
```

*   **`active`**: Full resource access. Active bot and campaign schedules operate.
*   **`past_due`**: Active period has ended but payment failed. Injects a 3-day grace period. Displays a header banner in the frontend dashboard.
*   **`expired`**: Grace period ended. Outbound sends and AI bot reply modules are blocked.
*   **`suspended`**: Super Admin manually revoked permissions. Workspace is locked.

---

## 2. Subscription Reminder Systems

A background worker task (`check_subscription_reminders_task` in `tasks.py`) runs periodically to verify active subscription periods:
*   **7 Days Before Expiry**: Sends a warning to prepare payment.
*   **3 Days Before Expiry**: Injects a dashboard notice reminding the user of the upcoming charge.
*   **1 Day Before Expiry**: Outlines the Auto-Pay schedule.
*   **Expiry Day**: Sends an urgent alert.
*   **Post-Expiry**: Displays warning flags to pay immediately.

### Communication Channels
1.  **Dashboard Alert**: Publishes a `subscription_reminder` event via WebSockets to the client workspace.
2.  **WhatsApp Notice**: Triggers an outbound dispatch using the connected session node to message the customer/owner phone number directly.
3.  **Logs System**: Appends trace records to `/project-brain/logs/`.

---

## 3. Automated Renewal Pipeline (Auto-Pay)

The automated charging pipeline (`process_autopay_renewals_task` in `tasks.py`) processes renewals:
1.  Queries subscriptions expiring in less than 24 hours with `renewal_state == 'auto'`.
2.  Creates a transaction log in the `renewal_jobs` table.
3.  Calls the Razorpay Subscription Charge API with the cached token.
4.  **On Payment Capture Success**:
    - Extends `current_period_end` by 30 days.
    - Saves the invoice in the `billing_history` table.
    - Resets metric counters in `tenant_quotas`.
5.  **On Charge Decline**:
    - Marks subscription status as `"past_due"`.
    - Dispatches a warning alert over WhatsApp.

---

## 4. Enforcement Middleware Code Blueprint

Enforced in `chats.py`, `sessions.py`, and background campaigns `tasks.py`:
```python
# app/routers/billing.py
def is_subscription_active(db: Session, tenant_id: UUID) -> bool:
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        return True # Free defaults

    if sub.status != "active":
        return False

    if sub.current_period_end:
        now = datetime.now(timezone.utc)
        end_time = sub.current_period_end
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if now > end_time:
            sub.status = "expired"
            db.commit()
            return False

    return True
```
