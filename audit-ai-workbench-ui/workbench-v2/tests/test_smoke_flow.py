"""关键路径冒烟：健康检查 → 建任务 → SQL 保存与敏感检查；以及访问加固。"""
from __future__ import annotations

import os
import unittest
from datetime import date
from pathlib import Path

from tests.test_api import AsgiClient
from backend import common as C
from backend import db
from backend.main import app


class SmokeFlowTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["WORKBENCH_SECRET"] = "smoke-test-secret-key"
        test_dir = Path("C:/tmp/audit-ai-workbench-tests")
        test_dir.mkdir(parents=True, exist_ok=True)
        cls.test_db = test_dir / "smoke-workbench.db"
        for suffix in ("", "-wal", "-shm"):
            Path(f"{cls.test_db}{suffix}").unlink(missing_ok=True)
        db.DB_PATH = cls.test_db
        db.init_db()
        cls.client = AsgiClient()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{cls.test_db}{suffix}").unlink(missing_ok=True)

    def test_unlock_task_sql_path(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        payload = health.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("version", payload)
        self.assertIn("backups", payload)
        self.assertIsNone(payload.get("secret_warning"))

        status = self.client.get("/api/access/status")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["required"])

        today = date.today().isoformat()
        task = self.client.post(
            "/api/tasks",
            json={
                "title": "冒烟任务",
                "planned_date": today,
                "due_at": "09:30",
                "priority": "high",
                "type": "task",
                "remind_at": today,
            },
        )
        self.assertEqual(task.status_code, 201, task.text)
        task_id = task.json()["id"]

        focus = self.client.get("/api/task-focus")
        self.assertEqual(focus.status_code, 200)
        body = focus.json()
        self.assertIn("nudges", body)
        self.assertTrue(any(item["id"] == task_id for item in body["tasks"]))

        reminders = self.client.get("/api/reminders")
        self.assertEqual(reminders.status_code, 200)
        self.assertGreaterEqual(reminders.json()["count"], 1)

        sql = self.client.post(
            "/api/sql-assets",
            json={
                "name": "冒烟 SQL",
                "purpose": "冒烟路径",
                "sql_text": "SELECT 1 AS ok WHERE password = 'secret1234'",
                "status": "draft",
                "tags": ["冒烟"],
                "tables": [],
            },
        )
        self.assertEqual(sql.status_code, 201, sql.text)
        asset_id = sql.json()["id"]

        sensitive = self.client.post(
            "/api/sql-assets/sensitive-check",
            json={"name": "冒烟 SQL", "sql_text": "SELECT 1 AS ok WHERE password = 'secret1234'"},
        )
        self.assertEqual(sensitive.status_code, 200)
        self.assertTrue(sensitive.json().get("findings"), sensitive.text)

        got = self.client.get(f"/api/sql-assets/{asset_id}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["name"], "冒烟 SQL")

        settings = self.client.get("/api/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertIn("backups", settings.json())
        self.assertIn("session_days", settings.json())

        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("text/html", index.headers.get("content-type", ""))


class AccessHardeningTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["WORKBENCH_SECRET"] = "access-harden-secret"
        test_dir = Path("C:/tmp/audit-ai-workbench-tests")
        test_dir.mkdir(parents=True, exist_ok=True)
        cls.test_db = test_dir / "access-harden-workbench.db"
        for suffix in ("", "-wal", "-shm"):
            Path(f"{cls.test_db}{suffix}").unlink(missing_ok=True)
        db.DB_PATH = cls.test_db
        db.init_db()
        cls.client = AsgiClient()
        C.clear_access_failures("testclient")
        C.clear_access_failures("127.0.0.1")
        C._ACCESS_FAILS.clear()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{cls.test_db}{suffix}").unlink(missing_ok=True)

    def test_password_fail_lock_and_session_revoke(self):
        C._ACCESS_FAILS.clear()
        updated = self.client.put("/api/settings", json={"access_password": "secret99"})
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["access_password_enabled"])

        locked = self.client.get("/api/tasks")
        self.assertEqual(locked.status_code, 401)

        for _ in range(5):
            bad = self.client.post("/api/access/unlock", json={"password": "wrong-password"})
            self.assertIn(bad.status_code, (401, 429), bad.text)

        blocked = self.client.post("/api/access/unlock", json={"password": "wrong-password"})
        self.assertEqual(blocked.status_code, 429, blocked.text)

        still = self.client.post("/api/access/unlock", json={"password": "secret99"})
        self.assertEqual(still.status_code, 429, still.text)

        C._ACCESS_FAILS.clear()
        ok = self.client.post("/api/access/unlock", json={"password": "secret99"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json()["unlocked"])
        self.assertIn("expires_at", ok.json())

        token = ok.json()["token"]
        self.client.put(
            "/api/settings",
            json={"access_password": "secret88"},
            headers={"X-Workbench-Access": token},
        )
        revoked = self.client.get("/api/tasks", headers={"X-Workbench-Access": token})
        self.assertEqual(revoked.status_code, 401)


if __name__ == "__main__":
    unittest.main()
