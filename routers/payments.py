"""
FastAPI Payments Router
Enforces:
1. Server-side price lookup from DB (client price never trusted)
2. Real Razorpay order creation via Orders API
3. Razorpay HMAC-SHA256 signature verification
4. Atomic Database Transactions (single session commit)
5. Idempotency against duplicate webhook / concurrent clicks
6. Database-level unique constraint on payment_id and (user_id, package_id)
7. Server-to-server webhook so payment isn't lost if the browser closes
"""

import os
import json
import hmac
import hashlib
import logging
import uuid
from datetime import datetime
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from database import get_db
from models import User, Package, Payment, UserAccess
from schemas import CreateOrderRequest, VerifyPaymentRequest
from auth import get_current_user

router = APIRouter(prefix="/api/payments", tags=["payments"])
logger = logging.getLogger("payments")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_mock_jobaccess")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "mock_razorpay_secret_key")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
razorpay_client.session.timeout = 10  # seconds — stop a slow Razorpay call from hanging a worker


@router.post("/create-order")
async def create_order(
    req: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a REAL Razorpay order via their Orders API, with price fetched
    directly from the DB (client price never trusted).
    """
    if not RAZORPAY_KEY_SECRET or RAZORPAY_KEY_SECRET == "mock_razorpay_secret_key":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment gateway is not configured correctly.",
        )

    pkg_res = await db.execute(select(Package).where(Package.id == req.package_id))
    package = pkg_res.scalars().first()
    if not package or not package.is_active:
        raise HTTPException(status_code=400, detail="Invalid or inactive package")

    amount_paise = int(package.price * 100)

    try:
        razorpay_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"receipt_{uuid.uuid4().hex[:10]}",
            "notes": {
                "package_id": package.id,
                "user_id": current_user.id,
            },
        })
    except Exception as e:
        logger.error(f"Razorpay order creation failed for user={current_user.id} package={package.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create Razorpay order: {str(e)}",
        )

    return {
        "order_id": razorpay_order["id"],
        "amount": amount_paise,
        "amount_in_rupees": float(package.price),
        "currency": "INR",
        "key_id": RAZORPAY_KEY_ID,
        "package": {
            "id": package.id,
            "name": package.name,
            "slug": package.slug,
            "price": float(package.price),
        },
    }


async def _grant_access_for_payment(
    db: AsyncSession,
    user_id: str,
    package: Package,
    razorpay_order_id: str,
    razorpay_payment_id: str,
) -> dict:
    """
    Shared logic used by BOTH /verify (browser-triggered) and /webhook
    (Razorpay server-triggered). Keeping this in one place means a fix
    here fixes both paths — no risk of them drifting apart.

    Idempotent: checking payment_id first means calling this twice with
    the same payment_id is always safe.
    """
    existing_payment_res = await db.execute(
        select(Payment).where(Payment.payment_id == razorpay_payment_id)
    )
    existing_payment = existing_payment_res.scalars().first()
    if existing_payment:
        return {
            "success": True,
            "idempotent": True,
            "message": "Payment was already verified and access is active.",
            "payment_id": existing_payment.payment_id,
        }

    try:
        now = datetime.utcnow()
        payment_record = Payment(
            id=f"pay_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            package_id=package.id,
            order_id=razorpay_order_id,
            payment_id=razorpay_payment_id,
            amount=package.price,
            currency="INR",
            gateway="razorpay",
            status="Successful",
            created_at=now,
        )
        db.add(payment_record)

        packages_to_grant = [package.id]
        if package.access_type == "ALL":
            # Only active packages — a retired package shouldn't be grantable
            # via an "All Access" purchase.
            all_pkgs_res = await db.execute(select(Package).where(Package.is_active == True))
            all_pkgs = all_pkgs_res.scalars().all()
            packages_to_grant = [p.id for p in all_pkgs]

        for pkg_id in packages_to_grant:
            existing_acc_res = await db.execute(
                select(UserAccess).where(
                    UserAccess.user_id == user_id,
                    UserAccess.package_id == pkg_id,
                )
            )
            existing_acc = existing_acc_res.scalars().first()
            if existing_acc:
                existing_acc.status = "Active"
                existing_acc.payment_id = razorpay_payment_id
                existing_acc.start_date = now
            else:
                new_acc = UserAccess(
                    id=f"acc_{uuid.uuid4().hex[:12]}",
                    user_id=user_id,
                    package_id=pkg_id,
                    payment_id=razorpay_payment_id,
                    status="Active",
                    start_date=now,
                    expiry_date=None,
                    created_at=now,
                )
                db.add(new_acc)

        await db.commit()

        logger.info(f"Access granted: user={user_id} package={package.id} payment={razorpay_payment_id}")

        return {
            "success": True,
            "message": f"Payment verified successfully! Access to {package.name} unlocked.",
            "payment_id": payment_record.payment_id,
            "amount": float(payment_record.amount),
        }

    except IntegrityError:
        await db.rollback()
        existing_check = await db.execute(
            select(Payment).where(Payment.payment_id == razorpay_payment_id)
        )
        if existing_check.scalars().first():
            return {
                "success": True,
                "idempotent": True,
                "message": "Payment verified via concurrent execution.",
            }
        logger.error(f"Payment conflict with no resolving row: user={user_id} payment={razorpay_payment_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent payment transaction conflict. Please refresh.",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Access grant failed: user={user_id} payment={razorpay_payment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction failed: {str(e)}",
        )


@router.post("/verify")
async def verify_payment(
    req: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Browser-triggered verification, called right after Razorpay's checkout
    popup closes. Fast path for the common case. The /webhook endpoint below
    is the safety net for when this call never happens (tab closed, network
    drop, browser crash).
    """
    if not RAZORPAY_KEY_SECRET or RAZORPAY_KEY_SECRET == "mock_razorpay_secret_key":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment gateway is not configured correctly.",
        )

    expected_sig = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{req.razorpay_order_id}|{req.razorpay_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, req.razorpay_signature):
        logger.warning(f"Signature mismatch: user={current_user.id} payment={req.razorpay_payment_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay signature validation failed. Access not granted.",
        )

    pkg_res = await db.execute(select(Package).where(Package.id == req.package_id))
    package = pkg_res.scalars().first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    return await _grant_access_for_payment(
        db=db,
        user_id=current_user.id,
        package=package,
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
    )


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Called by RAZORPAY'S SERVERS directly — not the user's browser.
    This is what saves you when a user pays but closes the tab before
    /verify fires: Razorpay still tells you about it here.

    Must be registered in the Razorpay Dashboard under
    Settings → Webhooks, pointing at:
        https://yourdomain.com/api/payments/webhook
    Subscribe to the "payment.captured" event.
    Uses a SEPARATE secret from your API key — generate it when you
    create the webhook, and put it in .env as RAZORPAY_WEBHOOK_SECRET.
    """
    if not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook is not configured")

    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    expected_sig = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        logger.warning("Webhook signature mismatch — possible forged request")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = json.loads(body)

    if payload.get("event") != "payment.captured":
        return {"status": "ignored"}

    payment_entity = payload["payload"]["payment"]["entity"]
    razorpay_payment_id = payment_entity["id"]
    razorpay_order_id = payment_entity["order_id"]
    notes = payment_entity.get("notes", {})
    package_id = notes.get("package_id")
    user_id = notes.get("user_id")

    if not package_id or not user_id:
        logger.warning(f"Webhook payment.captured missing notes: payment={razorpay_payment_id}")
        return {"status": "ignored", "reason": "missing notes"}

    pkg_res = await db.execute(select(Package).where(Package.id == package_id))
    package = pkg_res.scalars().first()
    if not package:
        logger.error(f"Webhook: package not found: package={package_id} payment={razorpay_payment_id}")
        return {"status": "ignored", "reason": "package not found"}

    result = await _grant_access_for_payment(
        db=db,
        user_id=user_id,
        package=package,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
    )
    return {"status": "processed", **result}


@router.get("/history")
async def payment_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payment).where(Payment.user_id == current_user.id).order_by(Payment.created_at.desc())
    )
    payments = result.scalars().all()
    return payments