# """
# Database Seed Script for Neon / Supabase PostgreSQL
# Seeds initial packages, admin account, demo user, and demo jobs across IT, Non-IT, and Banking.
# """

# import asyncio
# from datetime import datetime
# from passlib.context import CryptContext
# from database import AsyncSessionLocal, init_db
# from models import Package, Admin, User, Job, UserAccess, Payment

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# async def seed_database():
#     await init_db()
#     async with AsyncSessionLocal() as session:
#         # Packages
#         packages = [
#             Package(
#                 id="pkg_it",
#                 name="IT Jobs Access",
#                 slug="it",
#                 description="Instant access to Software Engineering, DevOps, Cloud, AI/ML, and Data Analytics job listings with direct application links.",
#                 price=49.00,
#                 access_type="IT",
#                 is_active=True,
#             ),
#             Package(
#                 id="pkg_non_it",
#                 name="Non-IT Jobs Access",
#                 slug="non-it",
#                 description="Instant access to Operations, HR, Sales, Digital Marketing, Supply Chain, and Administrative roles.",
#                 price=39.00,
#                 access_type="NON_IT",
#                 is_active=True,
#             ),
#             Package(
#                 id="pkg_banking",
#                 name="Banking Jobs Access",
#                 slug="banking",
#                 description="Instant access to Commercial Banking, Wealth Management, NBFC, Risk Analysis, and FinTech career openings.",
#                 price=49.00,
#                 access_type="BANKING",
#                 is_active=True,
#             ),
#             Package(
#                 id="pkg_all",
#                 name="All Access Pass",
#                 slug="all",
#                 description="Complete unrestricted access to all 3 categories (IT + Non-IT + Banking). One single payment, zero recurring fees.",
#                 price=99.00,
#                 access_type="ALL",
#                 is_active=True,
#             ),
#         ]

#         for p in packages:
#             await session.merge(p)

#         # Admin
#         admin = Admin(
#             id="adm_01",
#             name="Platform Administrator",
#             email="admin@paidjobs.com",
#             password_hash=pwd_context.hash("admin123"),
#             role="SuperAdmin",
#             status="Active",
#         )
#         await session.merge(admin)

#         # Demo User
#         demo_user = User(
#             id="usr_demo_01",
#             name="Rahul Sharma",
#             email="jobseeker@example.com",
#             phone="+91 9876543210",
#             age=26,
#             location="Bengaluru, India",
#             profile_image="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=300&q=80",
#             password_hash=pwd_context.hash("user123"),
#             status="Active",
#         )
#         await session.merge(demo_user)

#         # Commit seeds
#         await session.commit()
#         print("Database seeded successfully!")

# if __name__ == "__main__":
#     asyncio.run(seed_database())










"""
Database Seed Script (LOCAL DEVELOPMENT ONLY)
Seeds initial packages, admin account, demo user for local testing.

DO NOT run against production. For production, use seed_packages.py.
To run locally: set ALLOW_DEMO_SEED=1 and make sure DATABASE_URL is not set
(so the local SQLite file is used).
"""

import asyncio
import os
from passlib.context import CryptContext
from database import AsyncSessionLocal, init_db, is_sqlite
from models import Package, Admin, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed_database():
    # Safety lock 1: must be explicitly enabled
    if os.getenv("ALLOW_DEMO_SEED") != "1":
        raise SystemExit(
            "Refusing to run demo seed. Use seed_packages.py for production."
        )

    # Safety lock 2: only allowed on the local SQLite database
    if not is_sqlite:
        raise SystemExit(
            "Refusing to run demo seed on a non-SQLite database (looks like production)."
        )

    await init_db()
    async with AsyncSessionLocal() as session:
        # Packages
        packages = [
            Package(
                id="pkg_it",
                name="IT Jobs Access",
                slug="it",
                description="Instant access to Software Engineering, DevOps, Cloud, AI/ML, and Data Analytics job listings with direct application links.",
                price=49.00,
                access_type="IT",
                is_active=True,
            ),
            Package(
                id="pkg_non_it",
                name="Non-IT Jobs Access",
                slug="non-it",
                description="Instant access to Operations, HR, Sales, Digital Marketing, Supply Chain, and Administrative roles.",
                price=39.00,
                access_type="NON_IT",
                is_active=True,
            ),
            Package(
                id="pkg_banking",
                name="Banking Jobs Access",
                slug="banking",
                description="Instant access to Commercial Banking, Wealth Management, NBFC, Risk Analysis, and FinTech career openings.",
                price=49.00,
                access_type="BANKING",
                is_active=True,
            ),
            Package(
                id="pkg_all",
                name="All Access Pass",
                slug="all",
                description="Complete unrestricted access to all 3 categories (IT + Non-IT + Banking). One single payment, zero recurring fees.",
                price=99.00,
                access_type="ALL",
                is_active=True,
            ),
        ]

        for p in packages:
            await session.merge(p)

        # Admin (demo only)
        # admin = Admin(
        #     id="adm_01",
        #     name="Platform Administrator",
        #     email="admin@paidjobs.com",
        #     password_hash=pwd_context.hash("admin123"),
        #     role="SuperAdmin",
        #     status="Active",
        # )
        # await session.merge(admin)

        # Demo User (demo only)
        # demo_user = User(
        #     id="usr_demo_01",
        #     name="Rahul Sharma",
        #     email="jobseeker@example.com",
        #     phone="+91 9876543210",
        #     age=26,
        #     location="Bengaluru, India",
        #     profile_image="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=300&q=80",
        #     password_hash=pwd_context.hash("user123"),
        #     status="Active",
        # )
        # await session.merge(demo_user)

        # await session.commit()
        # print("Local demo database seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_database())