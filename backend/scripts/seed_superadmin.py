"""
seed_superadmin.py — Standalone CLI script to seed the superadmin user.

Usage:
    cd backend
    uv run python scripts/seed_superadmin.py

Note: The server auto-seeds on startup too, so this is mainly for
manual database management or resetting the superadmin password.
"""

import asyncio
import os
import sys
from uuid import uuid4

from dotenv import load_dotenv

# Add backend root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from core.config import settings
from core.security import hash_password
from database.mongo import connect_db, close_db, get_db


async def seed():
    await connect_db()
    db = get_db()

    existing = await db.users.find_one({"role": "superadmin"})
    if existing:
        print(f"[INFO] Superadmin already exists: {existing['email']}")
        print(f"       user_id: {existing['user_id']}")
        resp = input("  → Delete and recreate? (y/N): ").strip().lower()
        if resp != "y":
            print("[SKIP] No changes made.")
            await close_db()
            return
        await db.users.delete_one({"user_id": existing["user_id"]})
        print("[DEL]  Old superadmin removed.")

    user_id = f"adm_{uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": settings.SUPERADMIN_EMAIL,
        "name": "Superadmin",
        "password": hash_password(settings.SUPERADMIN_PASSWORD),
        "role": "superadmin",
        "profile": {},
    }
    await db.users.insert_one(user_doc)

    print(f"[OK]   Superadmin created!")
    print(f"       Email:    {settings.SUPERADMIN_EMAIL}")
    print(f"       Password: {settings.SUPERADMIN_PASSWORD}")
    print(f"       user_id:  {user_id}")

    await close_db()


if __name__ == "__main__":
    asyncio.run(seed())
