"""Account persistence with the same response shape during the staged cutover."""
import json
from sqlalchemy import text
from database.postgres import principal_session


class MongoAccounts:
    uses_profile_cache = True
    def __init__(self, db):
        self.db = db

    async def by_email(self, email):
        return await self.db.users.find_one({"email": email})

    async def by_id(self, user_id):
        return await self.db.users.find_one({"user_id": user_id})

    async def create(self, user):
        await self.db.users.insert_one(user)

    async def update(self, user_id, values):
        await self.db.users.update_one({"user_id": user_id}, {"$set": values})
        return await self.by_id(user_id)


class PostgresAccounts:
    uses_profile_cache = False
    def __init__(self, factory):
        self.factory = factory

    async def by_email(self, email):
        # Login precedes an authenticated principal; this narrowly scoped function
        # is the sole runtime path that reads credential hashes.
        async with self.factory() as session:
            row = (await session.execute(text("SELECT * FROM public.login_account(:email)"), {"email": email})).mappings().first()
            if not row:
                return None
            return dict(row)

    async def by_id(self, user_id):
        async with principal_session(self.factory, user_id) as session:
            row = (await session.execute(text("SELECT user_id,email,name,role,profile FROM users WHERE user_id=:id"), {"id": user_id})).mappings().first()
            return dict(row) if row else None

    async def create(self, user):
        async with self.factory() as session, session.begin():
            await session.execute(text("SELECT public.register_account(:id,:email,:name,:password,:role,CAST(:profile AS jsonb))"), {
                "id": user["user_id"], "email": user["email"], "name": user["name"],
                "password": user["password"], "role": user["role"], "profile": json.dumps(user["profile"]),
            })

    async def update(self, user_id, values):
        # Column allowlist is independent of caller-supplied fields.
        columns = {"name": "name", "password": "password_hash"}
        changes = {key: value for key, value in values.items() if key in columns}
        if not changes:
            raise ValueError("No account changes supplied")
        async with principal_session(self.factory, user_id) as session:
            assignments = ', '.join(f"{columns[key]}=:{key}" for key in changes)
            await session.execute(text(f"UPDATE users SET {assignments} WHERE user_id=:id"), {**changes, "id": user_id})
        return await self.by_id(user_id)


def get_accounts(request):
    accounts = getattr(request.app.state, "accounts", None)
    if accounts is not None:
        return accounts
    from database.mongo import get_db
    return MongoAccounts(get_db())
