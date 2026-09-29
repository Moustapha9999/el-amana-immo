from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("immo_workers", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.task_routes = {
    "app.workers.tasks.*": {"queue": "default"},
    "app.workers.tasks_ocr.*": {"queue": "default"},
    "app.workers.tasks_supervision.*": {"queue": "default"},
}
celery_app.conf.timezone = "Africa/Nouakchott"
# Planification (beat embarqué dans le worker : `celery worker -B`).
celery_app.conf.beat_schedule = {
    "supervision-purge-api-errors": {
        "task": "app.workers.tasks_supervision.purge_api_error_events",
        "schedule": crontab(hour=2, minute=30),
    },
    "supervision-server-error-spike": {
        "task": "app.workers.tasks_supervision.check_server_error_spike",
        "schedule": 300.0,
    },
}
celery_app.autodiscover_tasks(["app.workers"], related_name="tasks_ocr")

# Import explicite pour enregistrer les tasks au démarrage worker
import app.workers.tasks_ocr  # noqa: E402,F401
import app.workers.tasks_supervision  # noqa: E402,F401


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"
