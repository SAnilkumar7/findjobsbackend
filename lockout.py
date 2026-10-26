"""
Persistent brute-force protection.

5 wrong attempts  ->  locked for 30 minutes  ->  then a fresh 5 attempts.

Stored in the database (table auth_attempts), so it works across restarts and
multiple Render workers. Unknown emails are tracked exactly like real ones, so
the response never reveals whether an account exists.
"""
import math
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import AuthAttempt, generate_uuid

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 30


def _locked_error(locked_until: datetime) -> HTTPException:
    seconds = max(1, int((locked_until - datetime.utcnow()).total_seconds()))
    minutes = math.ceil(seconds / 60)
    return HTTPException(
        status_code=429,
        detail=f"Too many failed attempts. Please try again in {minutes} minute(s).",
        headers={"Retry-After": str(seconds)},
    )


async def _get_row(db: AsyncSession, scope: str, key: str, for_update: bool = False):
    query = select(AuthAttempt).where(
        AuthAttempt.scope == scope, AuthAttempt.identifier == key
    )
    if for_update:
        query = query.with_for_update()  # row lock, so parallel requests can't skip the count
    res = await db.execute(query)
    return res.scalars().first()


async def ensure_not_locked(db: AsyncSession, scope: str, key: str) -> None:
    """Call BEFORE checking the password / code. Raises HTTP 429 while locked."""
    row = await _get_row(db, scope, key)
    if row and row.locked_until and row.locked_until > datetime.utcnow():
        raise _locked_error(row.locked_until)


async def register_failure(db: AsyncSession, scope: str, key: str) -> int:
    """
    Record one failed attempt and return how many attempts are left.
    Raises HTTP 429 immediately if this failure triggers (or hits) the lock.
    Always commits, so the failure is saved even though the caller then raises.
    """
    now = datetime.utcnow()
    row = await _get_row(db, scope, key, for_update=True)

    if row is None:
        # Opportunistic cleanup of stale rows (last failure more than a day ago)
        await db.execute(
            delete(AuthAttempt).where(AuthAttempt.last_failed_at < now - timedelta(days=1))
        )
        row = AuthAttempt(
            id=generate_uuid(), scope=scope, identifier=key,
            failed_count=0, last_failed_at=now,
        )
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            # Another request created the same row at the same moment
            await db.rollback()
            row = await _get_row(db, scope, key, for_update=True)
            if row is None:
                raise HTTPException(status_code=503, detail="Please try again.")

    # Already locked: report it (read the value BEFORE commit)
    if row.locked_until and row.locked_until > now:
        current_lock = row.locked_until
        await db.commit()
        raise _locked_error(current_lock)

    # Previous lock expired, or the last failure was long ago: start counting fresh
    if row.locked_until and row.locked_until <= now:
        row.failed_count = 0
        row.locked_until = None
    elif row.last_failed_at and now - row.last_failed_at > timedelta(minutes=LOCK_MINUTES):
        row.failed_count = 0

    row.failed_count += 1
    row.last_failed_at = now

    if row.failed_count >= MAX_FAILED_ATTEMPTS:
        locked_until = now + timedelta(minutes=LOCK_MINUTES)
        row.locked_until = locked_until
        await db.commit()
        raise _locked_error(locked_until)

    remaining = MAX_FAILED_ATTEMPTS - row.failed_count
    await db.commit()
    return remaining


async def clear_failures(db: AsyncSession, scope: str, key: str) -> bool:
    """
    Call after a SUCCESSFUL login / verification.
    Returns True if it committed (so callers know loaded objects may be expired).
    """
    row = await _get_row(db, scope, key)
    if row:
        await db.execute(
            delete(AuthAttempt).where(
                AuthAttempt.scope == scope, AuthAttempt.identifier == key
            )
        )
        await db.commit()
        return True
    return False