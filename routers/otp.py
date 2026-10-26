
"""
OTP Router — email verification via Brevo HTTPS API (works on Render, no SMTP ports needed)
"""
import os
import secrets
import uuid
import time
import logging
import httpx
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, func
from database import get_db
from models import OtpVerification
from schemas import SendOtpRequest, VerifyOtpRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["otp"])

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME", "FindMyJobs")

# ---------------- Limits ----------------
OTP_EXPIRY_MINUTES = 5
MAX_VERIFY_ATTEMPTS = 5            # wrong guesses allowed per OTP
RESEND_COOLDOWN_SECONDS = 60       # min gap between OTPs for the same email
MAX_OTPS_PER_EMAIL_PER_HOUR = 5
MAX_OTP_REQUESTS_PER_IP_PER_HOUR = 20

# In-memory trackers (per server process)
_verify_attempts: dict[str, int] = defaultdict(int)
_ip_requests: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    """Real client IP (Render sits behind a proxy and sets X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_ip_rate_limit(ip: str):
    now = time.time()
    window_start = now - 3600
    _ip_requests[ip] = [t for t in _ip_requests[ip] if t > window_start]
    if len(_ip_requests[ip]) >= MAX_OTP_REQUESTS_PER_IP_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many OTP requests. Please try again later.",
        )
    _ip_requests[ip].append(now)


async def send_email_async(to_email: str, otp_code: str):
    """Sends the OTP email using Brevo's HTTPS API (port 443, never blocked)."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            json={
                "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
                "to": [{"email": to_email}],
                "subject": "Your FindMyJobs Verification Code",
                "textContent": (
                    f"Your FindMyJobs verification code is: {otp_code}\n\n"
                    f"This code expires in {OTP_EXPIRY_MINUTES} minutes."
                ),
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Brevo error {r.status_code}: {r.text}")


@router.post("/send-otp")
async def send_otp(
    req: SendOtpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not BREVO_API_KEY or not SENDER_EMAIL:
        raise HTTPException(status_code=500, detail="Email OTP service not configured")

    email = req.email.lower().strip()
    now = datetime.utcnow()

    # --- Rate limit by IP ---
    _check_ip_rate_limit(_client_ip(request))

    # --- Rate limit by email (uses existing created_at column, works across workers) ---
    hour_ago = now - timedelta(hours=1)
    count_result = await db.execute(
        select(func.count())
        .select_from(OtpVerification)
        .where(OtpVerification.email == email)
        .where(OtpVerification.created_at >= hour_ago)
    )
    if (count_result.scalar() or 0) >= MAX_OTPS_PER_EMAIL_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many OTP requests for this email. Please try again later.",
        )

    # --- Resend cooldown ---
    last_result = await db.execute(
        select(OtpVerification)
        .where(OtpVerification.email == email)
        .order_by(OtpVerification.created_at.desc())
    )
    last = last_result.scalars().first()
    if last and (now - last.created_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        wait = RESEND_COOLDOWN_SECONDS - int((now - last.created_at).total_seconds())
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait} seconds before requesting a new OTP.",
        )

    # --- Clean up old unverified / expired OTPs for this email (verified ones are kept) ---
    await db.execute(
        delete(OtpVerification)
        .where(OtpVerification.email == email)
        .where(OtpVerification.is_verified == False)  # noqa: E712
    )

    # --- Generate a cryptographically secure OTP ---
    otp_code = str(secrets.randbelow(900000) + 100000)

    record = OtpVerification(
        id=f"otp_{uuid.uuid4().hex[:12]}",
        email=email,
        otp_code=otp_code,
        is_verified=False,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        created_at=now,
    )
    db.add(record)
    await db.commit()  # save first, so an emailed code always exists in the DB

    # New OTP -> reset failed-attempt counter for this email
    _verify_attempts.pop(email, None)

    try:
        await send_email_async(email, otp_code)
    except Exception as e:
        logger.error("Failed to send OTP email to %s: %s", email, e)
        # Email failed, so remove the unusable OTP
        await db.delete(record)
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail="Failed to send OTP email. Please try again.",
        )

    return {"success": True, "message": "OTP sent to your email"}


@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    email = req.email.lower().strip()

    result = await db.execute(
        select(OtpVerification)
        .where(OtpVerification.email == email)
        .order_by(OtpVerification.created_at.desc())
    )
    record = result.scalars().first()

    if not record:
        raise HTTPException(status_code=400, detail="No OTP request found for this email")

    # Already verified with this OTP: nothing more to check
    if record.is_verified and secrets.compare_digest(
        str(record.otp_code), str(req.otp_code)
    ):
        return {"success": True, "message": "Email verified successfully"}

    if datetime.utcnow() > record.expires_at:
        _verify_attempts.pop(email, None)
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

    # Too many wrong guesses: force a new OTP
    if _verify_attempts[email] >= MAX_VERIFY_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Please request a new OTP.",
        )

    # Constant-time comparison
    if not secrets.compare_digest(str(record.otp_code), str(req.otp_code)):
        _verify_attempts[email] += 1
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    record.is_verified = True
    await db.commit()
    _verify_attempts.pop(email, None)

    return {"success": True, "message": "Email verified successfully"}