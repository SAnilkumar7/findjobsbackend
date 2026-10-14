


import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db
from models import User, Admin

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