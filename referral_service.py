# """
# Helpers used by routers/auth.py, routers/payments.py and routers/referrals.py.

# IMPORTANT: every record_* / try_record_* function here
#   1. uses its OWN database session, and
#   2. swallows all errors (logs only).
# So a problem in referral tracking can never break registration, Google login,
# order creation or payment verification, and can never expire the caller's objects.
# """
# import logging
# import os
# import re
# from decimal import Decimal, ROUND_HALF_UP
# from typing import Optional

# from sqlalchemy import func
# from sqlalchemy.exc import IntegrityError
# from sqlalchemy.future import select

# from database import AsyncSessionLocal
# from models import Payment, User
# from referral_models import (
#     Creator, ReferralConversion, ReferralLink, ReferralOrderRef, ReferralSignup,
# )

# logger = logging.getLogger("referrals")

# CODE_RE = re.compile(r"^[A-Za-z0-9]{7}$")

# # ---- business rules (change here if you decide differently) ----
# FIRST_PURCHASE_ONLY = True   # commission only on the user's first successful purchase overall
# HOLD_DAYS = 7                # commission stays "pending" this long (your refund window), then becomes payable


# def site_url() -> str:
#     return (os.getenv("APP_URL") or "https://findmyjobs.in").rstrip("/")


# def normalize_code(raw: Optional[str]) -> Optional[str]:
#     code = (raw or "").strip()
#     return code if CODE_RE.match(code) else None


# async def get_active_link(session, code: str):
#     """Returns (link, creator) for an active link of an active creator, else None."""
#     res = await session.execute(
#         select(ReferralLink, Creator)
#         .join(Creator, Creator.id == ReferralLink.creator_id)
#         .where(
#             ReferralLink.code == code,
#             ReferralLink.is_active == True,   # noqa: E712
#             Creator.is_active == True,        # noqa: E712
#         )
#     )
#     return res.first()


# async def record_signup(user_id: str, ref_code: Optional[str]) -> None:
#     code = normalize_code(ref_code)
#     if not code:
#         return
#     try:
#         async with AsyncSessionLocal() as s:
#             found = await get_active_link(s, code)
#             if not found:
#                 return
#             link, _creator = found
#             s.add(ReferralSignup(user_id=str(user_id), link_id=link.id))
#             await s.commit()
#     except IntegrityError:
#         pass  # this user already has a signup row
#     except Exception:
#         logger.exception("record_signup failed (ignored)")


# async def record_order_ref(user_id: str, razorpay_order_id: str, ref_code: Optional[str]) -> None:
#     code = normalize_code(ref_code)
#     if not code or not razorpay_order_id:
#         return
#     try:
#         async with AsyncSessionLocal() as s:
#             found = await get_active_link(s, code)
#             if not found:
#                 return
#             link, _creator = found
#             s.add(ReferralOrderRef(
#                 razorpay_order_id=razorpay_order_id, user_id=str(user_id), link_id=link.id,
#             ))
#             await s.commit()
#     except IntegrityError:
#         pass
#     except Exception:
#         logger.exception("record_order_ref failed (ignored)")


# def _is_self_referral(creator: Creator, user: User) -> bool:
#     contact = (creator.contact or "").strip().lower()
#     if not contact:
#         return False
#     return contact in {(user.email or "").strip().lower(), (user.phone or "").strip().lower()}


# async def try_record_conversion(user_id: str, razorpay_order_id: str,
#                                 razorpay_payment_id: str, amount) -> None:
#     """
#     Called ONLY after a payment has been verified and saved (from the existing
#     _grant_access_for_payment, which both /verify and /webhook use).
#     Idempotent: payment_id is UNIQUE.
#     """
#     try:
#         async with AsyncSessionLocal() as s:
#             already = await s.scalar(
#                 select(ReferralConversion.id).where(ReferralConversion.payment_id == razorpay_payment_id)
#             )
#             if already:
#                 return

#             ref = (await s.execute(
#                 select(ReferralOrderRef).where(ReferralOrderRef.razorpay_order_id == razorpay_order_id)
#             )).scalars().first()
#             if not ref or ref.user_id != str(user_id):
#                 return

#             link = await s.get(ReferralLink, ref.link_id)
#             creator = await s.get(Creator, link.creator_id) if link else None
#             user = await s.get(User, user_id)
#             if not link or not creator or not user:
#                 return

#             if _is_self_referral(creator, user):
#                 logger.info("Skipped self-referral: creator=%s user=%s", creator.id, user_id)
#                 return

#             if FIRST_PURCHASE_ONLY:
#                 others = await s.scalar(
#                     select(func.count(Payment.id)).where(
#                         Payment.user_id == user_id,
#                         Payment.payment_id != razorpay_payment_id,
#                         Payment.status == "Successful",
#                     )
#                 )
#                 if others:
#                     return

#             amt = Decimal(str(amount)).quantize(Decimal("0.01"))
#             pct = Decimal(str(creator.commission_percent or 0))
#             commission = (amt * pct / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

#             s.add(ReferralConversion(
#                 link_id=link.id, creator_id=creator.id, user_id=str(user_id),
#                 payment_id=razorpay_payment_id, amount_paid=amt,
#                 commission_percent=pct, commission_amount=commission, status="pending",
#             ))
#             await s.commit()
#     except IntegrityError:
#         pass  # concurrent verify + webhook: the other one already credited it
#     except Exception:
#         logger.exception("try_record_conversion failed (ignored)")














"""
Helpers used by routers/auth.py, routers/payments.py and routers/referrals.py.

IMPORTANT: every record_* / try_record_* function here
  1. uses its OWN database session, and
  2. swallows all errors (logs only).
So a problem in referral tracking can never break registration, Google login,
order creation or payment verification, and can never expire the caller's objects.
"""
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import Payment, User
from referral_models import (
    Creator, ReferralConversion, ReferralLink, ReferralOrderRef, ReferralSignup,
)

logger = logging.getLogger("referrals")

CODE_RE = re.compile(r"^[A-Za-z0-9]{7}$")

# ---- business rules (change here if you decide differently) ----
FIRST_PURCHASE_ONLY = True   # commission only on the user's first successful purchase overall
HOLD_DAYS = 7                # commission stays "pending" this long (your refund window), then becomes payable

SITE_URL = "https://findmyjobs.in"


def site_url() -> str:
    return SITE_URL


def normalize_code(raw: Optional[str]) -> Optional[str]:
    code = (raw or "").strip()
    return code if CODE_RE.match(code) else None


async def get_active_link(session, code: str):
    """Returns (link, creator) for an active link of an active creator, else None."""
    res = await session.execute(
        select(ReferralLink, Creator)
        .join(Creator, Creator.id == ReferralLink.creator_id)
        .where(
            ReferralLink.code == code,
            ReferralLink.is_active == True,   # noqa: E712
            Creator.is_active == True,        # noqa: E712
        )
    )
    return res.first()


async def record_signup(user_id: str, ref_code: Optional[str]) -> None:
    code = normalize_code(ref_code)
    if not code:
        return
    try:
        async with AsyncSessionLocal() as s:
            found = await get_active_link(s, code)
            if not found:
                return
            link, _creator = found
            s.add(ReferralSignup(user_id=str(user_id), link_id=link.id))
            await s.commit()
    except IntegrityError:
        pass  # this user already has a signup row
    except Exception:
        logger.exception("record_signup failed (ignored)")


async def record_order_ref(user_id: str, razorpay_order_id: str, ref_code: Optional[str]) -> None:
    code = normalize_code(ref_code)
    if not code or not razorpay_order_id:
        return
    try:
        async with AsyncSessionLocal() as s:
            found = await get_active_link(s, code)
            if not found:
                return
            link, _creator = found
            s.add(ReferralOrderRef(
                razorpay_order_id=razorpay_order_id, user_id=str(user_id), link_id=link.id,
            ))
            await s.commit()
    except IntegrityError:
        pass
    except Exception:
        logger.exception("record_order_ref failed (ignored)")


def _is_self_referral(creator: Creator, user: User) -> bool:
    contact = (creator.contact or "").strip().lower()
    if not contact:
        return False
    return contact in {(user.email or "").strip().lower(), (user.phone or "").strip().lower()}


async def try_record_conversion(user_id: str, razorpay_order_id: str,
                                razorpay_payment_id: str, amount) -> None:
    """
    Called ONLY after a payment has been verified and saved (from the existing
    _grant_access_for_payment, which both /verify and /webhook use).
    Idempotent: payment_id is UNIQUE.
    """
    try:
        async with AsyncSessionLocal() as s:
            already = await s.scalar(
                select(ReferralConversion.id).where(ReferralConversion.payment_id == razorpay_payment_id)
            )
            if already:
                return

            ref = (await s.execute(
                select(ReferralOrderRef).where(ReferralOrderRef.razorpay_order_id == razorpay_order_id)
            )).scalars().first()
            if not ref or ref.user_id != str(user_id):
                return

            link = await s.get(ReferralLink, ref.link_id)
            creator = await s.get(Creator, link.creator_id) if link else None
            user = await s.get(User, user_id)
            if not link or not creator or not user:
                return

            if _is_self_referral(creator, user):
                logger.info("Skipped self-referral: creator=%s user=%s", creator.id, user_id)
                return

            if FIRST_PURCHASE_ONLY:
                others = await s.scalar(
                    select(func.count(Payment.id)).where(
                        Payment.user_id == user_id,
                        Payment.payment_id != razorpay_payment_id,
                        Payment.status == "Successful",
                    )
                )
                if others:
                    return

            amt = Decimal(str(amount)).quantize(Decimal("0.01"))
            pct = Decimal(str(creator.commission_percent or 0))
            commission = (amt * pct / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            s.add(ReferralConversion(
                link_id=link.id, creator_id=creator.id, user_id=str(user_id),
                payment_id=razorpay_payment_id, amount_paid=amt,
                commission_percent=pct, commission_amount=commission, status="pending",
            ))
            await s.commit()
    except IntegrityError:
        pass  # concurrent verify + webhook: the other one already credited it
    except Exception:
        logger.exception("try_record_conversion failed (ignored)")