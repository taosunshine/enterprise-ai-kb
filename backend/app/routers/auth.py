from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserCreate
from app.services.audit import client_ip, record_audit
from app.services.rate_limits import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(
        db,
        key=client_ip(request),
        scope="auth_register",
        limit=settings.auth_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )
    if db.scalar(select(User).where(User.email == payload.email)):
        record_audit(
            db, request, action="auth.register", status="failed", details={"reason": "duplicate"}
        )
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit(db, request, action="auth.register", user_id=user.id)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(
        db,
        key=client_ip(request),
        scope="auth_login",
        limit=settings.auth_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        record_audit(
            db,
            request,
            action="auth.login",
            user_id=user.id if user else None,
            status="failed",
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    record_audit(db, request, action="auth.login", user_id=user.id)
    return TokenResponse(access_token=create_access_token(user.id))
