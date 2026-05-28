from celery import Celery
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
    task_acks_late=True           # Acknowledge only after task completion
)

if __name__ == "__main__":
    celery.start()
