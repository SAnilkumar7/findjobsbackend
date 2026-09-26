"""
FastAPI Jobs Router
Enforces strict backend-authoritative access validation:
- Checks whether user has unlocked the specific category (IT, Non-IT, Banking) or All Access.
- Rejects with 403 ACCESS_REQUIRED if not subscribed.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database import get_db
from ..models import User, Job, Package, UserAccess
from ..auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

async def check_user_category_access(user_id: str, category: str, db: AsyncSession) -> bool:
    """
    Checks if user has active access to the given category slug or All Access pass.
    """
    # 1. Check if user has active pkg_all access
    all_pkg_res = await db.execute(select(Package).where(Package.slug == "all"))
    all_pkg = all_pkg_res.scalars().first()
    if all_pkg:
        has_all_res = await db.execute(
            select(UserAccess).where(
                UserAccess.user_id == user_id,
                UserAccess.package_id == all_pkg.id,
                UserAccess.status == "Active",
            )
        )
        if has_all_res.scalars().first():
            return True

    # 2. Check category-specific package
    cat_pkg_res = await db.execute(select(Package).where(Package.slug == category))
    cat_pkg = cat_pkg_res.scalars().first()
    if not cat_pkg:
        return False

    has_cat_res = await db.execute(
        select(UserAccess).where(
            UserAccess.user_id == user_id,
            UserAccess.package_id == cat_pkg.id,
            UserAccess.status == "Active",
        )
    )
    return bool(has_cat_res.scalars().first())

@router.get("")
async def get_all_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns jobs filtered to only categories the user has unlocked.
    If no categories unlocked, returns 403 ACCESS_REQUIRED.
    """
    has_it = await check_user_category_access(current_user.id, "it", db)
    has_non_it = await check_user_category_access(current_user.id, "non-it", db)
    has_banking = await check_user_category_access(current_user.id, "banking", db)

    if not has_it and not has_non_it and not has_banking:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_REQUIRED",
        )

    categories_allowed = []
    if has_it:
        categories_allowed.append("it")
    if has_non_it:
        categories_allowed.append("non-it")
    if has_banking:
        categories_allowed.append("banking")

    result = await db.execute(
        select(Job).where(
            Job.category_id.in_(categories_allowed),
            Job.status == "Published",
        ).order_by(Job.created_at.desc())
    )
    return result.scalars().all()

@router.get("/category/{category}")
async def get_jobs_by_category(
    category: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    category = category.lower()
    if category not in ["it", "non-it", "banking"]:
        raise HTTPException(status_code=400, detail="Invalid job category")

    has_access = await check_user_category_access(current_user.id, category, db)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_REQUIRED",
        )

    result = await db.execute(
        select(Job).where(
            Job.category_id == category,
            Job.status == "Published",
        ).order_by(Job.created_at.desc())
    )
    return result.scalars().all()

@router.get("/{job_id}")
async def get_job_detail(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    has_access = await check_user_category_access(current_user.id, job.category_id, db)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_REQUIRED",
        )

    return job
