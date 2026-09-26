# from fastapi import APIRouter, Depends, HTTPException, status, Response
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from ..database import get_db
# from ..models import User
# from ..schemas import UserRegisterRequest, UserLoginRequest, GoogleAuthRequest, UserResponse
# from ..auth import get_password_hash, verify_password, create_access_token, get_current_user

# router = APIRouter(prefix="/api/auth", tags=["auth"])

# @router.post("/register", status_code=status.HTTP_201_CREATED)
# async def register(req: UserRegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
#     existing_res = await db.execute(select(User).where(User.email == req.email.lower()))
#     if existing_res.scalars().first():
#         raise HTTPException(status_code=409, detail="An account with this email already exists")

#     new_user = User(
#         name=req.name.strip(),
#         email=req.email.lower().strip(),
#         password_hash=get_password_hash(req.password),
#         phone=req.phone,
#         age=req.age,
#         location=req.location,
#     )
#     db.add(new_user)
#     await db.commit()
#     await db.refresh(new_user)

#     token = create_access_token({"id": new_user.id, "email": new_user.email})
#     response.set_cookie(key="token", value=token, httponly=True, secure=True, samesite="none", max_age=604800)

#     return {"success": True, "token": token, "user": UserResponse.from_orm(new_user)}

# @router.post("/login")
# async def login(req: UserLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
#     res = await db.execute(select(User).where(User.email == req.email.lower().strip()))
#     user = res.scalars().first()
#     if not user or not verify_password(req.password, user.password_hash):
#         raise HTTPException(status_code=401, detail="Invalid email or password")

#     if user.status == "Disabled":
#         raise HTTPException(status_code=403, detail="Account is disabled")

#     token = create_access_token({"id": user.id, "email": user.email})
#     response.set_cookie(key="token", value=token, httponly=True, secure=True, samesite="none", max_age=604800)

#     return {"success": True, "token": token, "user": UserResponse.from_orm(user)}

# @router.post("/google")
# async def google_login(req: GoogleAuthRequest, response: Response, db: AsyncSession = Depends(get_db)):
#     res = await db.execute(select(User).where(User.email == req.email.lower().strip()))
#     user = res.scalars().first()
#     if not user:
#         user = User(
#             name=req.name or req.email.split("@")[0],
#             email=req.email.lower().strip(),
#             password_hash=get_password_hash("google_oauth_dummy_pass"),
#             google_id=req.google_id or f"google_{req.email}",
#         )
#         db.add(user)
#         await db.commit()
#         await db.refresh(user)

#     if user.status == "Disabled":
#         raise HTTPException(status_code=403, detail="Account is disabled")

#     token = create_access_token({"id": user.id, "email": user.email})
#     response.set_cookie(key="token", value=token, httponly=True, secure=True, samesite="none", max_age=604800)

#     return {"success": True, "token": token, "user": UserResponse.from_orm(user)}

# @router.post("/logout")
# async def logout(response: Response):
#     response.delete_cookie(key="token")
#     return {"success": True, "message": "Logged out successfully"}

# @router.get("/me")
# async def get_me(current_user: User = Depends(get_current_user)):
#     return {"user": UserResponse.from_orm(current_user)}










import os
import asyncio
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from ..database import get_db
from ..models import User, OtpVerification
from ..schemas import UserRegisterRequest, UserLoginRequest, GoogleAuthRequest, UserResponse
from ..auth import get_password_hash, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key="token", value=token, httponly=True,
        secure=True, samesite="none", max_age=604800,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: UserRegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    email = req.email.lower().strip()

    existing_res = await db.execute(select(User).where(User.email == email))
    if existing_res.scalars().first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    otp_result = await db.execute(
        select(OtpVerification)
        .where(
            OtpVerification.email == email,
            OtpVerification.otp_code == req.otp_code,
            OtpVerification.is_verified == True,
        )
        .order_by(desc(OtpVerification.created_at))
    )
    verified_otp = otp_result.scalars().first()

    if not verified_otp:
        raise HTTPException(status_code=400, detail="Please verify your email with the OTP first")

    if datetime.utcnow() > verified_otp.expires_at:
        raise HTTPException(status_code=400, detail="OTP verification has expired. Please verify again")

    new_user = User(
        name=req.name.strip(),
        email=email,
        password_hash=get_password_hash(req.password),
        phone=req.phone,
        age=req.age,
        location=req.location,
    )
    db.add(new_user)
    await db.delete(verified_otp)  # OTP can only be used once

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    await db.refresh(new_user)

    token = create_access_token({"id": new_user.id, "email": new_user.email})
    set_auth_cookie(response, token)

    return {"success": True, "token": token, "user": UserResponse.from_orm(new_user)}


@router.post("/login")
async def login(req: UserLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.email == req.email.lower().strip()))
    user = res.scalars().first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status == "Disabled":
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token({"id": user.id, "email": user.email})
    set_auth_cookie(response, token)

    return {"success": True, "token": token, "user": UserResponse.from_orm(user)}


@router.post("/google")
async def google_login(req: GoogleAuthRequest, response: Response, db: AsyncSession = Depends(get_db)):
    # Read at request time so it works even if .env loads after this file is imported
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Google sign-in is not configured")

    # Verify the token was issued by Google for OUR app. Runs in a thread
    # because it makes a blocking network call.
    try:
        idinfo = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            req.credential,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=10,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    if not idinfo.get("email_verified"):
        raise HTTPException(status_code=400, detail="Google email is not verified")

    email = idinfo.get("email", "").lower().strip()
    name = idinfo.get("name") or email.split("@")[0]
    google_id = idinfo.get("sub")

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalars().first()

    if not user:
        user = User(
            name=name,
            email=email,
            # Random, unguessable password: Google users never log in with it
            password_hash=get_password_hash(secrets.token_urlsafe(32)),
            google_id=google_id,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Account already exists. Please try again")
        await db.refresh(user)
    elif not user.google_id:
        # Link Google to an existing password account with the same email
        user.google_id = google_id
        await db.commit()

    if user.status == "Disabled":
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token({"id": user.id, "email": user.email})
    set_auth_cookie(response, token)

    return {"success": True, "token": token, "user": UserResponse.from_orm(user)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="token")
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"user": UserResponse.from_orm(current_user)}