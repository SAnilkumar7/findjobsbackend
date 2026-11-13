


# import uuid
# import logging
# from datetime import datetime
# from fastapi import APIRouter, Depends, HTTPException, status, Response, Body
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from sqlalchemy import func, delete, text  # CHANGED: added text
# from sqlalchemy.exc import IntegrityError
# from database import get_db
# from models import Admin, User, Job, Package, Payment, UserAccess, OtpVerification
# from schemas import JobCreateUpdateRequest, UserLoginRequest
# from auth import verify_password, create_access_token, get_current_admin

# logger = logging.getLogger(__name__)

# router = APIRouter(prefix="/api/admin", tags=["admin"])

# # ---------------- ADDED: site settings storage ----------------
# DEFAULT_SETTINGS = {
#     "site_name": "FindMyJobs",
#     "site_logo": "",
#     "contact_email": "support@findmyjobs.in",
#     "contact_phone": "",
#     "currency_symbol": "₹",
# }
# PRICE_DEFAULTS = {
#     "price_it": 79,
#     "price_non_it": 69,
#     "price_banking": 59,
#     "price_all": 99,
# }
# # Package slugs that each price is synced with
# PRICE_SLUGS = {
#     "price_it": ["it"],
#     "price_non_it": ["non-it", "non_it", "nonit"],
#     "price_banking": ["banking"],
#     "price_all": ["all", "all-access", "all-access-bundle", "bundle"],
# }

# async def _ensure_settings_table(db: AsyncSession):
#     await db.execute(text(
#         "CREATE TABLE IF NOT EXISTS site_settings (key VARCHAR(100) PRIMARY KEY, value TEXT)"
#     ))
#     await db.commit()

# async def _load_settings(db: AsyncSession) -> dict:
#     await _ensure_settings_table(db)
#     rows = await db.execute(text("SELECT key, value FROM site_settings"))
#     stored = {k: v for k, v in rows.all()}

#     data = dict(DEFAULT_SETTINGS)
#     for k in DEFAULT_SETTINGS:
#         if k in stored and stored[k] is not None:
#             data[k] = stored[k]

#     for k, default in PRICE_DEFAULTS.items():
#         try:
#             data[k] = float(stored[k]) if k in stored else default
#         except (TypeError, ValueError):
#             data[k] = default

#     # Real package prices win when a package matches
#     pkgs = (await db.execute(select(Package))).scalars().all()
#     for pkg in pkgs:
#         slug = getattr(pkg, "slug", None)
#         for price_key, slugs in PRICE_SLUGS.items():
#             if slug in slugs and pkg.price is not None:
#                 data[price_key] = float(pkg.price)
#     return data
# # --------------------------------------------------------------

# @router.post("/login")
# async def admin_login(req: UserLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
#     res = await db.execute(select(Admin).where(Admin.email == req.email.lower().strip()))
#     admin = res.scalars().first()
#     if not admin or not verify_password(req.password, admin.password_hash):
#         raise HTTPException(status_code=401, detail="Invalid admin credentials")

#     token = create_access_token({"id": admin.id, "email": admin.email, "role": "Admin"})
#     response.set_cookie(key="admin_token", value=token, httponly=True, secure=True, samesite="none", max_age=604800)

#     return {
#         "success": True,
#         "token": token,
#         "admin": {
#             "id": admin.id,
#             "name": admin.name,
#             "email": admin.email,
#             "role": admin.role,
#         },
#     }

# # CHANGED: now returns the full saved settings (admin-only)
# @router.get("/settings")
# async def get_admin_settings(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
#     return await _load_settings(db)

# # ADDED: saves the settings page (admin-only)
# @router.put("/settings")
# async def update_admin_settings(
#     body: dict = Body(...),
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     site_name = str(body.get("site_name", "")).strip()
#     contact_email = str(body.get("contact_email", "")).strip()
#     if not site_name:
#         raise HTTPException(status_code=400, detail="Site name is required")
#     if not contact_email or "@" not in contact_email:
#         raise HTTPException(status_code=400, detail="A valid contact email is required")

#     prices = {}
#     for key in PRICE_DEFAULTS:
#         try:
#             value = float(body.get(key))
#         except (TypeError, ValueError):
#             raise HTTPException(status_code=400, detail=f"Invalid value for {key}")
#         if value <= 0:
#             raise HTTPException(status_code=400, detail=f"{key} must be greater than 0")
#         prices[key] = value

#     to_store = {
#         "site_name": site_name,
#         "site_logo": str(body.get("site_logo", "") or "").strip(),
#         "contact_email": contact_email,
#         "contact_phone": str(body.get("contact_phone", "") or "").strip(),
#         "currency_symbol": str(body.get("currency_symbol", "") or "₹").strip() or "₹",
#     }
#     to_store.update({k: str(v) for k, v in prices.items()})

#     await _ensure_settings_table(db)
#     for k, v in to_store.items():
#         await db.execute(
#             text(
#                 "INSERT INTO site_settings (key, value) VALUES (:k, :v) "
#                 "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
#             ),
#             {"k": k, "v": v},
#         )

#     # Keep real package prices in sync with the four prices
#     pkgs = (await db.execute(select(Package))).scalars().all()
#     for pkg in pkgs:
#         slug = getattr(pkg, "slug", None)
#         for price_key, slugs in PRICE_SLUGS.items():
#             if slug in slugs:
#                 pkg.price = prices[price_key]

#     await db.commit()
#     return await _load_settings(db)

# @router.get("/stats")
# async def get_dashboard_stats(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
#     u_count = await db.scalar(select(func.count(User.id)))
#     j_count = await db.scalar(select(func.count(Job.id)))

#     # One grouped query instead of three separate count queries
#     cat_rows = await db.execute(
#         select(Job.category_id, func.count(Job.id)).group_by(Job.category_id)
#     )
#     counts = dict(cat_rows.all())
#     it_count = counts.get("it", 0)
#     non_it_count = counts.get("non-it", 0)
#     banking_count = counts.get("banking", 0)

#     pay_count = await db.scalar(select(func.count(Payment.id)).where(Payment.status == "Successful"))
#     total_rev = await db.scalar(select(func.sum(Payment.amount)).where(Payment.status == "Successful")) or 0

#     return {
#         "total_users": u_count or 0,
#         "total_jobs": j_count or 0,
#         "jobs_per_category": {
#             "it": it_count or 0,
#             "non_it": non_it_count or 0,
#             "banking": banking_count or 0,
#         },
#         "total_payments": pay_count or 0,
#         "total_revenue": float(total_rev),
#     }

# @router.get("/jobs")
# async def list_admin_jobs(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
#     res = await db.execute(select(Job).order_by(Job.created_at.desc()))
#     return res.scalars().all()

# @router.get("/jobs/{job_id}")
# async def get_admin_job(
#     job_id: str,
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     res = await db.execute(select(Job).where(Job.id == job_id))
#     job = res.scalars().first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")
#     return job

# @router.post("/jobs", status_code=status.HTTP_201_CREATED)
# async def create_job(
#     req: JobCreateUpdateRequest,
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     slug = req.title.lower().replace(" ", "-")[:50] + f"-{uuid.uuid4().hex[:6]}"
#     new_job = Job(
#         title=req.title,
#         slug=slug,
#         company_name=req.company_name,
#         category_id=req.category_id,
#         location=req.location,
#         job_type=req.job_type,
#         work_mode=req.work_mode,
#         salary=req.salary,
#         experience=req.experience,
#         education=req.education,
#         skills=",".join(req.skills),
#         description=req.description,
#         eligibility=req.eligibility,
#         requirements=req.requirements,
#         additional_information=req.additional_information,
#         apply_method=req.apply_method,
#         application_url=req.application_url,
#         application_phone=req.application_phone,
#         deadline=req.deadline,
#         status=req.status,
#         created_by=admin.id,
#         poster_image=req.poster_image,
#         rating=req.rating,  # ADDED (stars)
#     )
#     db.add(new_job)
#     await db.commit()
#     await db.refresh(new_job)
#     return new_job

# @router.put("/jobs/{job_id}")
# async def update_job(
#     job_id: str,
#     req: JobCreateUpdateRequest,
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     res = await db.execute(select(Job).where(Job.id == job_id))
#     job = res.scalars().first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     job.title = req.title
#     job.company_name = req.company_name
#     job.category_id = req.category_id
#     job.location = req.location
#     job.job_type = req.job_type
#     job.work_mode = req.work_mode
#     job.salary = req.salary
#     job.experience = req.experience
#     job.education = req.education
#     job.skills = ",".join(req.skills)
#     job.description = req.description
#     job.eligibility = req.eligibility
#     job.requirements = req.requirements
#     job.additional_information = req.additional_information
#     job.apply_method = req.apply_method
#     job.application_url = req.application_url
#     job.application_phone = req.application_phone
#     job.deadline = req.deadline
#     job.status = req.status
#     job.rating = req.rating  # ADDED (stars)
#     if req.poster_image:
#         job.poster_image = req.poster_image

#     await db.commit()
#     return job

# @router.delete("/jobs/{job_id}")
# async def delete_job(
#     job_id: str,
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     res = await db.execute(select(Job).where(Job.id == job_id))
#     job = res.scalars().first()
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")
#     await db.delete(job)
#     await db.commit()
#     return {"success": True, "message": "Job deleted"}

# @router.get("/users")
# async def list_users(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
#     res = await db.execute(select(User).order_by(User.created_at.desc()))
#     users = res.scalars().all()

#     # One query for all users' active packages instead of one query per user
#     acc_res = await db.execute(
#         select(UserAccess.user_id, Package.name)
#         .join(Package, UserAccess.package_id == Package.id)
#         .where(UserAccess.status == "Active")
#     )
#     pkgs_by_user: dict = {}
#     for uid, name in acc_res.all():
#         pkgs_by_user.setdefault(uid, []).append(name)

#     out = []
#     for u in users:
#         out.append({
#             "id": u.id,
#             "name": u.name,
#             "email": u.email,
#             "phone": u.phone,
#             "signup_date": u.created_at,
#             "status": u.status,
#             "purchased_packages": pkgs_by_user.get(u.id, []),
#         })
#     return out

# @router.patch("/users/{user_id}/status")
# async def toggle_user_status(
#     user_id: str,
#     status_body: dict = Body(...),
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     new_status = status_body.get("status")
#     if new_status not in ["Active", "Disabled"]:
#         raise HTTPException(status_code=400, detail="Status must be Active or Disabled")

#     res = await db.execute(select(User).where(User.id == user_id))
#     user = res.scalars().first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")
#     user.status = new_status
#     await db.commit()
#     return {"success": True, "user_id": user.id, "status": user.status}

# @router.delete("/users/{user_id}")
# async def delete_user_permanently(
#     user_id: str,
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     res = await db.execute(select(User).where(User.id == user_id))
#     user = res.scalars().first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     try:
#         # 1. Delete rows from EVERY table that has a foreign key pointing to users
#         #    (payments, package access, and any other table linked to the user)
#         users_table = User.__table__
#         for table in reversed(User.metadata.sorted_tables):
#             if table is users_table:
#                 continue
#             for fk in table.foreign_keys:
#                 if fk.column.table is users_table:
#                     await db.execute(
#                         delete(table).where(fk.parent == user.id)
#                     )

#         # 2. Remove any OTP records for this email
#         await db.execute(
#             delete(OtpVerification).where(OtpVerification.email == user.email.lower())
#         )

#         # 3. Delete the user
#         await db.delete(user)
#         await db.commit()
#     except IntegrityError as e:
#         await db.rollback()
#         logger.exception("Failed to delete user %s: %s", user_id, e)
#         raise HTTPException(
#             status_code=409,
#             detail="User could not be deleted because other records still depend on it. Check the server logs.",
#         )

#     return {"success": True, "message": "User deleted permanently", "user_id": user_id}

# @router.get("/payments")
# async def list_payments(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
#     res = await db.execute(
#         select(Payment, User.email, Package.name)
#         .outerjoin(User, Payment.user_id == User.id)
#         .outerjoin(Package, Payment.package_id == Package.id)
#         .order_by(Payment.created_at.desc())
#     )
#     rows = res.all()
#     result = []
#     for pay, u_email, pkg_name in rows:
#         result.append({
#             "id": pay.id,
#             "user_id": pay.user_id,
#             "email": u_email or "Unknown",
#             "package_name": pkg_name or "Custom Package",
#             "amount": float(pay.amount),
#             "order_id": pay.order_id,
#             "payment_id": pay.payment_id,
#             "status": pay.status,
#             "gateway": pay.gateway,
#             "created_at": pay.created_at,
#         })
#     return result

# @router.put("/packages/{pkg_id}")
# async def update_package_price(
#     pkg_id: str,
#     body: dict = Body(...),
#     admin: Admin = Depends(get_current_admin),
#     db: AsyncSession = Depends(get_db),
# ):
#     new_price = body.get("price")
#     # CHANGED: text or bad values now return 400 instead of crashing with 500
#     try:
#         price_value = float(new_price)
#     except (TypeError, ValueError):
#         raise HTTPException(status_code=400, detail="Invalid price value")
#     if price_value <= 0:
#         raise HTTPException(status_code=400, detail="Invalid price value")

#     res = await db.execute(select(Package).where(Package.id == pkg_id))
#     pkg = res.scalars().first()
#     if not pkg:
#         raise HTTPException(status_code=404, detail="Package not found")
#     pkg.price = price_value
#     await db.commit()
#     return {"success": True, "package_id": pkg.id, "price": float(pkg.price)}





















import uuid
import asyncio  # ADDED (scaling)
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Response, Body, Request  # ADDED (scaling): Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, delete, text  # CHANGED: added text
from sqlalchemy.exc import IntegrityError
from database import get_db
from models import Admin, User, Job, Package, Payment, UserAccess, OtpVerification
from schemas import JobCreateUpdateRequest, UserLoginRequest
from auth import (  # ADDED (scaling): limiter, plus password helpers for the admin password feature
    verify_password,
    create_access_token,
    get_current_admin,
    limiter,
    get_password_hash,
    validate_password_strength,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------------- ADDED: site settings storage ----------------
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
# Package slugs that each price is synced with
PRICE_SLUGS = {
    "price_it": ["it"],
    "price_non_it": ["non-it", "non_it", "nonit"],
    "price_banking": ["banking"],
    "price_all": ["all", "all-access", "all-access-bundle", "bundle"],
}

async def _ensure_settings_table(db: AsyncSession):
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS site_settings (key VARCHAR(100) PRIMARY KEY, value TEXT)"
    ))
    await db.commit()

async def _load_settings(db: AsyncSession) -> dict:
    await _ensure_settings_table(db)
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

    # Real package prices win when a package matches
    pkgs = (await db.execute(select(Package))).scalars().all()
    for pkg in pkgs:
        slug = getattr(pkg, "slug", None)
        for price_key, slugs in PRICE_SLUGS.items():
            if slug in slugs and pkg.price is not None:
                data[price_key] = float(pkg.price)
    return data
# --------------------------------------------------------------

@router.post("/login")
@limiter.limit("5/minute")  # ADDED (scaling)
async def admin_login(request: Request, req: UserLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):  # ADDED (scaling): request param
    res = await db.execute(select(Admin).where(Admin.email == req.email.lower().strip()))
    admin = res.scalars().first()
    # ADDED (scaling): bcrypt runs in a thread so it does not freeze other requests
    password_ok = False
    if admin:
        password_ok = await asyncio.to_thread(verify_password, req.password, admin.password_hash)
    if not admin or not password_ok:
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

# ---------------- ADDED (admin password feature): admins are created and managed only by a logged-in admin ----------------
@router.get("/admins")
async def list_admins(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Admin))
    return [
        {"id": a.id, "name": a.name, "email": a.email, "role": a.role, "status": a.status}
        for a in res.scalars().all()
    ]

@router.post("/admins", status_code=status.HTTP_201_CREATED)
async def create_admin(
    body: dict = Body(...),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    name = str(body.get("name", "")).strip()
    email = str(body.get("email", "")).lower().strip()
    password = str(body.get("password", ""))

    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    validate_password_strength(password, email)  # same strong-password rule as users

    existing = await db.execute(select(Admin).where(Admin.email == email))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="An admin with this email already exists")

    new_admin = Admin(
        name=name,
        email=email,
        password_hash=await asyncio.to_thread(get_password_hash, password),
        role="Admin",
        status="Active",
    )
    db.add(new_admin)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An admin with this email already exists")
    await db.refresh(new_admin)
    return {"success": True, "admin": {"id": new_admin.id, "name": new_admin.name, "email": new_admin.email, "role": new_admin.role}}

@router.put("/change-password")
@limiter.limit("5/minute")
async def change_own_password(
    request: Request,
    body: dict = Body(...),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    current_password = str(body.get("current_password", ""))
    new_password = str(body.get("new_password", ""))

    ok = await asyncio.to_thread(verify_password, current_password, admin.password_hash)
    if not ok:
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    validate_password_strength(new_password, admin.email)

    admin.password_hash = await asyncio.to_thread(get_password_hash, new_password)
    await db.commit()
    return {"success": True, "message": "Password changed successfully"}

@router.put("/admins/{admin_id}/password")
async def reset_admin_password(
    admin_id: str,
    body: dict = Body(...),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    new_password = str(body.get("new_password", ""))

    res = await db.execute(select(Admin).where(Admin.id == admin_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found")
    validate_password_strength(new_password, target.email)

    target.password_hash = await asyncio.to_thread(get_password_hash, new_password)
    await db.commit()
    return {"success": True, "message": "Password updated", "admin_id": target.id}
# --------------------------------------------------------------------------------------------------------------------------

# CHANGED: now returns the full saved settings (admin-only)
@router.get("/settings")
async def get_admin_settings(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    return await _load_settings(db)

# ADDED: saves the settings page (admin-only)
@router.put("/settings")
async def update_admin_settings(
    body: dict = Body(...),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    site_name = str(body.get("site_name", "")).strip()
    contact_email = str(body.get("contact_email", "")).strip()
    if not site_name:
        raise HTTPException(status_code=400, detail="Site name is required")
    if not contact_email or "@" not in contact_email:
        raise HTTPException(status_code=400, detail="A valid contact email is required")

    prices = {}
    for key in PRICE_DEFAULTS:
        try:
            value = float(body.get(key))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}")
        if value <= 0:
            raise HTTPException(status_code=400, detail=f"{key} must be greater than 0")
        prices[key] = value

    to_store = {
        "site_name": site_name,
        "site_logo": str(body.get("site_logo", "") or "").strip(),
        "contact_email": contact_email,
        "contact_phone": str(body.get("contact_phone", "") or "").strip(),
        "currency_symbol": str(body.get("currency_symbol", "") or "₹").strip() or "₹",
    }
    to_store.update({k: str(v) for k, v in prices.items()})

    await _ensure_settings_table(db)
    for k, v in to_store.items():
        await db.execute(
            text(
                "INSERT INTO site_settings (key, value) VALUES (:k, :v) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            ),
            {"k": k, "v": v},
        )

    # Keep real package prices in sync with the four prices
    pkgs = (await db.execute(select(Package))).scalars().all()
    for pkg in pkgs:
        slug = getattr(pkg, "slug", None)
        for price_key, slugs in PRICE_SLUGS.items():
            if slug in slugs:
                pkg.price = prices[price_key]

    await db.commit()
    return await _load_settings(db)

@router.get("/stats")
async def get_dashboard_stats(admin: Admin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    u_count = await db.scalar(select(func.count(User.id)))
    j_count = await db.scalar(select(func.count(Job.id)))

    # One grouped query instead of three separate count queries
    cat_rows = await db.execute(
        select(Job.category_id, func.count(Job.id)).group_by(Job.category_id)
    )
    counts = dict(cat_rows.all())
    it_count = counts.get("it", 0)
    non_it_count = counts.get("non-it", 0)
    banking_count = counts.get("banking", 0)

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
        apply_method=req.apply_method,
        application_url=req.application_url,
        application_phone=req.application_phone,
        deadline=req.deadline,
        status=req.status,
        created_by=admin.id,
        poster_image=req.poster_image,
        rating=req.rating,  # ADDED (stars)
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
    job.apply_method = req.apply_method
    job.application_url = req.application_url
    job.application_phone = req.application_phone
    job.deadline = req.deadline
    job.status = req.status
    job.rating = req.rating  # ADDED (stars)
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

    # One query for all users' active packages instead of one query per user
    acc_res = await db.execute(
        select(UserAccess.user_id, Package.name)
        .join(Package, UserAccess.package_id == Package.id)
        .where(UserAccess.status == "Active")
    )
    pkgs_by_user: dict = {}
    for uid, name in acc_res.all():
        pkgs_by_user.setdefault(uid, []).append(name)

    out = []
    for u in users:
        out.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "phone": u.phone,
            "signup_date": u.created_at,
            "status": u.status,
            "purchased_packages": pkgs_by_user.get(u.id, []),
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

@router.delete("/users/{user_id}")
async def delete_user_permanently(
    user_id: str,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # 1. Delete rows from EVERY table that has a foreign key pointing to users
        #    (payments, package access, and any other table linked to the user)
        users_table = User.__table__
        for table in reversed(User.metadata.sorted_tables):
            if table is users_table:
                continue
            for fk in table.foreign_keys:
                if fk.column.table is users_table:
                    await db.execute(
                        delete(table).where(fk.parent == user.id)
                    )

        # 2. Remove any OTP records for this email
        await db.execute(
            delete(OtpVerification).where(OtpVerification.email == user.email.lower())
        )

        # 3. Delete the user
        await db.delete(user)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logger.exception("Failed to delete user %s: %s", user_id, e)
        raise HTTPException(
            status_code=409,
            detail="User could not be deleted because other records still depend on it. Check the server logs.",
        )

    return {"success": True, "message": "User deleted permanently", "user_id": user_id}

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
    # CHANGED: text or bad values now return 400 instead of crashing with 500
    try:
        price_value = float(new_price)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid price value")
    if price_value <= 0:
        raise HTTPException(status_code=400, detail="Invalid price value")

    res = await db.execute(select(Package).where(Package.id == pkg_id))
    pkg = res.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg.price = price_value
    await db.commit()
    return {"success": True, "package_id": pkg.id, "price": float(pkg.price)}