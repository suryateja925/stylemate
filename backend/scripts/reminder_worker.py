"""Persistent in-app reminder worker.

Run one worker alongside the API in deployments that want notifications:
    python -m backend.scripts.reminder_worker

The schedule is stored in the application database, so reloads do not erase it.
This worker creates durable in-app notifications; browser/OS push delivery is a
separate deployment concern and is never claimed automatically.
"""

from datetime import datetime, timezone
import logging
import time

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from backend.app.database import SessionLocal, init_db
from backend.app.core.config import settings
from backend.app.models import AppNotification, PreparationTask

logger = logging.getLogger("stylemate.reminder_worker")


def deliver_due_notifications() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        tasks = db.scalars(
            select(PreparationTask).where(
                PreparationTask.status.in_(["pending", "snoozed"]),
                PreparationTask.due_at <= now,
                PreparationTask.notification_created_at.is_(None),
            )
        ).all()
        for task in tasks:
            db.add(AppNotification(
                user_id=task.user_id,
                task_id=task.id,
                title="StyleMate preparation reminder",
                message=task.title,
                scheduled_for=task.due_at,
            ))
            task.notification_created_at = now
        db.commit()
        return len(tasks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not settings.is_production:
        init_db()
    print("StyleMate reminder worker is running. Press Ctrl+C to stop.")
    while True:
        try:
            created = deliver_due_notifications()
        except SQLAlchemyError:
            logger.exception("Reminder job failed; it will retry after the next interval.")
        else:
            if created:
                logger.info("Created %s in-app notification(s).", created)
        time.sleep(60)
