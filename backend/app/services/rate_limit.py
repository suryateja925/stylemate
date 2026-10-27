import time

from fastapi import HTTPException, status
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import ApiRateLimit


def enforce_rate_limit(
    db: Session,
    user_id: str,
    action: str,
    limit: int,
    window_seconds: int,
) -> None:
    now = int(time.time())
    window_id = now // window_seconds
    dialect = db.get_bind().dialect.name
    update_values = {
        "window_id": window_id,
        "request_count": case(
            (ApiRateLimit.window_id == window_id, ApiRateLimit.request_count + 1),
            else_=1,
        ),
    }
    if dialect == "postgresql":
        insert = postgresql_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise RuntimeError("Rate limiting is not configured for this database dialect.")

    statement = insert(ApiRateLimit).values(
        user_id=user_id,
        action=action,
        window_id=window_id,
        request_count=1,
    )
    if dialect == "postgresql":
        statement = statement.on_conflict_do_update(
            constraint="uq_api_rate_limit_user_action",
            set_=update_values,
        )
    else:
        statement = statement.on_conflict_do_update(
            index_elements=[ApiRateLimit.user_id, ApiRateLimit.action],
            set_=update_values,
        )
    statement = statement.returning(ApiRateLimit.request_count)
    request_count = db.execute(statement).scalar_one()
    db.commit()
    if request_count > limit:
        retry_after = window_seconds - now % window_seconds
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
