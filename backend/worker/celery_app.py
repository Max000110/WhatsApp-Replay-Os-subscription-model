from celery import Celery
from celery.schedules import crontab
from app.config import settings

# Initialize Celery app mapping to Redis Broker
celery = Celery(
    "saas_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["worker.tasks"]
)

# Standard optimizations for low memory footprints
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1, # Process 1 task at a time per worker process
    task_acks_late=True,          # Acknowledge only after task completion
    result_expires=1800           # Purge old task metadata in Redis after 30 minutes
)

# ── Periodic Beat Schedule ────────────────────────────────────────────────────
# BUG-001: Scan for outbound messages stuck in 'sent' > 5 minutes
# Subscription: Hourly renewal and expiry reminders
# Termination: 5-min grace-period expiry enforcement
celery.conf.beat_schedule = {
    "scan-stuck-delivery-every-5min": {
        "task": "worker.tasks.scan_stuck_delivery_task",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "check-subscription-reminders-hourly": {
        "task": "worker.tasks.check_subscription_reminders_task",
        "schedule": crontab(minute=0),      # Every hour at :00
    },
    "process-autopay-renewals-hourly": {
        "task": "worker.tasks.process_autopay_renewals_task",
        "schedule": crontab(minute=30),     # Every hour at :30
    },
    "check-graceful-terminations-5min": {
        "task": "worker.tasks.check_graceful_terminations_task",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
}

if __name__ == "__main__":
    celery.start()

