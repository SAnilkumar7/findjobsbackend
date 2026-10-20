



import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Must run BEFORE the imports below, because database.py and auth.py read env vars on import
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from database import init_db, delete_expired_jobs
from routers import auth, packages, jobs, payments, access, admin, otp


async def _expiry_loop():
    """Deletes jobs whose deadline has passed, once every hour."""
    while True:
        try:
            deleted = await delete_expired_jobs()
            if deleted:
                print(f"Deleted {deleted} expired job(s)")
        except Exception as e:
            print("Expired-job cleanup failed:", e)
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup (replaces the old @app.on_event("startup") handler)
    await init_db()
    task = asyncio.create_task(_expiry_loop())
    yield
    task.cancel()


app = FastAPI(
    title="Paid Job-Access Platform API",
    description="High-performance async FastAPI backend with PostgreSQL and Razorpay integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Compress large responses (job lists with poster images)
app.add_middleware(GZipMiddleware, minimum_size=1000)

origins = [
    "https://findmyjobs.in",
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

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "jobaccess-fastapi"}