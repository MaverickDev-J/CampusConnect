import asyncio
from uuid import uuid4
from database.mongo import connect_db, get_db, close_db
from core.security import hash_password

async def create_admin():
    await connect_db()
    db = get_db()
    
    email = "admin@campusmind.local"
    password = "adminpassword123"
    
    existing = await db.users.find_one({"email": email})
    if existing:
        print(f"User {email} already exists!")
    else:
        user_id = f"adm_{uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": "Super User Admin",
            "password": hash_password(password),
            "role": "superadmin",
            "profile": {},
        }
        await db.users.insert_one(user_doc)
        print(f"SUCCESS: Created super user admin: {email} / {password}")
        
    await close_db()

asyncio.run(create_admin())
