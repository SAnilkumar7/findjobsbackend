# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from database import get_db
# from models import Package
# from schemas import PackageResponse

# router = APIRouter(prefix="/api/packages", tags=["packages"])

# @router.get("", response_model=list[PackageResponse])
# async def list_packages(db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(Package).where(Package.is_active == True))
#     return result.scalars().all()

# @router.get("/{package_id}", response_model=PackageResponse)
# async def get_package(package_id: str, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(Package).where(Package.id == package_id))
#     pkg = result.scalars().first()
#     if not pkg:
#         raise HTTPException(status_code=404, detail="Package not found")
#     return pkg











# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from database import get_db
# from models import Package
# from schemas import PackageResponse

# router = APIRouter(prefix="/api/packages", tags=["packages"])

# @router.get("", response_model=list[PackageResponse])
# async def list_packages(db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(Package).where(Package.is_active == True))
#     return result.scalars().all()

# # ADDED: public site settings (no login needed). Must stay ABOVE "/{package_id}"
# @router.get("/settings")
# async def get_public_settings():
#     return {
#         "support_email": "support@findmyjobs.in",
#     }

# @router.get("/{package_id}", response_model=PackageResponse)
# async def get_package(package_id: str, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(Package).where(Package.id == package_id))
#     pkg = result.scalars().first()
#     if not pkg:
#         raise HTTPException(status_code=404, detail="Package not found")
#     return pkg


















from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text  # ADDED
from database import get_db
from models import Package
from schemas import PackageResponse

router = APIRouter(prefix="/api/packages", tags=["packages"])

# ---------------- ADDED: public read of the saved site settings ----------------
DEFAULT_SETTINGS = {
    "site_name": "FindMyJobs",
    "site_logo": "",
    "contact_email": "support@findmyjobs.in",
    "contact_phone": "",
    "currency_symbol": "₹",
}
PRICE_DEFAULTS = {
    "price_it": 79,
    "price_non_it": 69,
    "price_banking": 59,
    "price_all": 99,
}
PRICE_SLUGS = {
    "price_it": ["it"],
    "price_non_it": ["non-it", "non_it", "nonit"],
    "price_banking": ["banking"],
    "price_all": ["all", "all-access", "all-access-bundle", "bundle"],
}

async def _load_public_settings(db: AsyncSession) -> dict:
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS site_settings (key VARCHAR(100) PRIMARY KEY, value TEXT)"
    ))
    await db.commit()
    rows = await db.execute(text("SELECT key, value FROM site_settings"))
    stored = {k: v for k, v in rows.all()}

    data = dict(DEFAULT_SETTINGS)
    for k in DEFAULT_SETTINGS:
        if k in stored and stored[k] is not None:
            data[k] = stored[k]

    for k, default in PRICE_DEFAULTS.items():
        try:
            data[k] = float(stored[k]) if k in stored else default
        except (TypeError, ValueError):
            data[k] = default

    pkgs = (await db.execute(select(Package))).scalars().all()
    for pkg in pkgs:
        slug = getattr(pkg, "slug", None)
        for price_key, slugs in PRICE_SLUGS.items():
            if slug in slugs and pkg.price is not None:
                data[price_key] = float(pkg.price)
    return data
# -------------------------------------------------------------------------------

@router.get("", response_model=list[PackageResponse])
async def list_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.is_active == True))
    return result.scalars().all()

# CHANGED: public site settings (no login needed). Must stay ABOVE "/{package_id}"
@router.get("/settings")
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    return await _load_public_settings(db)

@router.get("/{package_id}", response_model=PackageResponse)
async def get_package(package_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg