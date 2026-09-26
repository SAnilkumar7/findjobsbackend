from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database import get_db
from ..models import User, Package, UserAccess
from ..auth import get_current_user
from .jobs import check_user_category_access

router = APIRouter(prefix="/api/access", tags=["access"])

@router.get("")
async def get_user_access_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    has_it = await check_user_category_access(current_user.id, "it", db)
    has_non_it = await check_user_category_access(current_user.id, "non-it", db)
    has_banking = await check_user_category_access(current_user.id, "banking", db)

    # Check All access
    all_pkg_res = await db.execute(select(Package).where(Package.slug == "all"))
    all_pkg = all_pkg_res.scalars().first()
    has_all = False
    if all_pkg:
        has_all_res = await db.execute(
            select(UserAccess).where(
                UserAccess.user_id == current_user.id,
                UserAccess.package_id == all_pkg.id,
                UserAccess.status == "Active",
            )
        )
        has_all = bool(has_all_res.scalars().first())

    unlocked = []
    if has_it: unlocked.append("it")
    if has_non_it: unlocked.append("non-it")
    if has_banking: unlocked.append("banking")

    all_packages_res = await db.execute(select(Package))
    all_packages = all_packages_res.scalars().all()

    pkgs_info = []
    for p in all_packages:
        is_active = False
        if p.slug == "all":
            is_active = has_all
        elif p.slug == "it":
            is_active = has_it
        elif p.slug == "non-it":
            is_active = has_non_it
        elif p.slug == "banking":
            is_active = has_banking

        pkgs_info.append({
            "package_id": p.id,
            "slug": p.slug,
            "name": p.name,
            "price": float(p.price),
            "is_active": is_active,
        })

    return {
        "has_it": has_it,
        "has_non_it": has_non_it,
        "has_banking": has_banking,
        "has_all": has_all,
        "unlocked_categories": unlocked,
        "packages": pkgs_info,
    }

@router.get("/{package_slug}")
async def check_specific_package_access(
    package_slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slug = package_slug.lower()
    if slug == "all":
        all_pkg_res = await db.execute(select(Package).where(Package.slug == "all"))
        all_pkg = all_pkg_res.scalars().first()
        has_all = False
        if all_pkg:
            has_all_res = await db.execute(
                select(UserAccess).where(
                    UserAccess.user_id == current_user.id,
                    UserAccess.package_id == all_pkg.id,
                    UserAccess.status == "Active",
                )
            )
            has_all = bool(has_all_res.scalars().first())
        return {"package_slug": "all", "has_access": has_all}

    if slug in ["it", "non-it", "banking"]:
        has_acc = await check_user_category_access(current_user.id, slug, db)
        return {"package_slug": slug, "has_access": has_acc}

    raise HTTPException(status_code=400, detail="Invalid package slug")
