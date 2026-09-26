from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("immo_workers", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.task_routes = {
    "app.workers.tasks.*": {"queue": "default"},
    "app.workers.tasks_ocr.*": {"queue": "default"},
}
celery_app.autodiscover_tasks(["app.workers"], related_name="tasks_ocr")

# Import explicite pour enregistrer les tasks OCR au démarrage worker
import app.workers.tasks_ocr  # noqa: E402,F401


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    return "pong"
