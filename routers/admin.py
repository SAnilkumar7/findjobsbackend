import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Response, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from ..database import get_db
from ..models import Admin, User, Job, Package, Payment, UserAccess
from ..schemas import JobCreateUpdateRequest, UserLoginRequest
from ..auth import verify_password, create_access_token, get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.post("/login")
async def admin_login(req: UserLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Admin).where(Admin.email == req.email.lower().strip()))
    admin = res.scalars().first()
    if not admin or not verify_password(req.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    token = create_access_token({"id": admin.id, "email": admin.email, "role": "Admin"})
    response.set_cookie(key="admin_token", value=token, httponly=True, secure=True, samesite="none", max_age=604800)

    return {
        "success": True,
        "token": token,
        "admin": {
            "id": admin.id,
            "name": admin.name,
            "email": admin.email,
            "role": admin.role,
        },
    }

@router.get("/stats")
async def get_dashboard_stats(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    u_count = await db.scalar(select(func.count(User.id)))
    j_count = await db.scalar(select(func.count(Job.id)))
    it_count = await db.scalar(select(func.count(Job.id)).where(Job.category_id == "it"))
    non_it_count = await db.scalar(select(func.count(Job.id)).where(Job.category_id == "non-it"))
    banking_count = await db.scalar(select(func.count(Job.id)).where(Job.category_id == "banking"))

    pay_count = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "Successful"))
    total_rev = await db.scalar(select(func.sum(Payment.amount)).where(Payment.status == "Successful")) or 0

    return {
        "total_users": u_count or 0,
        "total_jobs": j_count or 0,
        "jobs_per_category": {
            "it": it_count or 0,
            "non_it": non_it_count or 0,
            "banking": banking_count or 0,
        },
        "total_payments": pay_count or 0,
        "total_revenue": float(total_rev),
    }

@router.get("/jobs")
async def list_admin_jobs(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Job).order_by(Job.created_at.desc()))
    return res.scalars().all()

@router.get("/jobs/{job_id}")
async def get_admin_job(
    job_id: str,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(
    req: JobCreateUpdateRequest,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    slug = req.title.lower().replace(" ", "-")[:50] + f"-{uuid.uuid4().hex[:6]}"
    new_job = Job(
        title=req.title,
        slug=slug,
        company_name=req.company_name,
        category_id=req.category_id,
        location=req.location,
        job_type=req.job_type,
        work_mode=req.work_mode,
        salary=req.salary,
        experience=req.experience,
        education=req.education,
        skills=",".join(req.skills),
        description=req.description,
        eligibility=req.eligibility,
        requirements=req.requirements,
        additional_information=req.additional_information,
        application_url=req.application_url,
        deadline=req.deadline,
        status=req.status,
        created_by=admin.id,
        poster_image=req.poster_image,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return new_job

@router.put("/jobs/{job_id}")
async def update_job(
    job_id: str,
    req: JobCreateUpdateRequest,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.title = req.title
    job.company_name = req.company_name
    job.category_id = req.category_id
    job.location = req.location
    job.job_type = req.job_type
    job.work_mode = req.work_mode
    job.salary = req.salary
    job.experience = req.experience
    job.education = req.education
    job.skills = ",".join(req.skills)
    job.description = req.description
    job.eligibility = req.eligibility
    job.requirements = req.requirements
    job.additional_information = req.additional_information
    job.application_url = req.application_url
    job.deadline = req.deadline
    job.status = req.status
    if req.poster_image:
        job.poster_image = req.poster_image

    await db.commit()
    return job

@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.delete(job)
    await db.commit()
    return {"success": True, "message": "Job deleted"}

@router.get("/users")
async def list_users(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).order_by(User.created_at.desc()))
    users = res.scalars().all()
    out = []
    for u in users:
        acc_res = await db.execute(
            select(Package.name)
            .join(UserAccess, UserAccess.package_id == Package.id)
            .where(UserAccess.user_id == u.id, UserAccess.status == "Active")
        )
        pkgs = acc_res.scalars().all()
        out.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone,
            "signup_date": u.created_at,
            "status": u.status,
            "purchased_packages": pkgs,
        })
    return out

@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: str,
    status_body: dict = Body(...),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    new_status = status_body.get("status")
    if new_status not in ["Active", "Disabled"]:
        raise HTTPException(status_code=400, detail="Status must be Active or Disabled")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = new_status
    await db.commit()
    return {"success": True, "user_id": user.id, "status": user.status}

@router.get("/payments")
async def list_payments(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Payment, User.email, Package.name)
        .outerjoin(User, Payment.user_id == User.id)
        .outerjoin(Package, Payment.package_id == Package.id)
        .order_by(Payment.created_at.desc())
    )
    rows = res.all()
    result = []
    for pay, u_email, pkg_name in rows:
        result.append({
            "id": pay.id,
            "user_id": pay.user_id,
            "email": u_email or "Unknown",
            "package_name": pkg_name or "Custom Package",
            "amount": float(pay.amount),
            "order_id": pay.order_id,
            "payment_id": pay.payment_id,
            "status": pay.status,
            "gateway": pay.gateway,
            "created_at": pay.created_at,
        })
    return result

@router.put("/packages/{pkg_id}")
async def update_package_price(
    pkg_id: str,
    body: dict = Body(...),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    new_price = body.get("price")
    if new_price is None or float(new_price) <= 0:
        raise HTTPException(status_code=400, detail="Invalid price value")

    res = await db.execute(select(Package).where(Package.id == pkg_id))
    pkg = res.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg.price = float(new_price)
    await db.commit()
    return {"success": True, "package_id": pkg.id, "price": float(pkg.price)}