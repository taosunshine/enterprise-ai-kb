import json

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded or (request.client.host if request.client else "")


def record_audit(
    db: Session,
    request: Request,
    *,
    action: str,
    user_id: int | None = None,
    resource_type: str = "",
    resource_id: int | str | None = None,
    status: str = "success",
    details: dict[str, str | int | bool] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id or ""),
            status=status,
            ip_address=client_ip(request),
            details_json=json.dumps(details or {}, ensure_ascii=False),
        )
    )
    db.commit()
