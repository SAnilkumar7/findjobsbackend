from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database import get_db
from ..models import Package
from ..schemas import PackageResponse

router = APIRouter(prefix="/api/packages", tags=["packages"])

@router.get("", response_model=list[PackageResponse])
async def list_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.is_active == True))
    return result.scalars().all()

@router.get("/{package_id}", response_model=PackageResponse)
async def get_package(package_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg
