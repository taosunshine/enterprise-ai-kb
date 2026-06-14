from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import RateLimitEvent


def enforce_rate_limit(
    db: Session,
    *,
    key: str,
    scope: str,
    limit: int,
    window_seconds: int,
) -> None:
    if limit <= 0:
        return

    cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
    count = db.scalar(
        select(func.count(RateLimitEvent.id)).where(
            RateLimitEvent.key == key,
            RateLimitEvent.scope == scope,
            RateLimitEvent.created_at >= cutoff,
        )
    )
    if count is not None and count >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(window_seconds)},
        )

    db.add(RateLimitEvent(key=key, scope=scope))
    # Keep this small DB-backed limiter from growing without bound.
    db.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at < cutoff - timedelta(days=1)))
    db.commit()
