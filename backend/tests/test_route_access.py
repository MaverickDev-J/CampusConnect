"""Exercise the real route dependencies with isolated storage and identities."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies import get_current_user
from api.routers import announcements, calendar


class RouteAccessTests(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(
            classrooms=SimpleNamespace(find_one=AsyncMock(return_value={
                "classroom_id": "private", "created_by": "owner", "members": [],
            })),
            calendar_events=SimpleNamespace(insert_one=AsyncMock()),
            announcements=SimpleNamespace(count_documents=AsyncMock()),
        )
        app = FastAPI()
        app.include_router(calendar.router)
        app.include_router(announcements.router)
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "outsider", "name": "Outside teacher", "role": "teacher",
        }
        self.client = TestClient(app)

    def test_calendar_rejects_other_classroom_before_writing(self):
        with patch.object(calendar, "get_db", return_value=self.db):
            response = self.client.post("/api/calendar/events", json={
                "title": "Revision", "date": "2026-11-06", "classroom_id": "private",
            })
        self.assertEqual(response.status_code, 403)
        self.db.calendar_events.insert_one.assert_not_awaited()

    def test_announcement_read_rejects_other_classroom_before_loading(self):
        with patch.object(announcements, "get_db", return_value=self.db):
            response = self.client.get("/api/announcements/private")
        self.assertEqual(response.status_code, 403)
        self.db.announcements.count_documents.assert_not_awaited()
