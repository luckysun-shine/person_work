"""API routes: projects."""
import json
import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import common as C
from ..db import new_id, transaction, utc_now
from ..schemas import (
    NavigationCreate,
    NavigationUpdate,
    ProjectCreate,
    ProjectExecutionCreate,
    ProjectExecutionUpdate,
    ProjectRelationCreate,
    ProjectStepCreate,
    ProjectStepUpdate,
    ProjectTemplateCreate,
    ProjectTemplateUpdate,
    ProjectUpdate,
)

router = APIRouter(tags=["projects"])

def _linked_models_for_project(project_id: str) -> list[dict]:
    return C.fetch_all(
        """SELECT m.id, m.name, m.status, m.current_version, m.schedule,
                  m.last_run_at, m.hit_count, m.pending_review_count, m.purpose
        FROM project_relations r
        INNER JOIN monitoring_models m ON m.id = r.entity_id
        WHERE r.project_id = ? AND r.entity_type = 'model'
        ORDER BY m.updated_at DESC""",
        (project_id,),
    )


def _model_attention_count(models: list[dict]) -> int:
    return sum(
        1
        for model in models
        if model.get("status") == "update_due" or int(model.get("pending_review_count") or 0) > 0
    )


def _attach_ledger_summary(items: list[dict]) -> list[dict]:
    if not items:
        return items
    ids = [item["id"] for item in items]
    placeholders = ",".join("?" for _ in ids)
    latest_rows = C.fetch_all(
        f"""SELECT project_id, executed_at, result, summary FROM (
            SELECT project_id, executed_at, result, summary,
                   ROW_NUMBER() OVER (
                       PARTITION BY project_id ORDER BY executed_at DESC, created_at DESC
                   ) AS rn
            FROM project_executions WHERE project_id IN ({placeholders})
        ) WHERE rn = 1""",
        tuple(ids),
    )
    latest_map = {row.pop("project_id"): row for row in latest_rows}
    pending_rows = C.fetch_all(
        f"""SELECT project_id, COUNT(*) AS c FROM project_update_steps
        WHERE project_id IN ({placeholders}) AND status != 'done'
        GROUP BY project_id""",
        tuple(ids),
    )
    pending_map = {row["project_id"]: int(row["c"] or 0) for row in pending_rows}
    model_rows = C.fetch_all(
        f"""SELECT r.project_id, m.id, m.name, m.status, m.current_version, m.schedule,
                  m.last_run_at, m.hit_count, m.pending_review_count, m.purpose
        FROM project_relations r
        INNER JOIN monitoring_models m ON m.id = r.entity_id
        WHERE r.entity_type = 'model' AND r.project_id IN ({placeholders})
        ORDER BY m.updated_at DESC""",
        tuple(ids),
    )
    models_map: dict[str, list[dict]] = {}
    for row in model_rows:
        models_map.setdefault(row.pop("project_id"), []).append(row)
    for item in items:
        models = models_map.get(item["id"], [])
        item["latest_execution"] = latest_map.get(item["id"])
        item["pending_steps"] = pending_map.get(item["id"], 0)
        item["relation_count"] = int(item.get("relation_count") or 0)
        item["linked_models"] = models
        item["model_count"] = len(models)
        item["model_attention"] = _model_attention_count(models)
    return items


@router.get("/api/projects")
def list_projects(
    category: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    ledger_only: Annotated[bool, Query()] = True,
) -> list[dict]:
    clauses: list[str] = []
    params: list[str] = []
    if ledger_only and not category:
        clauses.append("p.category IN ('员工监管类','经销商监管类','合作商监管类','AI助力管理类')")
    if category:
        clauses.append("p.category = ?")
        params.append(category)
    if q:
        clauses.append(
            "(p.name LIKE ? OR p.goal LIKE ? OR p.plan_detail LIKE ? OR p.monitor_logic LIKE ? "
            "OR p.next_action LIKE ? OR p.category LIKE ?)"
        )
        keyword = f"%{q}%"
        params.extend([keyword] * 6)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    items = C.fetch_all(
        f"""SELECT p.*, COUNT(r.id) AS relation_count
        FROM projects p
        LEFT JOIN project_relations r ON r.project_id = p.id
        {where}
        GROUP BY p.id
        ORDER BY
          CASE p.category
            WHEN '员工监管类' THEN 1
            WHEN '经销商监管类' THEN 2
            WHEN '合作商监管类' THEN 3
            WHEN 'AI助力管理类' THEN 4
            ELSE 9 END,
          p.sort_order, p.name""",
        tuple(params),
    )
    return _attach_ledger_summary(items)


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
    project_id = new_id("ML")
    now = utc_now()
    name = payload.name
    project_type = payload.type or "monitor"
    goal = payload.goal
    next_action = payload.next_action
    checklist: list[str] = []
    if payload.template_id:
        template = C.fetch_one("SELECT * FROM project_templates WHERE id = ?", (payload.template_id,))
        if not template:
            raise HTTPException(status_code=404, detail="项目模板不存在")
        project_type = project_type or template.get("project_type") or "monitor"
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
            (id,name,type,goal,status,progress,due_date,next_action,
             category,sort_order,monitor_cycle,cycle_note,plan_detail,monitor_logic,
             code_backup,code_note,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                project_id, name, project_type, goal, payload.status, payload.progress,
                payload.due_date, next_action, payload.category, payload.sort_order,
                payload.monitor_cycle, payload.cycle_note, payload.plan_detail,
                payload.monitor_logic, payload.code_backup, payload.code_note, now, now,
            ),
        )
    project = C.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    project["checklist"] = checklist
    project["latest_execution"] = None
    project["pending_steps"] = 0
    project["relation_count"] = 0
    project["linked_models"] = []
    project["model_count"] = 0
    project["model_attention"] = 0
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
    steps = C.fetch_all(
        """SELECT * FROM project_update_steps
        WHERE project_id = ? ORDER BY sort_order, created_at""",
        (project_id,),
    )
    executions = C.fetch_all(
        """SELECT * FROM project_executions
        WHERE project_id = ? ORDER BY executed_at DESC, created_at DESC""",
        (project_id,),
    )
    linked_models = _linked_models_for_project(project_id)
    project["relation_count"] = len(relations)
    project["task_total"] = len(direct_tasks)
    project["task_done"] = sum(task["status"] == "done" for task in direct_tasks)
    project["request_total"] = len(related_requests)
    project["pending_steps"] = sum(1 for step in steps if step.get("status") != "done")
    project["latest_execution"] = executions[0] if executions else None
    project["linked_models"] = linked_models
    project["model_count"] = len(linked_models)
    project["model_attention"] = _model_attention_count(linked_models)
    return {
        "project": project,
        "relations": relations,
        "tasks": direct_tasks,
        "requests": related_requests,
        "update_steps": steps,
        "executions": executions,
        "models": linked_models,
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
    now = utc_now()
    with transaction() as connection:
        result = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="项目不存在")
        # 步骤/执行/关系由外键级联删除；这里清理其它表上指向该台账的软引用，避免悬空编号。
        for table in ("sql_assets", "data_requests", "stored_procedures"):
            connection.execute(
                f"UPDATE {table} SET related_project_id = NULL, updated_at = ? WHERE related_project_id = ?",
                (now, project_id),
            )
        for table in ("tasks", "work_notes"):
            connection.execute(
                f"""UPDATE {table} SET related_entity_type = NULL, related_entity_id = NULL, updated_at = ?
                WHERE related_entity_type = 'project' AND related_entity_id = ?""",
                (now, project_id),
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


def _require_project(project_id: str) -> dict:
    project = C.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="台账条目不存在")
    return project


@router.get("/api/projects/{project_id}/steps")
def list_project_steps(project_id: str) -> list[dict]:
    _require_project(project_id)
    return C.fetch_all(
        """SELECT * FROM project_update_steps
        WHERE project_id = ? ORDER BY sort_order, created_at""",
        (project_id,),
    )


@router.post("/api/projects/{project_id}/steps", status_code=status.HTTP_201_CREATED)
def create_project_step(project_id: str, payload: ProjectStepCreate) -> dict:
    _require_project(project_id)
    step_id, now = new_id("PS"), utc_now()
    done_at = now if payload.status == "done" else None
    with transaction() as connection:
        connection.execute(
            """INSERT INTO project_update_steps
            (id,project_id,title,detail,status,sort_order,done_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                step_id, project_id, payload.title, payload.detail, payload.status,
                payload.sort_order, done_at, now, now,
            ),
        )
    return C.fetch_one("SELECT * FROM project_update_steps WHERE id = ?", (step_id,))


@router.patch("/api/projects/{project_id}/steps/{step_id}")
def update_project_step(project_id: str, step_id: str, payload: ProjectStepUpdate) -> dict:
    _require_project(project_id)
    item = C.fetch_one(
        "SELECT * FROM project_update_steps WHERE id = ? AND project_id = ?",
        (step_id, project_id),
    )
    if not item:
        raise HTTPException(status_code=404, detail="更新步骤不存在")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == "done" and item.get("status") != "done":
        changes["done_at"] = utc_now()
    elif changes.get("status") == "pending":
        changes["done_at"] = None
    return C.update_record("project_update_steps", step_id, changes, "更新步骤不存在")


@router.delete("/api/projects/{project_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_step(project_id: str, step_id: str) -> Response:
    with transaction() as connection:
        result = connection.execute(
            "DELETE FROM project_update_steps WHERE id = ? AND project_id = ?",
            (step_id, project_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="更新步骤不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/projects/{project_id}/executions")
def list_project_executions(project_id: str) -> list[dict]:
    _require_project(project_id)
    return C.fetch_all(
        """SELECT * FROM project_executions
        WHERE project_id = ? ORDER BY executed_at DESC, created_at DESC""",
        (project_id,),
    )


@router.post("/api/projects/{project_id}/executions", status_code=status.HTTP_201_CREATED)
def create_project_execution(project_id: str, payload: ProjectExecutionCreate) -> dict:
    _require_project(project_id)
    exec_id, now = new_id("PE"), utc_now()
    executed_at = payload.executed_at or now
    with transaction() as connection:
        connection.execute(
            """INSERT INTO project_executions
            (id,project_id,executed_at,result,summary,evidence_note,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                exec_id, project_id, executed_at, payload.result,
                payload.summary, payload.evidence_note, now, now,
            ),
        )
        connection.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (now, project_id),
        )
    return C.fetch_one("SELECT * FROM project_executions WHERE id = ?", (exec_id,))


@router.patch("/api/projects/{project_id}/executions/{execution_id}")
def update_project_execution(project_id: str, execution_id: str, payload: ProjectExecutionUpdate) -> dict:
    _require_project(project_id)
    item = C.fetch_one(
        "SELECT * FROM project_executions WHERE id = ? AND project_id = ?",
        (execution_id, project_id),
    )
    if not item:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return C.update_record(
        "project_executions",
        execution_id,
        payload.model_dump(exclude_unset=True),
        "执行记录不存在",
    )


@router.delete("/api/projects/{project_id}/executions/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_execution(project_id: str, execution_id: str) -> Response:
    with transaction() as connection:
        result = connection.execute(
            "DELETE FROM project_executions WHERE id = ? AND project_id = ?",
            (execution_id, project_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="执行记录不存在")
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

