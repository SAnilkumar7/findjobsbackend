"""
Password reset via email code (Brevo HTTPS API).

Flow:  /forgot-password  ->  /verify-reset-code  ->  /reset-password

Only users.password_hash is changed. The user row, payments and user_access
records are never touched, so purchased access is preserved.

Wrong codes: 5 wrong attempts -> locked for 30 minutes (see lockout.py).
"""
import os
import hashlib
import logging
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import get_password_hash, validate_password_strength
from database import get_db
from lockout import ensure_not_locked, register_failure, clear_failures, LOCK_MINUTES
from models import PasswordReset, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["password-reset"])

# ---------------- Limits ----------------
CODE_EXPIRY_MINUTES = 10
TOKEN_EXPIRY_MINUTES = 10          # time allowed to set the new password after the code is verified
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_EMAIL_PER_HOUR = 5
IP_LIMITS_PER_HOUR = {"forgot": 10, "verify": 30, "reset": 20}

GENERIC_FORGOT_RESPONSE = {
    "success": True,
    "message": "If an account exists for this email, a reset code has been sent.",
}
INVALID_CODE_MSG = "Invalid or expired code."
INVALID_SESSION_MSG = "Reset session is invalid or has expired. Please start again."

_ip_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


# ---------------- Schemas ----------------
class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyResetCodeRequest(BaseModel):
    email: str
    otp_code: str


class ResetPasswordRequest(BaseModel):
    email: str
    reset_token: str
    new_password: str


# ---------------- Helpers ----------------
def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_ip_limit(bucket: str, ip: str):
    now = time.time()
    key = (bucket, ip)
    _ip_hits[key] = [t for t in _ip_hits[key] if t > now - 3600]
    if len(_ip_hits[key]) >= IP_LIMITS_PER_HOUR[bucket]:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    _ip_hits[key].append(now)


def _hash(email: str, value: str) -> str:
    return hashlib.sha256(f"{email}:{value}".encode()).hexdigest()


def _normalize_email(email: str) -> str:
    return (email or "").lower().strip()


async def _send_reset_email(to_email: str, code: str):
    """Runs in the background so response time is identical for existing and unknown emails."""
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL")
    sender_name = os.getenv("SENDER_NAME", "FindMyJobs")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                    "accept": "application/json",
                },
                json={
                    "sender": {"name": sender_name, "email": sender_email},
                    "to": [{"email": to_email}],
                    "subject": "Reset your FindMyJobs password",
                    "textContent": (
                        f"Your FindMyJobs password reset code is: {code}\n\n"
                        f"This code expires in {CODE_EXPIRY_MINUTES} minutes.\n"
                        "If you didn't request this, you can ignore this email. "
                        "Your password will not change."
                    ),
                },
            )
            if r.status_code >= 400:
                logger.error("Brevo error %s sending reset email: %s", r.status_code, r.text)
    except Exception as e:
        logger.error("Failed to send reset email to %s: %s", to_email, e)


async def _latest_record(db: AsyncSession, email: str):
    res = await db.execute(
        select(PasswordReset)
        .where(PasswordReset.email == email)
        .order_by(PasswordReset.created_at.desc())
    )
    return res.scalars().first()


# ---------------- Step 1: request a code ----------------
@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if not os.getenv("BREVO_API_KEY") or not os.getenv("SENDER_EMAIL"):
        raise HTTPException(status_code=500, detail="Email service not configured")

    _check_ip_limit("forgot", _client_ip(request))

    email = _normalize_email(req.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address")

    # Locked after too many wrong codes? (applies to any email, so nothing is revealed)
    await ensure_not_locked(db, "reset", email)

    now = datetime.utcnow()

    # Housekeeping: purge old expired rows
    await db.execute(delete(PasswordReset).where(PasswordReset.expires_at < now - timedelta(days=1)))

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()

    # Same response whether or not the account exists (no email enumeration)
    if not user or user.status == "Disabled":
        await db.commit()
        return GENERIC_FORGOT_RESPONSE

    count_res = await db.execute(
        select(func.count())
        .select_from(PasswordReset)
        .where(PasswordReset.email == email)
        .where(PasswordReset.created_at >= now - timedelta(hours=1))
    )
    if (count_res.scalar() or 0) >= MAX_CODES_PER_EMAIL_PER_HOUR:
        await db.commit()
        return GENERIC_FORGOT_RESPONSE

    last = await _latest_record(db, email)
    if last and (now - last.created_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        await db.commit()
        return GENERIC_FORGOT_RESPONSE

    code = str(secrets.randbelow(900000) + 100000)
    db.add(PasswordReset(
        id=f"pr_{uuid.uuid4().hex[:12]}",
        email=email,
        code_hash=_hash(email, code),
        attempts=0,
        is_verified=False,
        expires_at=now + timedelta(minutes=CODE_EXPIRY_MINUTES),
        created_at=now,
    ))
    await db.commit()

    background.add_task(_send_reset_email, email, code)
    return GENERIC_FORGOT_RESPONSE


# ---------------- Step 2: verify the code ----------------
@router.post("/verify-reset-code")
async def verify_reset_code(
    req: VerifyResetCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _check_ip_limit("verify", _client_ip(request))

    email = _normalize_email(req.email)
    code = (req.otp_code or "").strip()
    now = datetime.utcnow()

    # 5 wrong attempts -> 30 minute lock. Checked before looking at the code.
    await ensure_not_locked(db, "reset", email)

    record = await _latest_record(db, email)

    valid = (
        record is not None
        and not record.is_verified
        and now <= record.expires_at
        and secrets.compare_digest(record.code_hash, _hash(email, code))
    )

    if not valid:
        remaining = await register_failure(db, "reset", email)  # raises 429 on the 5th
        raise HTTPException(
            status_code=400,
            detail=f"{INVALID_CODE_MSG} {remaining} attempt(s) left before a {LOCK_MINUTES}-minute lock.",
        )

    reset_token = secrets.token_urlsafe(32)
    record.is_verified = True
    record.token_hash = _hash(email, reset_token)
    record.expires_at = now + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
    await db.commit()

    await clear_failures(db, "reset", email)

    return {"success": True, "reset_token": reset_token}


# ---------------- Step 3: set the new password ----------------
@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _check_ip_limit("reset", _client_ip(request))

    email = _normalize_email(req.email)
    validate_password_strength(req.new_password, email)  # strong password rule
    now = datetime.utcnow()

    record = await _latest_record(db, email)
    if (
        not record
        or not record.is_verified
        or not record.token_hash
        or now > record.expires_at
        or not secrets.compare_digest(record.token_hash, _hash(email, req.reset_token or ""))
    ):
        raise HTTPException(status_code=400, detail=INVALID_SESSION_MSG)

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()
    if not user or user.status == "Disabled":
        raise HTTPException(status_code=400, detail=INVALID_SESSION_MSG)

    user.password_hash = get_password_hash(req.new_password)

    # Single use: remove every reset record for this email
    await db.execute(delete(PasswordReset).where(PasswordReset.email == email))
    await db.commit()

    # Proving email ownership also lifts any login lock, so the user can sign in right away
    await clear_failures(db, "login", email)
    await clear_failures(db, "reset", email)

    return {"success": True, "message": "Password updated. You can now log in with your new password."}