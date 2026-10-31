import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from api.services.access_policy import authorize_classroom, authorize_file


class AccessPolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = SimpleNamespace(
            classrooms=SimpleNamespace(find_one=AsyncMock(return_value={
                "classroom_id": "a", "created_by": "owner",
                "members": [{"user_id": "teacher"}, {"user_id": "student"}],
            })),
            file_metadata=SimpleNamespace(find_one=AsyncMock(return_value={
                "file_id": "file", "classroom_id": "a",
            })),
        )

    async def test_current_member_and_owner_can_read(self):
        for user in ("teacher", "student", "owner"):
            await authorize_classroom(self.db, "a", {"user_id": user, "role": "student"})

    async def test_teacher_cannot_write_other_classroom(self):
        with self.assertRaises(HTTPException) as error:
            await authorize_classroom(self.db, "a", {"user_id": "outsider", "role": "teacher"}, write=True)
        self.assertEqual(error.exception.status_code, 403)

    async def test_student_cannot_write_even_when_member(self):
        with self.assertRaises(HTTPException):
            await authorize_classroom(self.db, "a", {"user_id": "student", "role": "student"}, write=True)

    async def test_admin_can_access_existing_classroom(self):
        await authorize_classroom(self.db, "a", {"user_id": "admin", "role": "superadmin"}, write=True)

    async def test_missing_classroom(self):
        self.db.classrooms.find_one.return_value = None
        with self.assertRaises(HTTPException) as error:
            await authorize_classroom(self.db, "a", {"user_id": "teacher", "role": "teacher"})
        self.assertEqual(error.exception.status_code, 404)

    async def test_explicit_file_scope_cannot_expand(self):
        with self.assertRaises(HTTPException):
            await authorize_file(self.db, "file", {"user_id": "teacher", "role": "teacher"}, classroom_id="b")

    async def test_file_checks_current_membership(self):
        with self.assertRaises(HTTPException):
            await authorize_file(self.db, "file", {"user_id": "outsider", "role": "student"})
