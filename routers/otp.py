"""
OTP Router — email verification via Gmail SMTP (free, no third-party API)
"""
import os
import random
import uuid
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database import get_db
from ..models import OtpVerification
from ..schemas import SendOtpRequest, VerifyOtpRequest

router = APIRouter(prefix="/api/auth", tags=["otp"])

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def send_email_sync(to_email: str, otp_code: str):
    """Sends the OTP email using Gmail's SMTP server."""
    msg = MIMEText(
        f"Your JobAccess verification code is: {otp_code}\n\nThis code expires in 5 minutes."
    )
    msg["Subject"] = "Your JobAccess Verification Code"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_email], msg.as_string())


@router.post("/send-otp")
async def send_otp(req: SendOtpRequest, db: AsyncSession = Depends(get_db)):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise HTTPException(status_code=500, detail="Email OTP service not configured")

    email = req.email.lower().strip()
    otp_code = str(random.randint(100000, 999999))

    try:
        send_email_sync(email, otp_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send OTP email: {str(e)}")

    record = OtpVerification(
        id=f"otp_{uuid.uuid4().hex[:12]}",
        email=email,
        otp_code=otp_code,
        is_verified=False,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        created_at=datetime.utcnow(),
    )
    db.add(record)
    await db.commit()

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
    if datetime.utcnow() > record.expires_at:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
    if record.otp_code != req.otp_code:
        raise HTTPException(status_code=400, detail="Incorrect OTP")

    record.is_verified = True
    await db.commit()

    return {"success": True, "message": "Email verified successfully"}