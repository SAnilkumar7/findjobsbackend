# """
# FastAPI Jobs Router
# Enforces strict backend-authoritative access validation:
# - Checks whether user has unlocked the specific category (IT, Non-IT, Banking) or All Access.
# - Rejects with 403 ACCESS_REQUIRED if not subscribed.
# """

# from typing import List, Optional
# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from database import get_db
# from models import User, Job, Package, UserAccess
# from auth import get_current_user

# router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# async def check_user_category_access(user_id: str, category: str, db: AsyncSession) -> bool:
#     """
#     Checks if user has active access to the given category slug or All Access pass.
#     """
#     # 1. Check if user has active pkg_all access
#     all_pkg_res = await db.execute(select(Package).where(Package.slug == "all"))
#     all_pkg = all_pkg_res.scalars().first()
#     if all_pkg:
#         has_all_res = await db.execute(
#             select(UserAccess).where(
#                 UserAccess.user_id == user_id,
#                 UserAccess.package_id == all_pkg.id,
#                 UserAccess.status == "Active",
#             )
#         )
#         if has_all_res.scalars().first():
#             return True

#     # 2. Check category-specific package
#     cat_pkg_res = await db.execute(select(Package).where(Package.slug == category))
#     cat_pkg = cat_pkg_res.scalars().first()
#     if not cat_pkg:
#         return False

#     has_cat_res = await db.execute(
#         select(UserAccess).where(
#             UserAccess.user_id == user_id,
#             UserAccess.package_id == cat_pkg.id,
#             UserAccess.status == "Active",
#         )
#     )
#     return bool(has_cat_res.scalars().first())

# @router.get("")
# async def get_all_jobs(
#     current_user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Returns jobs filtered to only categories the user has unlocked.
#     If no categories unlocked, returns 403 ACCESS_REQUIRED.
#     """
#     has_it = await check_user_category_access(current_user.id, "it", db)
#     has_non_it = await check_user_category_access(current_user.id, "non-it", db)
#     has_banking = await check_user_category_access(current_user.id, "banking", db)

#     if not has_it and not has_non_it and not has_banking:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="ACCESS_REQUIRED",
#         )

#     categories_allowed = []
#     if has_it:
#         categories_allowed.append("it")
#     if has_non_it:
#         categories_allowed.append("non-it")
#     if has_banking:
#         categories_allowed.append("banking")

#     result = await db.execute(
#         select(Job).where(
#             Job.category_id.in_(categories_allowed),
#             Job.status == "Published",
#         ).order_by(Job.created_at.desc())
#     )
#     return result.scalars().all()

# @router.get("/category/{category}")
# async def get_jobs_by_category(
#     category: str,
#     current_user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     category = category.lower()
#     if category not in ["it", "non-it", "banking"]:
#         raise HTTPException(status_code=400, detail="Invalid job category")

#     has_access = await check_user_category_access(current_user.id, category, db)
#     if not has_access:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="ACCESS_REQUIRED",
#         )

#     result = await db.execute(
#         select(Job).where(
#             Job.category_id == category,
#             Job.status == "Published",
#         ).order_by(Job.created_at.desc())
#     )
#     return result.scalars().all()

# @router.get("/{job_id}")
# async def get_job_detail(
#     job_id: str,
#     current_user: User = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(select(Job).where(Job.id == job_id))
#     job = result.scalars().first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     has_access = await check_user_category_access(current_user.id, job.category_id, db)
#     if not has_access:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="ACCESS_REQUIRED",
#         )

#     return job











"""
FastAPI Jobs Router
Enforces strict backend-authoritative access validation:
- Checks whether user has unlocked the specific category (IT, Non-IT, Banking) or All Access.
- Rejects with 403 ACCESS_REQUIRED if not subscribed.
- Jobs whose deadline has passed are hidden (and deleted hourly by the cleanup task in main.py).
"""

from typing import List, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db, today_ist
from models import User, Job, Package, UserAccess
from auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

async def get_user_active_slugs(user_id: str, db: AsyncSession) -> Set[str]:
    """
    Returns the slugs (it, non-it, banking, all) of every package the user has ACTIVE access to.
    One single query instead of several (much faster on a cloud database).
    """
    res = await db.execute(
        select(Package.slug)
        .join(UserAccess, UserAccess.package_id == Package.id)
        .where(
            UserAccess.user_id == user_id,
            UserAccess.status == "Active",
        )
    )
    return set(res.scalars().all())

async def check_user_category_access(user_id: str, category: str, db: AsyncSession) -> bool:
    """
    Checks if user has active access to the given category slug or All Access pass.
    (Same behaviour as before: "all" unlocks every category.)
    """
    slugs = await get_user_active_slugs(user_id, db)
    return "all" in slugs or category in slugs

@router.get("")
async def get_all_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns jobs filtered to only categories the user has unlocked.
    If no categories unlocked, returns 403 ACCESS_REQUIRED.
    """
    slugs = await get_user_active_slugs(current_user.id, db)
    has_all = "all" in slugs
    has_it = has_all or "it" in slugs
    has_non_it = has_all or "non-it" in slugs
    has_banking = has_all or "banking" in slugs

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
            Job.deadline >= today_ist(),
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

    # "All Jobs" tab: same result as GET /api/jobs (every category the user unlocked)
    if category == "all":
        return await get_all_jobs(current_user=current_user, db=db)

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
            Job.deadline >= today_ist(),
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

    # Expired jobs are treated as gone
    if job.deadline < today_ist():
        raise HTTPException(status_code=404, detail="Job not found")

    has_access = await check_user_category_access(current_user.id, job.category_id, db)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_REQUIRED",
        )

    return job