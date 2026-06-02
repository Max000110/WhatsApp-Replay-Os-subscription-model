# ReplyOS — Campaign Broadcaster Engine Architecture

This document details the Celery background scheduler, timezone-aware schedules, message delays, and logging triggers.

---

## 1. Engine Core Flow

```
[Create Campaign in UI] ──► [Write to Postgres `campaigns` table]
                                         │ (Saves schedule & timezone)
                                         ▼
[Celery Beat Scheduler] ──► [Picks up pending campaigns matching time]
                                         │ (Triggers Celery Worker Task)
                                         ▼
                            [execute_campaign_broadcast_task]
                                         │ (Fetches contact phone list)
                                         │ (Loops contacts sequentially)
                                         ▼
                             [Send Outbound API Payload]
                                         │ (Injects random delay: 5s - 15s)
                                         ▼
                            [Write Postgres `campaign_logs`]
```

---

## 2. Dynamic Recurrence Mappings

Campaigns support 4 recurrence types saved in the `recurring_interval` column:
* `none`: Single execution. The campaign transitions to `"completed"` status post-execution.
* `daily`: Runs every 24 hours relative to the scheduled start time.
* `weekly`: Runs every 7 days.
* `monthly`: Runs on the same numerical date of the subsequent month.

---

## 3. Timezone-Aware Scheduling & Execution

To prevent broadcasts from firing during inappropriate hours, localized execution is enforced:
1. **Input Payload**: The customer sets the schedule using their local timezone (e.g., `America/New_York` or `Asia/Kolkata`) and input time.
2. **UTC Synchronization**: The API maps localized times to UTC timestamps before saving them in the `scheduled_for` database column.
3. **Task Evaluation**: The scheduler daemon parses UTC timestamps:
   ```python
   # Fetches campaigns where scheduled UTC time has passed
   pending = db.query(Campaign).filter(
       Campaign.scheduled_for <= datetime.utcnow(),
       Campaign.status == "scheduled"
   ).all()
   ```

---

## 4. Anti-Ban Throttling (Throttled Delay Controls)

Sending bulk messages simultaneously triggers instant automated bans from the WhatsApp network. To prevent this, the broadcaster loop implements throttled queues:
* **Inter-Message Delays**: A sleep timer is injected between consecutive contact dispatches (default range is **5 to 15 seconds**, configurable per campaign).
* **Jitter Control**: Dynamic random offsets (e.g., `random.uniform(1.2, 3.5)`) are appended to the sleep timer, simulating manual human typing and dispatch rhythms.
* **Batch Limits**: Large broadcasts are divided into batches (e.g., 50 contacts per batch) with longer cooldown periods between them.
