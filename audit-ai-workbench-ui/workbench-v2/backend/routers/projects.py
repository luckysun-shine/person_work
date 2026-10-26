"""API routes: projects."""
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import difflib
import io
import json
import re
import sqlite3
import time

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from .. import common as C
from ..ai_client import (
    AINotConfigured,
    AIRequestError,
    enhance_note_assist,
    enhance_sql_assist,
    enhance_weekly_report,
)
from ..calendar_sync import sync_subscription_events, window_for_settings
from ..db import PROJECT_DIR, connect, init_db, new_id, row_to_dict, transaction, utc_now
from ..report_exports import report_docx, report_markdown, report_pdf
from ..schemas import (
    AccessUnlock,
    BatchIds,
    BatchRequestStatus,
    BatchSqlStatus,
    BatchTaskCopy,
    CalendarSubscriptionCreate,
    CalendarSubscriptionUpdate,
    CsvImportPayload,
    DataImportPayload,
    DataRequestCreate,
    DataRequestUpdate,
    GenericReportGenerate,
    GenericReportUpsert,
    ModelCreate,
    ModelRunCreate,
    ModelUpdate,
    NavigationCreate,
    NavigationUpdate,
    NoteCreate,
    NoteAssistRequest,
    NoteUpdate,
    ProjectCreate,
    ProjectRelationCreate,
    ProjectTemplateCreate,
    ProjectTemplateUpdate,
    ProjectUpdate,
    ProcedureCreate,
    ProcedureDeploymentCreate,
    ProcedureUpdate,
    ReportTemplateCreate,
    ReportTemplateImport,
    ReportTemplateUpdate,
    SavedSearchCreate,
    SavedSearchUpdate,
    SettingsUpdate,
    SqlAssetCreate,
    SqlAssetUpdate,
    SqlAssistRequest,
    SqlVersionCreate,
    TableRestorePayload,
    TaskCreate,
    TaskUpdate,
    WeekReviewUpsert,
    WeeklyReportUpsert,
)
from ..secrets_util import decrypt_secret, encrypt_secret, mask_secret

router = APIRouter(tags=["projects"])

@router.get("/api/projects")
def list_projects() -> list[dict]:
    return C.fetch_all(
        """SELECT p.*, COUNT(r.id) AS relation_count
        FROM projects p LEFT JOIN project_relations r ON r.project_id = p.id
        GROUP BY p.id ORDER BY p.updated_at DESC"""
    )


@router.get("/api/project-templates")
def list_project_templates() -> list[dict]:
    return C.fetch_all("SELECT * FROM project_templates ORDER BY name")


@router.post("/api/project-templates", status_code=status.HTTP_201_CREATED)
def create_project_template(payload: ProjectTemplateCreate) -> dict:
    item_id = new_id("PT")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO project_templates
            (id,name,project_type,description,goal_template,next_action_template,checklist_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                item_id, payload.name, payload.project_type, payload.description,
                payload.goal_template, payload.next_action_template,
                json.dumps(payload.checklist, ensure_ascii=False), now, now,
            ),
        )
    return C.fetch_one("SELECT * FROM project_templates WHERE id = ?", (item_id,))


@router.patch("/api/project-templates/{template_id}")
def update_project_template(template_id: str, payload: ProjectTemplateUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "checklist" in changes:
        changes["checklist_json"] = json.dumps(changes.pop("checklist"), ensure_ascii=False)
    return C.update_record("project_templates", template_id, changes, "项目模板不存在")


@router.delete("/api/project-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_template(template_id: str) -> Response:
    return C.delete_record("project_templates", template_id, "项目模板不存在")


@router.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate) -> dict:
    project_id = new_id("P")
    now = utc_now()
    name = payload.name
    project_type = payload.type
    goal = payload.goal
    next_action = payload.next_action
    checklist: list[str] = []
    if payload.template_id:
        template = C.fetch_one("SELECT * FROM project_templates WHERE id = ?", (payload.template_id,))
        if not template:
            raise HTTPException(status_code=404, detail="项目模板不存在")
        project_type = project_type or template.get("project_type") or "analysis"
        if not goal:
            goal = template.get("goal_template") or ""
        if not next_action:
            next_action = template.get("next_action_template") or ""
        checklist = template.get("checklist") or []
        if checklist and goal and "检查清单" not in goal:
            goal = f"{goal}\n\n检查清单：\n" + "\n".join(f"- [ ] {item}" for item in checklist)
    with transaction() as connection:
        connection.execute(
            """INSERT INTO projects
            (id,name,type,goal,status,progress,due_date,next_action,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (project_id, name, project_type, goal, payload.status, payload.progress,
             payload.due_date, next_action, now, now),
        )
    project = C.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    project["checklist"] = checklist
    return project


ENTITY_TABLES = {
    "task": ("tasks", "title"),
    "data_request": ("data_requests", "title"),
    "sql_asset": ("sql_assets", "name"),
    "model": ("monitoring_models", "name"),
    "note": ("work_notes", "title"),
}


def project_relations(project_id: str) -> list[dict]:
    relations = C.fetch_all(
        "SELECT * FROM project_relations WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    for relation in relations:
        table, label_field = ENTITY_TABLES.get(relation["entity_type"], (None, None))
        entity = C.fetch_one(f"SELECT * FROM {table} WHERE id = ?", (relation["entity_id"],)) if table else None
        relation["entity_label"] = entity.get(label_field) if entity else relation["entity_id"]
        relation["entity_exists"] = bool(entity)
    return relations


@router.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict:
    project = C.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    relations = project_relations(project_id)
    direct_tasks = C.fetch_all(
        """SELECT * FROM tasks
        WHERE related_entity_type = 'project' AND related_entity_id = ?
        ORDER BY planned_date DESC, sort_order""",
        (project_id,),
    )
    related_requests = C.fetch_all(
        "SELECT * FROM data_requests WHERE related_project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    project["relation_count"] = len(relations)
    project["task_total"] = len(direct_tasks)
    project["task_done"] = sum(task["status"] == "done" for task in direct_tasks)
    project["request_total"] = len(related_requests)
    return {
        "project": project,
        "relations": relations,
        "tasks": direct_tasks,
        "requests": related_requests,
    }


@router.patch("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate) -> dict:
    return C.update_record(
        "projects",
        project_id,
        payload.model_dump(exclude_unset=True),
        "项目不存在",
    )


@router.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str) -> Response:
    return C.delete_record("projects", project_id, "项目不存在")


@router.get("/api/projects/{project_id}/relations")
def list_project_relations(project_id: str) -> dict:
    project = C.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"project": project, "relations": project_relations(project_id)}


@router.post("/api/projects/{project_id}/relations", status_code=status.HTTP_201_CREATED)
def create_project_relation(project_id: str, payload: ProjectRelationCreate) -> dict:
    relation_id = new_id("PR")
    now = utc_now()
    table, _ = ENTITY_TABLES[payload.entity_type]
    with transaction() as connection:
        if not connection.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")
        if not connection.execute(f"SELECT id FROM {table} WHERE id = ?", (payload.entity_id,)).fetchone():
            raise HTTPException(status_code=404, detail="关联对象不存在")
        try:
            connection.execute(
                """INSERT INTO project_relations
                (id,project_id,entity_type,entity_id,relation_type,note,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (relation_id, project_id, payload.entity_type, payload.entity_id, payload.relation_type, payload.note, now),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="该对象已关联到项目") from exc
            raise
    return C.fetch_one("SELECT * FROM project_relations WHERE id = ?", (relation_id,))


@router.delete("/api/projects/{project_id}/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_relation(project_id: str, relation_id: str) -> Response:
    with transaction() as connection:
        result = connection.execute(
            "DELETE FROM project_relations WHERE id = ? AND project_id = ?",
            (relation_id, project_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="项目关系不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def validate_navigation_url(url: str) -> str:
    value = url.strip()
    if not re.match(r"^(https?://|file://)", value, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="导航地址必须以 http://、https:// 或 file:// 开头")
    return value


@router.get("/api/navigation")
def list_navigation(q: str | None = None) -> list[dict]:
    if q:
        keyword = f"%{q}%"
        return C.fetch_all(
            """SELECT * FROM navigation_items
            WHERE title LIKE ? OR description LIKE ? OR category LIKE ? OR url LIKE ?
            ORDER BY category, sort_order, title""",
            (keyword, keyword, keyword, keyword),
        )
    return C.fetch_all("SELECT * FROM navigation_items ORDER BY category, sort_order, title")


@router.post("/api/navigation", status_code=status.HTTP_201_CREATED)
def create_navigation(payload: NavigationCreate) -> dict:
    item_id = new_id("NAV")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO navigation_items
            (id,title,url,description,category,icon_text,color,sort_order,show_on_home,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (item_id, payload.title, validate_navigation_url(payload.url), payload.description,
             payload.category, payload.icon_text, payload.color, payload.sort_order,
             1 if payload.show_on_home else 0, now, now),
        )
    return C.fetch_one("SELECT * FROM navigation_items WHERE id = ?", (item_id,))


@router.patch("/api/navigation/{item_id}")
def update_navigation(item_id: str, payload: NavigationUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "url" in changes:
        changes["url"] = validate_navigation_url(changes["url"])
    if "show_on_home" in changes:
        changes["show_on_home"] = 1 if changes["show_on_home"] else 0
    return C.update_record("navigation_items", item_id, changes, "导航不存在")


@router.post("/api/navigation/{item_id}/visit")
def visit_navigation(item_id: str) -> dict:
    now = utc_now()
    with transaction() as connection:
        result = connection.execute(
            """UPDATE navigation_items SET visit_count = visit_count + 1,
            last_visited_at = ?, updated_at = ? WHERE id = ?""",
            (now, now, item_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="导航不存在")
    return C.fetch_one("SELECT * FROM navigation_items WHERE id = ?", (item_id,))


@router.delete("/api/navigation/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_navigation(item_id: str) -> Response:
    return C.delete_record("navigation_items", item_id, "导航不存在")

