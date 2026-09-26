


# from datetime import datetime
# from fastapi import APIRouter, Depends, HTTPException, status, Response
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select
# from sqlalchemy import desc
# from .database import get_db
# from ..models import User, OtpVerification
# from ..schemas import UserRegisterRequest, UserLoginRequest, GoogleAuthRequest, UserResponse
# from ..auth import get_password_hash, verify_password, create_access_token, get_current_user

# router = APIRouter(prefix="/api/auth", tags=["auth"])

# @router.post("/register", status_code=status.HTTP_201_CREATED)
# async def register(req: UserRegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
#     email = req.email.lower().strip()

#     existing_res = await db.execute(select(User).where(User.email == email))
#     if existing_res.scalars().first():
#         raise HTTPException(status_code=409, detail="An account with this email already exists")

#     # Verify the email was OTP-verified before allowing registration
#     otp_result = await db.execute(
#         select(OtpVerification)
#         .where(
#             OtpVerification.email == email,
#             OtpVerification.otp_code == req.otp_code,
#             OtpVerification.is_verified == True,
#         )
#         .order_by(desc(OtpVerification.created_at))
#     )
#     verified_otp = otp_result.scalars().first()

#     if not verified_otp:
#         raise HTTPException(status_code=400, detail="Please verify your email with the OTP first")

#     if datetime.utcnow() > verified_otp.expires_at:
#         raise HTTPException(status_code=400, detail="OTP verification has expired. Please verify again")

#     new_user = User(
#         name=req.name.strip(),
#         email=email,
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
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from .database import get_db
from .models import User, Admin

JWT_SECRET = os.getenv("JWT_SECRET", "jobaccess_super_secret_jwt_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = None
    if credentials:
        token = credentials.credentials
    elif "token" in request.cookies:
        token = request.cookies.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("id")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None or user.status == "Disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account disabled or deleted")
    return user

async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    token = None
    if credentials:
        token = credentials.credentials
    elif "admin_token" in request.cookies:
        token = request.cookies.get("admin_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        admin_id: str = payload.get("id")
        role: str = payload.get("role")
        if admin_id is None or role != "Admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permissions required")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate admin token")

    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalars().first()
    if admin is None or admin.status == "Disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account deactivated")
    return admin