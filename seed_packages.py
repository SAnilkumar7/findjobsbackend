"""
Production-safe package seed.
Inserts or updates ONLY the 4 packages. No admin, no demo users.
Safe to re-run any number of times.
"""

import asyncio
from database import AsyncSessionLocal, init_db
from models import Package

PACKAGES = [
    dict(
        id="pkg_it",
        name="IT Jobs Access",
        slug="it",
        description="Instant access to Software Engineering, DevOps, Cloud, AI/ML, and Data Analytics job listings with direct application links.",
        price=49.00,
        access_type="IT",
        is_active=True,
    ),
    dict(
        id="pkg_non_it",
        name="Non-IT Jobs Access",
        slug="non-it",
        description="Instant access to Operations, HR, Sales, Digital Marketing, Supply Chain, and Administrative roles.",
        price=39.00,
        access_type="NON_IT",
        is_active=True,
    ),
    dict(
        id="pkg_banking",
        name="Banking Jobs Access",
        slug="banking",
        description="Instant access to Commercial Banking, Wealth Management, NBFC, Risk Analysis, and FinTech career openings.",
        price=49.00,
        access_type="BANKING",
        is_active=True,
    ),
    dict(
        id="pkg_all",
        name="All Access Pass",
        slug="all",
        description="Complete unrestricted access to all 3 categories (IT + Non-IT + Banking). One single payment, zero recurring fees.",
        price=99.00,
        access_type="ALL",
        is_active=True,
    ),
]


async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        for p in PACKAGES:
            await session.merge(Package(**p))
        await session.commit()
    print(f"Packages seeded: {len(PACKAGES)}")


if __name__ == "__main__":
    asyncio.run(main())