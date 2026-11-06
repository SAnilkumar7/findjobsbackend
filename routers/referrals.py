"""
Creator referral tracking.

  PUBLIC   POST /api/referrals/{code}/click          (records a click, returns where to redirect)
  ADMIN    /api/admin/referrals/...                  (every route uses your existing get_current_admin)

Nothing here touches job content: the public endpoint only returns job_id + category,
so locked jobs stay locked until the user signs in AND has paid (jobs.py is unchanged).
"""
import csv
import io
import re
import secrets
import string
import time
from collections import deque
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from auth import get_current_admin
from database import get_db, today_ist
from models import Admin, Job, User, generate_uuid
from referral_models import (
    Creator, CreatorPayout, ReferralClick, ReferralConversion, ReferralLink, ReferralSignup,
)
from referral_service import HOLD_DAYS, get_active_link, normalize_code, site_url

public_router = APIRouter(prefix="/api/referrals", tags=["referrals"])
admin_router = APIRouter(prefix="/api/admin/referrals", tags=["referrals-admin"])

VISITOR_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_ALPHABET = string.ascii_letters + string.digits


def _f(x) -> float:
    return float(x or 0)


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(7))


# ------------------------- tiny per-IP rate limiter (public endpoint) -------------------------
# Best effort, per server process. It limits abuse of the public click endpoint;
# it is NOT used for anything money-related.
_RATE_LIMIT = 30
_RATE_WINDOW = 60.0
_hits: dict = {}


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    dq = _hits.setdefault(key, deque())
    while dq and now - dq[0] > _RATE_WINDOW:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT:
        return True
    dq.append(now)
    if len(_hits) > 5000:  # keep memory bounded
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > _RATE_WINDOW]:
            _hits.pop(k, None)
    return False


# ------------------------------------- schemas -------------------------------------
class ClickBody(BaseModel):
    visitor_id: Optional[str] = None


class CreatorCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    handle: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=30)
    contact: Optional[str] = Field(None, max_length=150)
    commission_percent: float = Field(0, ge=0, le=100)
    notes: Optional[str] = Field(None, max_length=1000)


class CreatorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    handle: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=30)
    contact: Optional[str] = Field(None, max_length=150)
    commission_percent: Optional[float] = Field(None, ge=0, le=100)
    notes: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None


class LinkCreate(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=64)
    creator_id: str = Field(..., min_length=1, max_length=64)


class LinkUpdate(BaseModel):
    is_active: bool


class PayoutBody(BaseModel):
    method: Optional[str] = Field(None, max_length=30)      # e.g. UPI / Bank
    reference: Optional[str] = Field(None, max_length=100)  # e.g. UPI transaction id
    note: Optional[str] = Field(None, max_length=1000)


def _creator_out(c: Creator) -> dict:
    return {
        "id": c.id, "name": c.name, "handle": c.handle, "platform": c.platform,
        "contact": c.contact, "commission_percent": _f(c.commission_percent),
        "is_active": c.is_active, "notes": c.notes, "created_at": c.created_at,
    }


def _link_out(l: ReferralLink, creator_name: str) -> dict:
    return {
        "id": l.id, "code": l.code, "url": f"{site_url()}/r/{l.code}",
        "job_id": l.job_id, "job_title": l.job_title, "category_id": l.category_id,
        "creator_id": l.creator_id, "creator_name": creator_name,
        "is_active": l.is_active, "created_at": l.created_at,
    }


def _range(col, d_from: Optional[date], d_to: Optional[date]) -> list:
    conds = []
    if d_from:
        conds.append(col >= datetime.combine(d_from, datetime.min.time()))
    if d_to:  # inclusive end date
        conds.append(col < datetime.combine(d_to + timedelta(days=1), datetime.min.time()))
    return conds


# ============================== PUBLIC: record a click ==============================
@public_router.post("/{code}/click")
async def track_click(
    code: str,
    request: Request,
    body: Optional[ClickBody] = None,
    db: AsyncSession = Depends(get_db),
):
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    code = normalize_code(code)
    if not code:
        raise HTTPException(status_code=404, detail="Link not found")

    found = await get_active_link(db, code)
    if not found:
        raise HTTPException(status_code=404, detail="Link not found")
    link, _creator = found

    job = (await db.execute(select(Job).where(Job.id == link.job_id))).scalars().first()
    if not job or job.status != "Published" or (job.deadline or "") < today_ist():
        raise HTTPException(status_code=404, detail="Link not found")

    target = {"job_id": job.id, "category": job.category_id}
    link_id = link.id

    visitor_id = body.visitor_id if body and body.visitor_id and VISITOR_RE.match(body.visitor_id) else None
    try:
        if visitor_id:
            since = datetime.utcnow() - timedelta(minutes=30)
            dup = await db.scalar(
                select(ReferralClick.id).where(
                    ReferralClick.link_id == link_id,
                    ReferralClick.visitor_id == visitor_id,
                    ReferralClick.clicked_at >= since,
                ).limit(1)
            )
            if dup:
                return target
        db.add(ReferralClick(link_id=link_id, visitor_id=visitor_id))
        await db.commit()
    except Exception:
        await db.rollback()  # a failed click must never block the redirect
    return target


# ===================================== ADMIN: creators =====================================
@admin_router.post("/creators", status_code=201)
async def create_creator(body: CreatorCreate, admin: Admin = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    c = Creator(
        name=body.name.strip(), handle=(body.handle or "").strip() or None,
        platform=(body.platform or "").strip() or None, contact=(body.contact or "").strip() or None,
        commission_percent=Decimal(str(body.commission_percent)),
        notes=(body.notes or "").strip() or None,
    )
    db.add(c)
    await db.commit()
    return _creator_out(c)


@admin_router.get("/creators")
async def list_creators(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Creator).order_by(Creator.created_at.desc()))
    return [_creator_out(c) for c in res.scalars().all()]


@admin_router.patch("/creators/{creator_id}")
async def update_creator(creator_id: str, body: CreatorUpdate, admin: Admin = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    c = await db.get(Creator, creator_id)
    if not c:
        raise HTTPException(status_code=404, detail="Creator not found")
    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        if key == "commission_percent":
            if val is None:
                continue
            val = Decimal(str(val))   # only affects FUTURE purchases (past ones keep their snapshot)
        elif key == "is_active":
            if val is None:
                continue
        elif isinstance(val, str):
            val = val.strip() or None
        if key == "name" and not val:
            continue
        setattr(c, key, val)
    await db.commit()
    return _creator_out(c)


# ====================================== ADMIN: links ======================================
@admin_router.post("/links", status_code=201)
async def create_link(body: LinkCreate, admin: Admin = Depends(get_current_admin),
                      db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(Job).where(Job.id == body.job_id))).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    creator = await db.get(Creator, body.creator_id)
    if not creator or not creator.is_active:
        raise HTTPException(status_code=404, detail="Creator not found or inactive")

    # copy values now: a rollback below would expire these objects
    job_id, job_title, category_id = job.id, job.title, job.category_id
    creator_id, creator_name = creator.id, creator.name

    async def _existing():
        r = await db.execute(select(ReferralLink).where(
            ReferralLink.job_id == job_id, ReferralLink.creator_id == creator_id))
        return r.scalars().first()

    link = await _existing()
    if link:
        return _link_out(link, creator_name)   # one link per (job, creator); returns the same one

    for _ in range(6):
        link = ReferralLink(code=_new_code(), job_id=job_id, job_title=job_title,
                            category_id=category_id, creator_id=creator_id)
        db.add(link)
        try:
            await db.commit()
            return _link_out(link, creator_name)
        except IntegrityError:
            await db.rollback()
            again = await _existing()
            if again:
                return _link_out(again, creator_name)
    raise HTTPException(status_code=500, detail="Could not generate a unique code. Please try again.")


@admin_router.get("/links")
async def list_links(creator_id: Optional[str] = None, job_id: Optional[str] = None,
                     admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    q = select(ReferralLink, Creator.name).join(Creator, Creator.id == ReferralLink.creator_id)
    if creator_id:
        q = q.where(ReferralLink.creator_id == creator_id)
    if job_id:
        q = q.where(ReferralLink.job_id == job_id)
    rows = (await db.execute(q.order_by(ReferralLink.created_at.desc()))).all()
    return [_link_out(l, n) for l, n in rows]


@admin_router.patch("/links/{link_id}")
async def update_link(link_id: str, body: LinkUpdate, admin: Admin = Depends(get_current_admin),
                      db: AsyncSession = Depends(get_db)):
    link = await db.get(ReferralLink, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    link.is_active = body.is_active
    await db.commit()
    return {"success": True, "id": link_id, "is_active": body.is_active}


# ===================================== ADMIN: stats =====================================
@admin_router.get("/stats")
async def referral_stats(
    creator_id: Optional[str] = None,
    job_id: Optional[str] = None,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    clicks / unique visitors / signups / paid users / revenue / commission per creator and per link.
    Dates (from/to, YYYY-MM-DD, inclusive) are UTC and filter the activity shown.
    payable_now and total_paid_out ignore the date filter (they are balances).
    """
    lq = select(ReferralLink, Creator.name).join(Creator, Creator.id == ReferralLink.creator_id)
    if creator_id:
        lq = lq.where(ReferralLink.creator_id == creator_id)
    if job_id:
        lq = lq.where(ReferralLink.job_id == job_id)
    link_rows = (await db.execute(lq)).all()
    empty_totals = {"clicks": 0, "signups": 0, "paid_users": 0, "revenue": 0.0,
                    "commission_earned": 0.0, "payable_now": 0.0, "total_paid_out": 0.0}
    if not link_rows:
        return {"creators": [], "totals": empty_totals}

    link_ids = [l.id for l, _ in link_rows]
    creator_ids = list({l.creator_id for l, _ in link_rows})
    cutoff = datetime.utcnow() - timedelta(days=HOLD_DAYS)

    click_conds = [ReferralClick.link_id.in_(link_ids)] + _range(ReferralClick.clicked_at, from_date, to_date)
    clicks = {r[0]: (r[1], r[2]) for r in (await db.execute(
        select(ReferralClick.link_id, func.count(ReferralClick.id),
               func.count(func.distinct(ReferralClick.visitor_id)))
        .where(*click_conds).group_by(ReferralClick.link_id))).all()}

    uniq_by_creator = dict((await db.execute(
        select(ReferralLink.creator_id, func.count(func.distinct(ReferralClick.visitor_id)))
        .join(ReferralClick, ReferralClick.link_id == ReferralLink.id)
        .where(*click_conds).group_by(ReferralLink.creator_id))).all())

    signups = dict((await db.execute(
        select(ReferralSignup.link_id, func.count(ReferralSignup.id))
        .where(ReferralSignup.link_id.in_(link_ids), *_range(ReferralSignup.created_at, from_date, to_date))
        .group_by(ReferralSignup.link_id))).all())

    conv_conds = [ReferralConversion.link_id.in_(link_ids)] + _range(ReferralConversion.created_at, from_date, to_date)
    conv: dict = {}
    for link_id, st, cnt, amt, com in (await db.execute(
        select(ReferralConversion.link_id, ReferralConversion.status, func.count(ReferralConversion.id),
               func.coalesce(func.sum(ReferralConversion.amount_paid), 0),
               func.coalesce(func.sum(ReferralConversion.commission_amount), 0))
        .where(*conv_conds).group_by(ReferralConversion.link_id, ReferralConversion.status))).all():
        d = conv.setdefault(link_id, {"paid_users": 0, "revenue": 0.0, "earned": 0.0, "paid": 0.0})
        if st == "reversed":
            continue
        d["paid_users"] += cnt
        d["revenue"] += _f(amt)
        d["earned"] += _f(com)
        if st == "paid":
            d["paid"] += _f(com)

    approved = dict((await db.execute(
        select(ReferralConversion.link_id, func.coalesce(func.sum(ReferralConversion.commission_amount), 0))
        .where(*conv_conds, ReferralConversion.status == "pending", ReferralConversion.created_at <= cutoff)
        .group_by(ReferralConversion.link_id))).all())

    payable = dict((await db.execute(
        select(ReferralConversion.creator_id, func.coalesce(func.sum(ReferralConversion.commission_amount), 0))
        .where(ReferralConversion.creator_id.in_(creator_ids), ReferralConversion.status == "pending",
               ReferralConversion.created_at <= cutoff)
        .group_by(ReferralConversion.creator_id))).all())
    paid_out = dict((await db.execute(
        select(CreatorPayout.creator_id, func.coalesce(func.sum(CreatorPayout.amount), 0))
        .where(CreatorPayout.creator_id.in_(creator_ids)).group_by(CreatorPayout.creator_id))).all())

    creators: dict = {}
    for link, cname in link_rows:
        c = creators.setdefault(link.creator_id, {
            "creator_id": link.creator_id, "name": cname,
            "clicks": 0, "unique_visitors": uniq_by_creator.get(link.creator_id, 0),
            "signups": 0, "paid_users": 0, "revenue": 0.0, "commission_earned": 0.0,
            "commission_paid": 0.0, "commission_approved": 0.0, "commission_in_hold": 0.0,
            "payable_now": _f(payable.get(link.creator_id)),
            "total_paid_out": _f(paid_out.get(link.creator_id)),
            "links": [],
        })
        cl, un = clicks.get(link.id, (0, 0))
        cv = conv.get(link.id, {"paid_users": 0, "revenue": 0.0, "earned": 0.0, "paid": 0.0})
        appr = _f(approved.get(link.id))
        hold = round(cv["earned"] - cv["paid"] - appr, 2)
        c["clicks"] += cl
        c["signups"] += signups.get(link.id, 0)
        c["paid_users"] += cv["paid_users"]
        c["revenue"] += cv["revenue"]
        c["commission_earned"] += cv["earned"]
        c["commission_paid"] += cv["paid"]
        c["commission_approved"] += appr
        c["commission_in_hold"] += hold
        c["links"].append({
            "link_id": link.id, "code": link.code, "url": f"{site_url()}/r/{link.code}",
            "job_id": link.job_id, "job_title": link.job_title, "category_id": link.category_id,
            "is_active": link.is_active, "clicks": cl, "unique_visitors": un,
            "signups": signups.get(link.id, 0), "paid_users": cv["paid_users"],
            "revenue": round(cv["revenue"], 2), "commission_earned": round(cv["earned"], 2),
            "commission_paid": round(cv["paid"], 2), "commission_approved": round(appr, 2),
            "commission_in_hold": hold,
        })

    out = sorted(creators.values(), key=lambda c: c["revenue"], reverse=True)
    for c in out:
        for k in ("revenue", "commission_earned", "commission_paid", "commission_approved", "commission_in_hold"):
            c[k] = round(c[k], 2)
    totals = {
        "clicks": sum(c["clicks"] for c in out), "signups": sum(c["signups"] for c in out),
        "paid_users": sum(c["paid_users"] for c in out),
        "revenue": round(sum(c["revenue"] for c in out), 2),
        "commission_earned": round(sum(c["commission_earned"] for c in out), 2),
        "payable_now": round(sum(c["payable_now"] for c in out), 2),
        "total_paid_out": round(sum(c["total_paid_out"] for c in out), 2),
    }
    return {"creators": out, "totals": totals}


# ============================ ADMIN: conversions, payouts, export ============================
def _conversion_rows_query(creator_id, status_filter, d_from, d_to):
    q = (select(ReferralConversion, Creator.name, ReferralLink.job_title, User.email)
         .join(Creator, Creator.id == ReferralConversion.creator_id)
         .join(ReferralLink, ReferralLink.id == ReferralConversion.link_id)
         .outerjoin(User, User.id == ReferralConversion.user_id))
    if creator_id:
        q = q.where(ReferralConversion.creator_id == creator_id)
    if status_filter:
        q = q.where(ReferralConversion.status == status_filter)
    for cond in _range(ReferralConversion.created_at, d_from, d_to):
        q = q.where(cond)
    return q.order_by(ReferralConversion.created_at.desc())


def _state(conv: ReferralConversion, cutoff: datetime) -> str:
    if conv.status == "pending" and conv.created_at <= cutoff:
        return "approved"   # past the hold period => payable
    return conv.status


@admin_router.get("/conversions")
async def list_conversions(
    creator_id: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(pending|paid|reversed)$"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    limit: int = Query(200, ge=1, le=500),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=HOLD_DAYS)
    rows = (await db.execute(_conversion_rows_query(creator_id, status, from_date, to_date).limit(limit))).all()
    return [{
        "id": cv.id, "created_at": cv.created_at, "creator_id": cv.creator_id, "creator_name": cname,
        "job_title": jt, "user_email": email, "payment_id": cv.payment_id,
        "amount_paid": _f(cv.amount_paid), "commission_percent": _f(cv.commission_percent),
        "commission_amount": _f(cv.commission_amount), "status": cv.status, "state": _state(cv, cutoff),
    } for cv, cname, jt, email in rows]


@admin_router.post("/conversions/{conversion_id}/reverse")
async def reverse_conversion(conversion_id: str, admin: Admin = Depends(get_current_admin),
                             db: AsyncSession = Depends(get_db)):
    """Use when a purchase is refunded / is fraudulent. Only works before it has been paid out."""
    cv = await db.get(ReferralConversion, conversion_id)
    if not cv:
        raise HTTPException(status_code=404, detail="Conversion not found")
    if cv.status == "paid":
        raise HTTPException(status_code=409, detail="Already paid out. Adjust it in the creator's next payout.")
    cv.status = "reversed"
    await db.commit()
    return {"success": True, "id": conversion_id, "status": "reversed"}


@admin_router.post("/creators/{creator_id}/payouts", status_code=201)
async def create_payout(creator_id: str, body: PayoutBody, admin: Admin = Depends(get_current_admin),
                        db: AsyncSession = Depends(get_db)):
    """
    Records that you paid this creator. The amount is NOT typed by the admin: it is the sum of
    every commission that is past the hold period and still unpaid, so the books always match.
    """
    creator = await db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")

    cutoff = datetime.utcnow() - timedelta(days=HOLD_DAYS)
    rows = (await db.execute(
        select(ReferralConversion).where(
            ReferralConversion.creator_id == creator_id,
            ReferralConversion.status == "pending",
            ReferralConversion.created_at <= cutoff,
        ).with_for_update()
    )).scalars().all()
    total = sum((Decimal(str(r.commission_amount)) for r in rows), Decimal("0"))
    if not rows or total <= 0:
        raise HTTPException(status_code=400, detail="Nothing is payable yet for this creator.")

    payout_id = generate_uuid()
    db.add(CreatorPayout(id=payout_id, creator_id=creator_id, amount=total,
                         method=(body.method or None), reference=(body.reference or None),
                         note=(body.note or None)))
    for r in rows:
        r.status = "paid"
        r.payout_id = payout_id
    await db.commit()
    return {"success": True, "payout_id": payout_id, "amount": float(total), "conversions": len(rows)}


def _csv_safe(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s   # blocks spreadsheet formula injection


@admin_router.get("/export.csv")
async def export_csv(
    creator_id: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(pending|paid|reversed)$"),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=HOLD_DAYS)
    rows = (await db.execute(_conversion_rows_query(creator_id, status, from_date, to_date))).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date_utc", "creator", "job", "user_email", "amount_paid", "commission_percent",
                "commission_amount", "state", "payment_id"])
    for cv, cname, jt, email in rows:
        w.writerow([cv.created_at.strftime("%Y-%m-%d %H:%M"), _csv_safe(cname), _csv_safe(jt), _csv_safe(email),
                    _f(cv.amount_paid), _f(cv.commission_percent), _f(cv.commission_amount),
                    _state(cv, cutoff), _csv_safe(cv.payment_id)])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="referrals.csv"'})