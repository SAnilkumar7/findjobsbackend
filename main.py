

# import os
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from .database import init_db
# from .routers import auth, packages, jobs, payments, access, admin, otp

# app = FastAPI(
#     title="Paid Job-Access Platform API",
#     description="High-performance async FastAPI backend with PostgreSQL and Razorpay integration",
#     version="1.0.0",
# )

# # Strict CORS configuration
# origins = [
#     "http://localhost:3000",
#     "http://127.0.0.1:3000",
#     os.getenv("APP_URL", "*"),
# ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Mount Routers
# app.include_router(auth.router)
# app.include_router(packages.router)
# app.include_router(jobs.router)
# app.include_router(payments.router)
# app.include_router(access.router)
# app.include_router(admin.router)
# app.include_router(otp.router)

# @app.on_event("startup")
# async def on_startup():
#     await init_db()

# @app.get("/api/health")
# async def health_check():
#     return {"status": "ok", "service": "jobaccess-fastapi"}









import os
from pathlib import Path
from dotenv import load_dotenv

# Must run BEFORE the imports below, because database.py and auth.py read env vars on import
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import auth, packages, jobs, payments, access, admin, otp

app = FastAPI(
    title="Paid Job-Access Platform API",
    description="High-performance async FastAPI backend with PostgreSQL and Razorpay integration",
    version="1.0.0",
)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app_url = os.getenv("APP_URL")
if app_url:
    origins.append(app_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(packages.router)
app.include_router(jobs.router)
app.include_router(payments.router)
app.include_router(access.router)
app.include_router(admin.router)
app.include_router(otp.router)

@app.on_event("startup")
async def on_startup():
    await init_db()

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "jobaccess-fastapi"}