import asyncio
from database.mongo import get_db, connect_db
from core.security import hash_password

async def check():
    await connect_db()
    db = get_db()
    
    print("--- USERS ---")
    async for user in db.users.find({}, {"password": 0}):
        print(user)
        
    print("\n--- CLASSROOMS ---")
    async for cls in db.classrooms.find({}):
        print(f"ID: {cls['classroom_id']}, Name: {cls['name']}, CreatedBy: {cls['created_by']}")

if __name__ == "__main__":
    asyncio.run(check())
