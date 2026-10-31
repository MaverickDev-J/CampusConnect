"""Real HTTP contract checks using a restricted PostgreSQL login role."""
import asyncio
from contextlib import AsyncExitStack
import os
from pathlib import Path
import secrets
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from core.config import settings
from postgres_main import create_app

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL for API integration")
class PostgresApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tag = uuid4().hex[:12]
        self.role = "api_test_" + self.tag
        self.password = secrets.token_hex(16)
        self.owner_url = os.environ["TEST_DATABASE_URL"]
        with psycopg.connect(self.owner_url) as connection:
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(self.role), sql.Literal(self.password)))
            grants = (Path(__file__).parents[1] / "migrations/runtime_grants.sql").read_text()
            for statement in grants.split(';'):
                if statement.strip():
                    connection.execute(statement.replace(':"runtime_role"', sql.Identifier(self.role).as_string(connection)))
        runtime_url = make_url(self.owner_url).set(username=self.role, password=self.password).render_as_string(hide_password=False)
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()
        self.stack.enter_context(patch.object(settings, "JWT_SECRET", "integration-test-secret-" + "x" * 32))
        self.app = create_app(runtime_url)
        await self.stack.enter_async_context(self.app.router.lifespan_context(self.app))
        self.client = await self.stack.enter_async_context(httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test"))

    async def asyncTearDown(self):
        await self.stack.aclose()
        with psycopg.connect(self.owner_url) as connection:
            connection.execute("DELETE FROM classrooms WHERE created_by IN (SELECT user_id FROM users WHERE email LIKE %s)", (f"%{self.tag}@example.com",))
            connection.execute("DELETE FROM users WHERE email LIKE %s", (f"%{self.tag}@example.com",))
            connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(self.role)))
            connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(self.role)))

    async def account(self, label, role="student"):
        email = f"{label}{self.tag}@example.com"
        response = await self.client.post("/api/auth/register", json={
            "email": email, "name": label, "password": "safe-test-password", "role": role,
        })
        self.assertEqual(response.status_code, 201, response.text)
        login = await self.client.post("/api/auth/login", data={"username": email.upper(), "password": "safe-test-password"})
        self.assertEqual(login.status_code, 200, login.text)
        return response.json(), {"Authorization": "Bearer " + login.json()["access_token"]}

    async def test_register_login_profile_and_password_contract(self):
        user, headers = await self.account("student")
        response = await self.client.get("/api/users/me", headers=headers)
        self.assertEqual(response.json()["user_id"], user["user_id"])
        self.assertNotIn("password", response.json())
        response = await self.client.patch("/api/users/me", headers=headers, json={"name": "Updated"})
        self.assertEqual(response.json()["name"], "Updated")
        duplicate = await self.client.post("/api/auth/register", json={
            "email": user["email"].upper(), "name": "Duplicate", "password": "safe-test-password",
        })
        self.assertEqual(duplicate.status_code, 409)
        denied = await self.client.post("/api/auth/register", json={
            "email": f"admin{self.tag}@example.com", "name": "Admin", "password": "safe-test-password", "role": "superadmin",
        })
        self.assertEqual(denied.status_code, 403)
        response = await self.client.post("/api/users/me/password", headers=headers, json={
            "old_password": "safe-test-password", "new_password": "new-safe-password",
        })
        self.assertEqual(response.status_code, 200, response.text)
        old = await self.client.post("/api/auth/login", data={"username": user["email"], "password": "safe-test-password"})
        self.assertEqual(old.status_code, 401)
        new = await self.client.post("/api/auth/login", data={"username": user["email"], "password": "new-safe-password"})
        self.assertEqual(new.status_code, 200)
        self.assertEqual((await self.client.get("/api/users/me", headers={"Authorization": "Bearer bad"})).status_code, 401)

    async def test_classroom_join_visibility_and_owner_deletion(self):
        teacher, teacher_headers = await self.account("teacher", "teacher")
        student, student_headers = await self.account("student")
        _, outsider_headers = await self.account("outsider", "teacher")
        response = await self.client.post("/api/classrooms", headers=teacher_headers, json={"name": "ML", "subject": "AI"})
        self.assertEqual(response.status_code, 201, response.text)
        classroom = response.json()
        self.assertEqual(classroom["member_count"], 1)
        cid = classroom["classroom_id"]
        listing = await self.client.get("/api/classrooms", headers=student_headers)
        self.assertEqual(listing.json()["total"], 0)
        self.assertEqual((await self.client.get(f"/api/classrooms/{cid}", headers=student_headers)).status_code, 404)
        self.assertEqual((await self.client.post("/api/classrooms", headers=student_headers, json={"name": "Forbidden"})).status_code, 403)
        joins = await asyncio.gather(*(self.client.post("/api/classrooms/join", headers=student_headers,
                json={"join_code": classroom["join_code"].lower()}) for _ in range(2)))
        self.assertTrue(all(response.status_code == 200 for response in joins))
        detail = await self.client.get(f"/api/classrooms/{cid}", headers=student_headers)
        self.assertEqual(detail.json()["member_count"], 2)
        self.assertEqual({m["user_id"] for m in detail.json()["members"]}, {teacher["user_id"], student["user_id"]})
        self.assertIn((await self.client.delete(f"/api/classrooms/{cid}", headers=outsider_headers)).status_code, (403,404))
        self.assertEqual((await self.client.delete(f"/api/classrooms/{cid}", headers=teacher_headers)).status_code, 200)
        self.assertEqual((await self.client.get("/api/classrooms", headers=teacher_headers)).json()["total"], 0)

    async def test_runtime_cannot_read_hashes_or_change_roles(self):
        user, _ = await self.account("student")
        async with self.app.state.accounts.factory() as session:
            with self.assertRaises(ProgrammingError) as error:
                await session.execute(text("SELECT password_hash FROM users"))
            self.assertEqual(getattr(error.exception.orig, "sqlstate", None), "42501")
        async with self.app.state.accounts.factory() as session:
            with self.assertRaises(ProgrammingError) as error:
                await session.execute(text("UPDATE users SET role='superadmin' WHERE user_id=:id"), {"id": user["user_id"]})
            self.assertEqual(getattr(error.exception.orig, "sqlstate", None), "42501")

    async def test_revoked_membership_and_deleted_user_take_effect_immediately(self):
        _, teacher_headers = await self.account("teacher", "teacher")
        student, headers = await self.account("student")
        classroom = (await self.client.post("/api/classrooms", headers=teacher_headers, json={"name": "Private"})).json()
        await self.client.post("/api/classrooms/join", headers=headers, json={"join_code": classroom["join_code"]})
        with psycopg.connect(self.owner_url) as connection:
            connection.execute("DELETE FROM classroom_members WHERE user_id=%s", (student["user_id"],))
        self.assertEqual((await self.client.get(f"/api/classrooms/{classroom['classroom_id']}", headers=headers)).status_code, 404)
        with psycopg.connect(self.owner_url) as connection:
            connection.execute("DELETE FROM users WHERE user_id=%s", (student["user_id"],))
        self.assertEqual((await self.client.get("/api/users/me", headers=headers)).status_code, 401)

    async def test_startup_rejects_owner_connection(self):
        unsafe_app = create_app(self.owner_url)
        with self.assertRaisesRegex(RuntimeError, "non-owner"):
            async with unsafe_app.router.lifespan_context(unsafe_app):
                self.fail("Owner connection should not start the API")
