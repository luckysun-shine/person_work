import unittest
import asyncio
from datetime import date, timedelta
from pathlib import Path

import httpx

from backend import db
from backend.main import app


class AsgiClient:
    """Small synchronous facade over httpx ASGITransport for unittest."""

    def request(self, method, url, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(run())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def close(self):
        pass


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_dir = Path("C:/tmp/audit-ai-workbench-tests")
        test_dir.mkdir(parents=True, exist_ok=True)
        cls.test_db = test_dir / "test-workbench.db"
        for suffix in ("", "-wal", "-shm"):
            Path(f"{cls.test_db}{suffix}").unlink(missing_ok=True)
        db.DB_PATH = cls.test_db
        db.init_db()
        # Avoid lifespan context deadlocks seen with some Starlette/httpx
        # combinations; the test database is initialized explicitly above.
        cls.client = AsgiClient()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{cls.test_db}{suffix}").unlink(missing_ok=True)

    def test_health_and_frontend(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        frontend = self.client.get("/")
        self.assertEqual(frontend.status_code, 200)
        self.assertIn("数智审监工作台", frontend.text)

    def test_dashboard_is_seeded(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["today_total"], 5)
        self.assertGreaterEqual(len(payload["projects"]), 3)

    def test_backup_create_download_and_restore(self):
        before = self.client.get("/api/projects/P-001").json()["project"]["progress"]
        created = self.client.post("/api/backups")
        self.assertEqual(created.status_code, 201)
        backup_name = created.json()["name"]
        listing = self.client.get("/api/backups").json()
        self.assertIn(backup_name, [item["name"] for item in listing])
        downloaded = self.client.get(f"/api/backups/{backup_name}/download")
        self.assertEqual(downloaded.status_code, 200)
        self.assertTrue(downloaded.content.startswith(b"SQLite format 3"))

        self.client.patch("/api/projects/P-001", json={"progress": 17})
        restored = self.client.post(f"/api/backups/{backup_name}/restore")
        self.assertEqual(restored.status_code, 200)
        after = self.client.get("/api/projects/P-001").json()["project"]["progress"]
        self.assertEqual(after, before)

    def test_unified_search_and_data_exchange(self):
        search = self.client.get("/api/search", params={"q": "采购付款"})
        self.assertEqual(search.status_code, 200)
        self.assertTrue(any(item["entity_type"] == "sql_asset" for item in search.json()["results"]))

        exported = self.client.get("/api/data/export.json")
        self.assertEqual(exported.status_code, 200)
        package = exported.json()
        self.assertIn("tasks", package["tables"])
        csv_export = self.client.get("/api/data/export.csv", params={"entity": "projects"})
        self.assertEqual(csv_export.status_code, 200)
        self.assertIn("name", csv_export.text)

        import_payload = {
            "schema_version": "0.7.0",
            "mode": "insert_only",
            "tables": {
                "tasks": [
                    {
                        "id": "T-IMPORT-001",
                        "title": "导入功能测试任务",
                        "planned_date": "2026-12-01",
                    }
                ]
            },
        }
        preview = self.client.post("/api/data/import/preview", json=import_payload)
        self.assertEqual(preview.json()["total"], 1)
        imported = self.client.post("/api/data/import", json=import_payload)
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["imported"]["tasks"], 1)
        task = self.client.get("/api/tasks/T-IMPORT-001")
        self.assertEqual(task.json()["title"], "导入功能测试任务")

        csv_payload = {
            "entity": "tasks",
            "mode": "insert_only",
            "csv_text": "id,title,planned_date\nT-IMPORT-CSV,CSV导入任务,2026-12-02\n",
        }
        csv_imported = self.client.post("/api/data/import.csv", json=csv_payload)
        self.assertEqual(csv_imported.status_code, 200)
        self.assertEqual(self.client.get("/api/tasks/T-IMPORT-CSV").status_code, 200)

    def test_task_create_and_update(self):
        created = self.client.post(
            "/api/tasks",
            json={"title": "验证新增任务", "priority": "high", "planned_date": "2026-10-20"},
        )
        self.assertEqual(created.status_code, 201)
        task = created.json()
        self.assertEqual(task["status"], "todo")
        updated = self.client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "done")

    def test_task_week_range_and_copy(self):
        first = self.client.post(
            "/api/tasks",
            json={
                "title": "周计划复制测试",
                "planned_date": "2026-11-02",
                "due_at": "10:30",
                "type": "model",
                "related_entity_id": "M-014",
            },
        )
        self.assertEqual(first.status_code, 201)
        task_id = first.json()["id"]
        week = self.client.get(
            "/api/tasks", params={"date_from": "2026-11-02", "date_to": "2026-11-06"}
        )
        self.assertIn(task_id, [item["id"] for item in week.json()])
        copied = self.client.post(f"/api/tasks/{task_id}/copy-next-week")
        self.assertEqual(copied.status_code, 201)
        self.assertTrue(copied.json()["created"])
        self.assertEqual(copied.json()["task"]["planned_date"], "2026-11-09")
        duplicate = self.client.post(f"/api/tasks/{task_id}/copy-next-week")
        self.assertFalse(duplicate.json()["created"])

        second = self.client.post(
            "/api/tasks",
            json={"title": "批量复制测试", "planned_date": "2026-11-03"},
        ).json()
        batch = self.client.post(
            "/api/tasks/batch-copy-next-week", json={"ids": [second["id"]]}
        )
        self.assertEqual(batch.json()["copied_count"], 1)

    def test_task_focus_and_week_review(self):
        focus = self.client.get("/api/task-focus")
        self.assertEqual(focus.status_code, 200)
        self.assertGreaterEqual(focus.json()["summary"]["total"], 5)
        self.assertTrue(all("is_overdue" in item for item in focus.json()["tasks"]))

        overdue = self.client.post(
            "/api/tasks",
            json={
                "title": "今日完成的逾期任务",
                "planned_date": (date.today() - timedelta(days=1)).isoformat(),
            },
        ).json()
        self.client.patch(f"/api/tasks/{overdue['id']}", json={"status": "done"})
        refreshed = self.client.get("/api/task-focus").json()
        completed = next(item for item in refreshed["tasks"] if item["id"] == overdue["id"])
        self.assertEqual(completed["status"], "done")
        self.assertFalse(completed["is_overdue"])

        saved = self.client.put(
            "/api/week-reviews/2026-11-02",
            json={
                "accomplishments": "完成规则复核",
                "blockers": "等待业务口径",
                "next_week_focus": "发布模型新版本",
                "energy_score": 4,
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["energy_score"], 4)
        loaded = self.client.get("/api/week-reviews/2026-11-02")
        self.assertEqual(loaded.json()["next_week_focus"], "发布模型新版本")

    def test_weekly_report_generation_save_and_markdown(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        week_start = monday.isoformat()
        self.client.patch("/api/tasks/T-001", json={"status": "done"})
        self.client.put(
            f"/api/week-reviews/{week_start}",
            json={
                "accomplishments": "完成采购异常样本复核",
                "blockers": "固定资产口径仍待确认",
                "next_week_focus": "发布采购模型新版本",
                "energy_score": 4,
            },
        )

        generated = self.client.post(f"/api/weekly-reports/{week_start}/generate")
        self.assertEqual(generated.status_code, 200)
        draft = generated.json()
        self.assertFalse(draft["saved"])
        self.assertGreaterEqual(draft["metrics"]["task_total"], 1)
        self.assertIn("完成采购异常样本复核", draft["highlights"])
        self.assertIn("发布采购模型新版本", draft["next_week_plan"])
        self.assertTrue(draft["source_snapshot"]["task_ids"])

        payload = {
            "title": "审计数据分析周报",
            "executive_summary": draft["executive_summary"],
            "highlights": draft["highlights"] + "\n- 人工补充成果",
            "risks": draft["risks"],
            "next_week_plan": draft["next_week_plan"],
            "metrics": draft["metrics"],
            "source_snapshot": draft["source_snapshot"],
        }
        saved = self.client.put(f"/api/weekly-reports/{week_start}", json=payload)
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["saved"])
        loaded = self.client.get(f"/api/weekly-reports/{week_start}")
        self.assertEqual(loaded.json()["title"], "审计数据分析周报")
        self.assertIn("人工补充成果", loaded.json()["highlights"])
        markdown = self.client.get(f"/api/weekly-reports/{week_start}/markdown")
        self.assertEqual(markdown.status_code, 200)
        self.assertIn("# 审计数据分析周报", markdown.text)

        invalid = self.client.post(
            f"/api/weekly-reports/{(monday + timedelta(days=1)).isoformat()}/generate"
        )
        self.assertEqual(invalid.status_code, 400)

    def test_note_create_and_search(self):
        created = self.client.post(
            "/api/notes",
            json={
                "type": "问题排查",
                "title": "唯一测试记录",
                "content": "用于验证记录检索。",
                "tags": ["测试"],
            },
        )
        self.assertEqual(created.status_code, 201)
        found = self.client.get("/api/notes", params={"q": "唯一测试记录"})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()[0]["title"], "唯一测试记录")

        note_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/notes/{note_id}",
            json={"title": "已更新的测试记录", "tags": ["测试", "已更新"]},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertIn("已更新", updated.json()["tags"])
        deleted = self.client.post("/api/notes/batch-delete", json={"ids": [note_id]})
        self.assertEqual(deleted.json()["affected"], 1)

    def test_navigation_crud_and_visit(self):
        created = self.client.post(
            "/api/navigation",
            json={"title": "测试入口", "url": "https://example.com/test", "category": "测试工具"},
        )
        self.assertEqual(created.status_code, 201)
        item = created.json()
        visited = self.client.post(f"/api/navigation/{item['id']}/visit")
        self.assertEqual(visited.json()["visit_count"], 1)
        updated = self.client.patch(f"/api/navigation/{item['id']}", json={"title": "已更新入口"})
        self.assertEqual(updated.json()["title"], "已更新入口")
        self.assertEqual(self.client.delete(f"/api/navigation/{item['id']}").status_code, 204)
        unsafe = self.client.post("/api/navigation", json={"title": "危险入口", "url": "javascript:alert(1)"})
        self.assertEqual(unsafe.status_code, 400)

    def test_model_and_project_lifecycle(self):
        model = self.client.post(
            "/api/models",
            json={
                "name": "测试监测模型",
                "current_version": "v1.0",
                "rule_definitions": [{"id": "R-01", "name": "测试规则"}],
                "update_steps": [{"title": "样本验证", "description": "复核十条样本", "done": False}],
            },
        )
        self.assertEqual(model.status_code, 201)
        model_id = model.json()["id"]
        updated_model = self.client.patch(
            f"/api/models/{model_id}",
            json={"current_version": "v1.1", "change_summary": "调整测试阈值", "update_steps": [{"title": "样本验证", "done": True}]},
        )
        self.assertEqual(updated_model.status_code, 200)
        detail = self.client.get(f"/api/models/{model_id}").json()
        self.assertEqual(detail["versions"][0]["version"], "v1.1")
        self.assertTrue(detail["update_steps"][0]["done"])

        project = self.client.post("/api/projects", json={"name": "测试审计项目", "type": "analysis"})
        self.assertEqual(project.status_code, 201)
        project_id = project.json()["id"]
        archived = self.client.patch(f"/api/projects/{project_id}", json={"status": "archived"})
        self.assertEqual(archived.json()["status"], "archived")
        self.assertEqual(self.client.delete(f"/api/projects/{project_id}").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/models/{model_id}").status_code, 204)

    def test_procedure_version_and_deployment_lifecycle(self):
        created = self.client.post("/api/procedures", json={"name": "sp_test_audit", "database_name": "audit_dw", "schema_name": "dbo", "definition_text": "CREATE PROCEDURE dbo.sp_test_audit AS SELECT 1", "rollback_text": "DROP PROCEDURE dbo.sp_test_audit"})
        self.assertEqual(created.status_code, 201)
        procedure_id = created.json()["id"]
        updated = self.client.patch(f"/api/procedures/{procedure_id}", json={"current_version": "v1.1", "status": "testing", "change_summary": "增加测试口径"})
        self.assertEqual(updated.status_code, 200)
        deployed = self.client.post(f"/api/procedures/{procedure_id}/deployments", json={"version": "v1.1", "environment": "testing", "status": "success", "validation_result": "样本验证通过"})
        self.assertEqual(deployed.status_code, 201)
        detail = self.client.get(f"/api/procedures/{procedure_id}").json()
        self.assertEqual(detail["versions"][0]["version"], "v1.1")
        self.assertEqual(detail["deployments"][0]["environment"], "testing")
        search = self.client.get("/api/search", params={"q": "sp_test_audit"}).json()
        self.assertTrue(any(item["entity_type"] == "procedure" and item["id"] == procedure_id for item in search["results"]))
        self.assertEqual(self.client.delete(f"/api/procedures/{procedure_id}").status_code, 204)

    def test_generic_report_templates_and_generation(self):
        templates = self.client.get("/api/report-templates")
        self.assertEqual(templates.status_code, 200)
        self.assertGreaterEqual(len(templates.json()), 4)
        generated = self.client.post("/api/reports/generate", json={"template_id": "RT-PROJECT", "period_start": "2026-10-19", "period_end": "2026-10-25", "related_entity_id": "P-001"})
        self.assertEqual(generated.status_code, 200)
        draft = generated.json()
        self.assertIn("项目进展报告", draft["title"])
        saved = self.client.post("/api/reports", json={"template_id": "RT-PROJECT", "title": draft["title"], "period_start": draft["period_start"], "period_end": draft["period_end"], "related_entity_id": "P-001", "sections": draft["sections"], "metrics": draft["metrics"], "source_snapshot": draft["source_snapshot"]})
        self.assertEqual(saved.status_code, 201)
        report_id = saved.json()["id"]
        self.assertEqual(self.client.get(f"/api/reports/{report_id}").json()["template_id"], "RT-PROJECT")
        updated_payload = {"template_id": "RT-PROJECT", "title": "采购项目阶段报告已更新", "period_start": draft["period_start"], "period_end": draft["period_end"], "related_entity_id": "P-001", "sections": {**draft["sections"], "summary": "已完成数据核验。"}, "metrics": draft["metrics"], "source_snapshot": draft["source_snapshot"], "status": "final"}
        updated = self.client.put(f"/api/reports/{report_id}", json=updated_payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "final")
        docx = self.client.get(f"/api/reports/{report_id}/docx")
        pdf = self.client.get(f"/api/reports/{report_id}/pdf")
        self.assertTrue(docx.content.startswith(b"PK"))
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        search = self.client.get("/api/search", params={"q": "阶段报告已更新"}).json()
        self.assertTrue(any(item["entity_type"] == "generated_report" and item["id"] == report_id for item in search["results"]))
        self.assertEqual(self.client.delete(f"/api/reports/{report_id}").status_code, 204)

    def test_custom_report_template_crud(self):
        created = self.client.post("/api/report-templates", json={"name": "审计发现跟踪模板", "type": "custom", "description": "跟踪问题整改", "section_labels": {"summary": "跟踪概览", "highlights": "整改进展", "risks": "逾期风险", "next_plan": "跟进安排"}})
        self.assertEqual(created.status_code, 201)
        template_id = created.json()["id"]
        updated = self.client.patch(f"/api/report-templates/{template_id}", json={"name": "审计发现闭环模板"})
        self.assertEqual(updated.json()["name"], "审计发现闭环模板")
        self.assertEqual(self.client.patch("/api/report-templates/RT-WEEKLY", json={"name": "不可改"}).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/report-templates/{template_id}").status_code, 204)

    def test_weekly_report_word_and_pdf_exports(self):
        week_start = date.today() - timedelta(days=date.today().weekday())
        docx = self.client.get(f"/api/weekly-reports/{week_start.isoformat()}/docx")
        pdf = self.client.get(f"/api/weekly-reports/{week_start.isoformat()}/pdf")
        self.assertEqual(docx.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(docx.content.startswith(b"PK"))
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_note_intelligent_organization(self):
        response = self.client.post(
            "/api/notes/assist",
            json={
                "title": "采购异常模型规则版本调整",
                "content": "M-014 命中结果复核后，需要调整阈值并记录版本变更原因。",
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["suggested_type"], "模型维护")
        self.assertIn("采购", result["suggested_tags"])
        self.assertEqual(result["suggested_relation"], "M-014")
        self.assertTrue(any(item["id"] == "N-002" for item in result["similar_notes"]))
        empty = self.client.post("/api/notes/assist", json={"title": "", "content": ""})
        self.assertEqual(empty.status_code, 400)

    def test_sql_asset_detail(self):
        assets = self.client.get("/api/sql-assets", params={"q": "采购付款"})
        self.assertEqual(assets.status_code, 200)
        self.assertEqual(assets.json()[0]["id"], "Q-128")
        detail = self.client.get("/api/sql-assets/Q-128")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("SELECT", detail.json()["sql_text"])

    def test_sql_description_and_risk_assistant(self):
        response = self.client.post(
            "/api/sql-assets/assist",
            json={
                "name": "采购付款异常明细",
                "sql_text": """SELECT * FROM dwd.purchase_payment p
                JOIN dwd.approval_flow a ON p.order_id = a.order_id
                WHERE p.payment_date BETWEEN :start_date AND :end_date""",
            },
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["operation"], "查询")
        self.assertIn("dwd.purchase_payment", result["tables"])
        self.assertIn("dwd.approval_flow", result["tables"])
        self.assertEqual(result["parameters"], ["end_date", "start_date"])
        self.assertIn("采购", result["tags"])
        self.assertTrue(any("SELECT *" in item for item in result["risk_notes"]))

        dangerous = self.client.post(
            "/api/sql-assets/assist",
            json={"name": "批量更新", "sql_text": "UPDATE audit_result SET status = 'done'"},
        )
        self.assertEqual(dangerous.json()["risk_level"], "high")

    def test_sql_asset_crud_and_batch_status(self):
        created = self.client.post(
            "/api/sql-assets",
            json={
                "name": "测试供应商查询",
                "purpose": "接口测试",
                "sql_text": "SELECT 1",
                "tags": ["测试"],
                "table_names": ["dual"],
            },
        )
        self.assertEqual(created.status_code, 201)
        asset_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/sql-assets/{asset_id}",
            json={"current_version": "v1.1", "validation_note": "已复核"},
        )
        self.assertEqual(updated.json()["current_version"], "v1.1")
        batched = self.client.post(
            "/api/sql-assets/batch-status",
            json={"ids": [asset_id], "status": "validated"},
        )
        self.assertEqual(batched.json()["affected"], 1)
        detail = self.client.get(f"/api/sql-assets/{asset_id}")
        self.assertEqual(detail.json()["status"], "validated")
        deleted = self.client.delete(f"/api/sql-assets/{asset_id}")
        self.assertEqual(deleted.status_code, 204)

    def test_sql_version_management(self):
        versions = self.client.get("/api/sql-assets/Q-128/versions")
        self.assertEqual(versions.status_code, 200)
        self.assertGreaterEqual(len(versions.json()), 1)
        created = self.client.post(
            "/api/sql-assets/Q-128/versions",
            json={
                "version": "v9.9-test",
                "sql_text": "SELECT 'version-test'",
                "change_summary": "自动化测试版本",
                "validation_status": "validated",
            },
        )
        self.assertEqual(created.status_code, 201)
        detail = self.client.get("/api/sql-assets/Q-128").json()
        self.assertEqual(detail["current_version"], "v9.9-test")
        duplicate = self.client.post(
            "/api/sql-assets/Q-128/versions",
            json={"version": "v9.9-test", "sql_text": "SELECT 2"},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_data_request_crud_and_batch_status(self):
        created = self.client.post(
            "/api/data-requests",
            json={
                "title": "测试数据提取",
                "purpose": "支持审计抽样",
                "scope": "2026 年付款数据",
                "due_at": "2026-10-28",
                "requester": "李四",
                "sql_text": "SELECT 1",
                "sql_current_version": "v1.0",
            },
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        request_id = body["id"]
        self.assertEqual(body["sql_current_version"], "v1.0")
        self.assertEqual(len(body.get("sql_versions") or []), 1)
        updated = self.client.patch(
            f"/api/data-requests/{request_id}",
            json={"purpose": "确认字段口径", "sql_text": "SELECT 2"},
        )
        self.assertEqual(updated.json()["purpose"], "确认字段口径")
        batched = self.client.post(
            "/api/data-requests/batch-status",
            json={"ids": [request_id], "status": "done"},
        )
        self.assertEqual(batched.json()["affected"], 1)
        detail = self.client.get(f"/api/data-requests/{request_id}")
        self.assertEqual(detail.json()["status"], "done")
        deleted = self.client.post(
            "/api/data-requests/batch-delete", json={"ids": [request_id]}
        )
        self.assertEqual(deleted.json()["affected"], 1)

    def test_model_run_and_project_relation(self):
        run = self.client.post(
            "/api/models/M-014/runs",
            json={
                "started_at": "2026-10-21T06:30:00+08:00",
                "finished_at": "2026-10-21T06:42:00+08:00",
                "status": "success",
                "scanned_count": 12000,
                "hit_count": 24,
                "reviewed_count": 10,
                "result_summary": "自动化测试运行",
            },
        )
        self.assertEqual(run.status_code, 201)
        runs = self.client.get("/api/models/M-014/runs")
        created_run = next(item for item in runs.json() if item["id"] == run.json()["id"])
        self.assertEqual(created_run["hit_count"], 24)

        relation = self.client.post(
            "/api/projects/P-009/relations",
            json={
                "entity_type": "sql_asset",
                "entity_id": "Q-121",
                "relation_type": "evidence",
                "note": "报告证据查询",
            },
        )
        self.assertEqual(relation.status_code, 201)
        relation_id = relation.json()["id"]
        graph = self.client.get("/api/projects/P-009/relations")
        self.assertTrue(any(item["entity_label"] == "固定资产处置审批链" for item in graph.json()["relations"]))
        deleted = self.client.delete(f"/api/projects/P-009/relations/{relation_id}")
        self.assertEqual(deleted.status_code, 204)

    def test_model_run_review_update_delete_and_stats_sync(self):
        model = self.client.post("/api/models", json={"name": "运行统计测试模型"}).json()
        model_id = model["id"]
        newer = self.client.post(
            f"/api/models/{model_id}/runs",
            json={"started_at": "2026-10-22T08:00:00+08:00", "finished_at": "2026-10-22T08:10:00+08:00",
                  "hit_count": 30, "reviewed_count": 5},
        ).json()
        # 补录一条更早的运行：不应覆盖最新统计
        older = self.client.post(
            f"/api/models/{model_id}/runs",
            json={"started_at": "2026-10-01T08:00:00+08:00", "finished_at": "2026-10-01T08:10:00+08:00",
                  "hit_count": 99, "reviewed_count": 0},
        ).json()
        detail = self.client.get(f"/api/models/{model_id}").json()
        self.assertEqual(detail["hit_count"], 30)
        self.assertEqual(detail["pending_review_count"], 25)
        self.assertEqual(detail["last_run_at"], "2026-10-22T08:10:00+08:00")

        too_many = self.client.patch(f"/api/models/{model_id}/runs/{newer['id']}", json={"reviewed_count": 31})
        self.assertEqual(too_many.status_code, 400)
        reviewed = self.client.patch(f"/api/models/{model_id}/runs/{newer['id']}", json={"reviewed_count": 30})
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(self.client.get(f"/api/models/{model_id}").json()["pending_review_count"], 0)

        self.assertEqual(self.client.delete(f"/api/models/{model_id}/runs/{newer['id']}").status_code, 204)
        detail = self.client.get(f"/api/models/{model_id}").json()
        self.assertEqual(detail["hit_count"], 99)
        self.assertEqual(detail["pending_review_count"], 99)
        self.assertEqual(self.client.delete(f"/api/models/{model_id}/runs/{older['id']}").status_code, 204)
        detail = self.client.get(f"/api/models/{model_id}").json()
        self.assertEqual(detail["hit_count"], 0)
        self.assertIsNone(detail["last_run_at"])
        self.assertEqual(self.client.delete(f"/api/models/{model_id}/runs/{older['id']}").status_code, 404)
        self.client.delete(f"/api/models/{model_id}")

    def test_delete_project_clears_soft_references(self):
        project = self.client.post("/api/projects", json={"name": "待删除监管项"}).json()
        project_id = project["id"]
        sql_asset = self.client.post(
            "/api/sql-assets", json={"name": "删除测试 SQL", "sql_text": "SELECT 1", "related_project_id": project_id}
        ).json()
        task = self.client.post(
            "/api/tasks", json={"title": "删除测试任务", "related_entity_type": "project", "related_entity_id": project_id}
        ).json()
        self.assertEqual(self.client.delete(f"/api/projects/{project_id}").status_code, 204)
        self.assertIsNone(self.client.get(f"/api/sql-assets/{sql_asset['id']}").json()["related_project_id"])
        refreshed_task = self.client.get(f"/api/tasks/{task['id']}").json()
        self.assertIsNone(refreshed_task["related_entity_id"])
        self.assertIsNone(refreshed_task["related_entity_type"])

    def test_project_detail_and_progress_update(self):
        detail = self.client.get("/api/projects/P-001")
        self.assertEqual(detail.status_code, 200)
        self.assertGreaterEqual(detail.json()["project"]["relation_count"], 2)
        self.assertIn("tasks", detail.json())
        updated = self.client.patch(
            "/api/projects/P-001",
            json={"progress": 81, "next_action": "完成界面验收"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["progress"], 81)

    def test_settings_and_backup_retention(self):
        settings = self.client.get("/api/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertGreaterEqual(settings.json()["backup_retention"], 3)
        updated = self.client.put("/api/settings", json={"backup_retention": 5})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["backup_retention"], 5)
        created = self.client.post("/api/backups")
        self.assertEqual(created.status_code, 201)
        self.assertIn("pruned", created.json())

    def test_import_diff_preview_and_table_restore(self):
        preview = self.client.post(
            "/api/data/import/preview",
            json={
                "schema_version": "1.5.0",
                "mode": "merge",
                "tables": {
                    "tasks": [
                        {"id": "T-001", "title": "复核采购异常模型本周命中样本"},
                        {"id": "T-DIFF-NEW", "title": "差异预览新任务", "planned_date": "2026-12-10"},
                    ]
                },
            },
        )
        self.assertEqual(preview.status_code, 200)
        body = preview.json()
        self.assertIn("diff", body)
        self.assertEqual(body["summary"]["new"], 1)
        self.assertGreaterEqual(body["diff"]["tasks"]["unchanged"] + body["diff"]["tasks"]["updated"], 1)

        backup = self.client.post("/api/backups").json()["name"]
        self.client.post(
            "/api/tasks",
            json={"title": "按表恢复后应被覆盖的任务", "planned_date": "2026-12-11"},
        )
        restored = self.client.post(
            f"/api/backups/{backup}/restore-tables",
            json={"tables": ["tasks"]},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertIn("tasks", restored.json()["restored_tables"])

    def test_saved_searches_and_recent_history(self):
        search = self.client.get("/api/search", params={"q": "采购付款"})
        self.assertEqual(search.status_code, 200)
        recent = self.client.get("/api/recent-searches")
        self.assertEqual(recent.status_code, 200)
        self.assertTrue(any(item["query"] == "采购付款" for item in recent.json()))
        created = self.client.post(
            "/api/saved-searches",
            json={"name": "采购相关", "query": "采购", "types": "sql_asset"},
        )
        self.assertEqual(created.status_code, 201)
        search_id = created.json()["id"]
        listing = self.client.get("/api/saved-searches")
        self.assertTrue(any(item["id"] == search_id for item in listing.json()))
        self.assertEqual(self.client.delete(f"/api/saved-searches/{search_id}").status_code, 204)
        self.assertEqual(self.client.delete("/api/recent-searches").status_code, 204)

    def test_report_finalize_versions_and_template_import(self):
        week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        saved = self.client.put(
            f"/api/weekly-reports/{week_start}",
            json={
                "title": "本周定稿测试",
                "executive_summary": "概览",
                "highlights": "进展",
                "risks": "风险",
                "next_week_plan": "计划",
                "status": "draft",
                "change_summary": "首次保存",
            },
        )
        self.assertEqual(saved.status_code, 200)
        finalized = self.client.post(f"/api/weekly-reports/{week_start}/finalize")
        self.assertEqual(finalized.status_code, 200)
        self.assertEqual(finalized.json()["status"], "final")
        versions = self.client.get(f"/api/weekly-reports/{week_start}/versions")
        self.assertGreaterEqual(len(versions.json()), 2)

        created = self.client.post(
            "/api/report-templates",
            json={
                "name": "部门封面模板",
                "type": "custom",
                "description": "带封面",
                "section_labels": {"summary": "概览", "highlights": "成果", "risks": "风险", "next_plan": "计划"},
                "cover": {"enabled": True, "org_name": "审计监察部", "subtitle": "周报封面", "footer": "内部资料"},
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["cover"]["enabled"])
        exported = self.client.get("/api/report-templates/export")
        self.assertEqual(exported.status_code, 200)
        package = exported.json()
        self.assertGreaterEqual(len(package["templates"]), 1)
        imported = self.client.post(
            "/api/report-templates/import",
            json={
                "mode": "merge",
                "templates": [
                    {
                        "name": "导入的专项模板",
                        "type": "audit",
                        "description": "从 JSON 导入",
                        "section_labels": {"summary": "概览", "highlights": "发现", "risks": "风险", "next_plan": "整改"},
                        "cover": {"enabled": True, "org_name": "审计监察部", "subtitle": "专项检查", "footer": "内部"},
                    }
                ],
            },
        )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["imported"], 1)

    def test_ai_settings_mask_and_clear(self):
        updated = self.client.put(
            "/api/settings",
            json={
                "ai": {
                    "enabled": True,
                    "base_url": "https://example.com/v1",
                    "model": "demo-model",
                    "api_key": "sk-test-secret-key",
                    "include_sql_text": False,
                }
            },
        )
        self.assertEqual(updated.status_code, 200)
        ai = updated.json()["ai"]
        self.assertTrue(ai["enabled"])
        self.assertTrue(ai["has_api_key"])
        self.assertIn("****", ai["api_key_masked"])
        self.assertNotIn("sk-test-secret-key", ai["api_key_masked"])
        self.assertFalse(ai["include_sql_text"])
        cleared = self.client.put("/api/settings", json={"ai": {"clear_api_key": True}})
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(cleared.json()["ai"]["has_api_key"])

    def test_access_password_unlock_and_guard(self):
        enabled = self.client.put("/api/settings", json={"access_password": "pass-1234"})
        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(enabled.json()["access_password_enabled"])
        blocked = self.client.get("/api/projects")
        self.assertEqual(blocked.status_code, 401)
        unlock = self.client.post("/api/access/unlock", json={"password": "pass-1234"})
        self.assertEqual(unlock.status_code, 200)
        token = unlock.json()["token"]
        ok = self.client.get("/api/projects", headers={"X-Workbench-Access": token})
        self.assertEqual(ok.status_code, 200)
        cleared = self.client.put(
            "/api/settings",
            json={"clear_access_password": True},
            headers={"X-Workbench-Access": token},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(cleared.json()["access_password_enabled"])

    def test_task_waiting_on_and_focus_buckets(self):
        later_date = (date.today() + timedelta(days=14)).isoformat()
        created = self.client.post(
            "/api/tasks",
            json={
                "title": "以后任务",
                "planned_date": later_date,
                "status": "todo",
                "waiting_on": "业务方确认",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["waiting_on"], "业务方确认")
        later = self.client.get("/api/task-focus", params={"bucket": "later"})
        self.assertEqual(later.status_code, 200)
        self.assertTrue(any(item["id"] == created.json()["id"] for item in later.json()["tasks"]))
        done = self.client.patch(
            f"/api/tasks/{created.json()['id']}",
            json={"status": "done", "planned_date": date.today().isoformat()},
        )
        self.assertEqual(done.status_code, 200)
        done_bucket = self.client.get("/api/task-focus", params={"bucket": "done"})
        self.assertEqual(done_bucket.status_code, 200)
        self.assertTrue(any(item["id"] == created.json()["id"] for item in done_bucket.json()["tasks"]))

    def test_data_request_sql_versions(self):
        created = self.client.post(
            "/api/data-requests",
            json={
                "title": "带 SQL 版本的请求",
                "purpose": "日常取数存档",
                "requester": "张三",
                "department": "审计监察部",
                "status": "waiting",
                "sql_text": "SELECT id FROM demo",
                "sql_current_version": "v1.0",
            },
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        request_id = body["id"]
        self.assertEqual(body["requester"], "张三")
        self.assertEqual(body["department"], "审计监察部")
        self.assertEqual(body["sql_current_version"], "v1.0")

        version = self.client.post(
            f"/api/data-requests/{request_id}/sql-versions",
            json={
                "version": "v1.1",
                "sql_text": "SELECT id, name FROM demo",
                "change_summary": "补充姓名字段",
            },
        )
        self.assertEqual(version.status_code, 201)
        detail = self.client.get(f"/api/data-requests/{request_id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["sql_current_version"], "v1.1")
        self.assertIn("name", payload["sql_text"])
        self.assertGreaterEqual(len(payload.get("sql_versions") or []), 2)

        first_version_id = next(
            item["id"] for item in payload["sql_versions"] if item["version"] == "v1.0"
        )
        restored = self.client.post(
            f"/api/data-requests/{request_id}/sql-versions/{first_version_id}/restore"
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["sql_current_version"], "v1.0")
        self.assertEqual(restored.json()["sql_text"], "SELECT id FROM demo")

        duplicate = self.client.post(
            f"/api/data-requests/{request_id}/sql-versions",
            json={"version": "v1.1", "sql_text": "SELECT 3", "change_summary": "重复"},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_sql_diff_and_sensitive_check(self):
        asset = self.client.post(
            "/api/sql-assets",
            json={
                "name": "敏感检查样例",
                "purpose": "测试",
                "sql_text": "SELECT 1 AS id",
                "current_version": "v1.0",
                "status": "draft",
            },
        )
        self.assertEqual(asset.status_code, 201)
        asset_id = asset.json()["id"]
        version = self.client.post(
            f"/api/sql-assets/{asset_id}/versions",
            json={
                "version": "v1.1",
                "validation_status": "draft",
                "change_summary": "加入密钥样例",
                "sql_text": "SELECT 1 AS id -- api_key = 'sk-abcdefghijklmnopqrstuvwxyz'",
            },
        )
        self.assertEqual(version.status_code, 201)
        diff = self.client.get(
            f"/api/sql-assets/{asset_id}/versions/diff",
            params={"left": "v1.0", "right": "v1.1"},
        )
        self.assertEqual(diff.status_code, 200)
        self.assertTrue(diff.json()["changed"])
        self.assertGreaterEqual(len(diff.json()["sensitive_findings"]), 1)
        check = self.client.post(
            "/api/sql-assets/sensitive-check",
            json={"sql_text": "password = 'SuperSecret123'"},
        )
        self.assertEqual(check.status_code, 200)
        self.assertGreaterEqual(check.json()["count"], 1)

    def test_calendar_subscription_crud(self):
        created = self.client.post(
            "/api/calendar/subscriptions",
            json={
                "name": "测试 ICS",
                "provider": "ics",
                "ics_url": "https://example.com/calendar.ics",
                "enabled": True,
            },
        )
        self.assertEqual(created.status_code, 201)
        sub_id = created.json()["id"]
        listing = self.client.get("/api/calendar/subscriptions")
        self.assertTrue(any(item["id"] == sub_id for item in listing.json()))
        events = self.client.get("/api/calendar/events")
        self.assertEqual(events.status_code, 200)
        self.assertEqual(self.client.delete(f"/api/calendar/subscriptions/{sub_id}").status_code, 204)

    def test_task_completion_and_recurrence(self):
        planned = date.today().isoformat()
        created = self.client.post(
            "/api/tasks",
            json={
                "title": "周报重复任务",
                "planned_date": planned,
                "status": "todo",
                "recurrence": "weekly",
                "actual_minutes": 0,
            },
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.json()["id"]
        done = self.client.patch(
            f"/api/tasks/{task_id}",
            json={
                "status": "done",
                "completion_result": "已提交周报",
                "actual_minutes": 45,
            },
        )
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()["completion_result"], "已提交周报")
        self.assertEqual(done.json()["actual_minutes"], 45)
        self.assertIn("spawned_next", done.json())
        self.assertEqual(done.json()["spawned_next"]["status"], "todo")
        next_date = (date.today() + timedelta(days=7)).isoformat()
        self.assertEqual(done.json()["spawned_next"]["planned_date"], next_date)

    def test_note_favorite_archive_and_revisions(self):
        created = self.client.post(
            "/api/notes",
            json={"type": "随手记录", "title": "可修订记录", "content": "初稿", "tags": ["测试"]},
        )
        self.assertEqual(created.status_code, 201)
        note_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/notes/{note_id}",
            json={"content": "二稿", "is_favorite": True},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["is_favorite"] in (1, True))
        revisions = self.client.get(f"/api/notes/{note_id}/revisions")
        self.assertEqual(revisions.status_code, 200)
        self.assertGreaterEqual(len(revisions.json()), 1)
        archived = self.client.patch(f"/api/notes/{note_id}", json={"is_archived": True})
        self.assertEqual(archived.status_code, 200)
        active = self.client.get("/api/notes", params={"archived": "false"})
        self.assertFalse(any(item["id"] == note_id for item in active.json()))
        favorites = self.client.get("/api/notes", params={"favorite": "true", "archived": "true"})
        self.assertTrue(any(item["id"] == note_id for item in favorites.json()))

    def test_request_combined_filters_and_stats(self):
        created = self.client.post(
            "/api/data-requests",
            json={
                "title": "组合筛选请求",
                "purpose": "采购审计",
                "requester": "李四",
                "department": "审计监察部",
                "status": "working",
            },
        )
        self.assertEqual(created.status_code, 201)
        filtered = self.client.get(
            "/api/data-requests",
            params={"requester": "李四", "department": "审计", "status": "working", "q": "组合"},
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertTrue(any(item["id"] == created.json()["id"] for item in filtered.json()))
        stats = self.client.get("/api/stats", params={"period": "month"})
        self.assertEqual(stats.status_code, 200)
        body = stats.json()
        self.assertIn("tasks", body)
        self.assertIn("requests", body)
        self.assertIn("drilldown", body["tasks"])

    def test_project_templates_and_auto_backup_setting(self):
        templates = self.client.get("/api/project-templates")
        self.assertEqual(templates.status_code, 200)
        self.assertGreaterEqual(len(templates.json()), 1)
        template_id = templates.json()[0]["id"]
        project = self.client.post(
            "/api/projects",
            json={"name": "模板项目", "template_id": template_id},
        )
        self.assertEqual(project.status_code, 201)
        self.assertTrue(project.json()["goal"])
        settings = self.client.put("/api/settings", json={"auto_backup_hours": 24})
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json()["auto_backup_hours"], 24)
        check = self.client.post("/api/backups/auto-check")
        self.assertEqual(check.status_code, 200)
        self.assertTrue(check.json()["enabled"])
        self.assertTrue(check.json()["created"])

    def test_home_layout_settings(self):
        current = self.client.get("/api/settings")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["home_layout"], ["tasks", "projects", "requests", "quick"])
        updated = self.client.put(
            "/api/settings",
            json={"home_layout": ["quick", "tasks", "bogus", "requests"]},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["home_layout"], ["quick", "tasks", "requests", "projects"])


if __name__ == "__main__":
    unittest.main()
