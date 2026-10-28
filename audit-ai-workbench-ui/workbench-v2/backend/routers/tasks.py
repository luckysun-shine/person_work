"""API routes: tasks."""
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import common as C
from ..db import new_id, row_to_dict, transaction, utc_now
from ..schemas import BatchTaskCopy, TaskCreate, TaskUpdate, WeekReviewUpsert

router = APIRouter(tags=["tasks"])

@router.get("/api/dashboard")
def dashboard() -> dict:
    today = date.today().isoformat()
    tasks = C.fetch_all(
        """SELECT * FROM tasks
        WHERE planned_date = ? OR (planned_date < ? AND status != 'done')
        ORDER BY planned_date, sort_order, due_at""",
        (today, today),
    )
    requests = C.fetch_all(
        "SELECT * FROM data_requests ORDER BY created_at DESC LIMIT 5"
    )
    projects = C.fetch_all(
        "SELECT * FROM projects WHERE status = 'active' ORDER BY progress DESC"
    )
    summary = {
        "today_total": len(tasks),
        "today_done": sum(task["status"] == "done" for task in tasks),
        "waiting_requests": sum(request["status"] == "waiting" for request in requests),
        "active_projects": len(projects),
    }
    return {"summary": summary, "tasks": tasks, "requests": requests, "projects": projects}


@router.get("/api/tasks")
def list_tasks(
    planned_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    task_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[dict]:
    conditions: list[str] = []
    parameters: list[str] = []
    if planned_date:
        conditions.append("planned_date = ?")
        parameters.append(planned_date)
    if date_from:
        conditions.append("planned_date >= ?")
        parameters.append(date_from)
    if date_to:
        conditions.append("planned_date <= ?")
        parameters.append(date_to)
    if task_status:
        conditions.append("status = ?")
        parameters.append(task_status)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return C.fetch_all(
        f"SELECT * FROM tasks{where} ORDER BY planned_date, sort_order, due_at",
        tuple(parameters),
    )


@router.get("/api/task-focus")
def task_focus(focus_date: str | None = None, bucket: str | None = None) -> dict:
    try:
        target = date.fromisoformat(focus_date) if focus_date else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="焦点日期格式不正确") from exc
    target_iso = target.isoformat()
    week_end = (target + timedelta(days=(6 - target.weekday()))).isoformat()
    later_start = (target + timedelta(days=(7 - target.weekday()))).isoformat()
    if bucket == "later":
        tasks = C.fetch_all(
            """SELECT * FROM tasks
            WHERE planned_date >= ? AND status != 'done'
            ORDER BY planned_date, sort_order, due_at""",
            (later_start,),
        )
    elif bucket == "done":
        week_start_iso = (target - timedelta(days=target.weekday())).isoformat()
        tasks = C.fetch_all(
            """SELECT * FROM tasks
            WHERE status = 'done' AND (planned_date BETWEEN ? AND ? OR substr(updated_at, 1, 10) BETWEEN ? AND ?)
            ORDER BY updated_at DESC""",
            (week_start_iso, week_end, week_start_iso, week_end),
        )
    else:
        tasks = C.fetch_all(
            """SELECT * FROM tasks
            WHERE planned_date = ?
               OR (planned_date < ? AND status != 'done')
               OR (planned_date < ? AND status = 'done' AND substr(updated_at, 1, 10) = ?)
            ORDER BY CASE WHEN planned_date < ? THEN 0 ELSE 1 END,
                     CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     due_at, sort_order""",
            (target_iso, target_iso, target_iso, target_iso, target_iso),
        )
    now = datetime.now().astimezone()
    for task in tasks:
        task["is_overdue"] = bool(task.get("planned_date")) and task["planned_date"] < target_iso and task["status"] != "done"
        task["overdue_days"] = (
            (target - date.fromisoformat(task["planned_date"])).days if task["is_overdue"] else 0
        )
        task["is_remind_due"] = bool(
            task.get("remind_at")
            and task["status"] != "done"
            and str(task["remind_at"])[:10] <= target_iso
        )
        task["is_due_soon"] = False
        due_at = task.get("due_at") or ""
        if task["status"] != "done" and task.get("planned_date") == target_iso and due_at and ":" in str(due_at):
            try:
                hour, minute = [int(part) for part in str(due_at)[:5].split(":", 1)]
                due_dt = datetime.combine(target, datetime.min.time().replace(hour=hour, minute=minute)).astimezone()
                delta_min = (due_dt - now).total_seconds() / 60
                task["is_due_soon"] = -30 <= delta_min <= 120
            except (TypeError, ValueError):
                task["is_due_soon"] = False
        task["needs_nudge"] = bool(
            task["status"] != "done"
            and (task["is_overdue"] or task["status"] == "blocked" or task.get("priority") == "high"
                 or task["is_remind_due"] or task["is_due_soon"])
        )
        task["nudge_reason"] = (
            "overdue" if task["is_overdue"]
            else "blocked" if task["status"] == "blocked"
            else "remind" if task["is_remind_due"]
            else "due_soon" if task["is_due_soon"]
            else "high" if task.get("priority") == "high"
            else None
        )
        task["bucket"] = (
            "done" if task["status"] == "done"
            else "overdue" if task["is_overdue"]
            else "today" if task.get("planned_date") == target_iso
            else "later" if task.get("planned_date") and task["planned_date"] > week_end
            else "week"
        )
    week_start = (target - timedelta(days=target.weekday())).isoformat()
    later_count = C.fetch_one(
        "SELECT COUNT(*) AS count FROM tasks WHERE planned_date >= ? AND status != 'done'",
        (later_start,),
    )["count"]
    done_count = C.fetch_one(
        """SELECT COUNT(*) AS count FROM tasks
        WHERE status = 'done' AND (planned_date BETWEEN ? AND ? OR substr(updated_at, 1, 10) BETWEEN ? AND ?)""",
        (week_start, week_end, week_start, week_end),
    )["count"]
    nudge_tasks = [task for task in tasks if task.get("needs_nudge")]
    summary = {
        "focus_date": target_iso,
        "bucket": bucket or "today",
        "total": len(tasks),
        "done": sum(task["status"] == "done" for task in tasks),
        "overdue": sum(task["is_overdue"] for task in tasks),
        "blocked": sum(task["status"] == "blocked" for task in tasks),
        "waiting": sum(task["status"] == "blocked" or bool(task.get("waiting_on")) for task in tasks),
        "high_priority": sum(task["priority"] == "high" and task["status"] != "done" for task in tasks),
        "remind_due": sum(bool(task.get("is_remind_due")) for task in tasks),
        "due_soon": sum(bool(task.get("is_due_soon")) for task in tasks),
        "nudge_count": len(nudge_tasks),
        "later_count": later_count,
        "week_done_count": done_count,
    }
    return {"summary": summary, "tasks": tasks, "nudges": nudge_tasks[:12]}


@router.get("/api/reminders")
def list_reminders(focus_date: str | None = None) -> dict:
    """今日需催办的任务：逾期、提醒日到、即将到期、受阻、高优先。"""
    focus = task_focus(focus_date=focus_date, bucket=None)
    nudges = focus.get("nudges") or []
    return {
        "focus_date": focus["summary"]["focus_date"],
        "count": len(nudges),
        "summary": {
            "overdue": focus["summary"]["overdue"],
            "remind_due": focus["summary"]["remind_due"],
            "due_soon": focus["summary"]["due_soon"],
            "blocked": focus["summary"]["blocked"],
            "high_priority": focus["summary"]["high_priority"],
        },
        "items": nudges,
    }


@router.post("/api/tasks/{task_id}/snooze-remind")
def snooze_task_remind(task_id: str, days: int = Query(default=1, ge=1, le=14)) -> dict:
    task = C.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    base = date.today()
    if task.get("remind_at"):
        try:
            base = max(base, date.fromisoformat(str(task["remind_at"])[:10]))
        except ValueError:
            pass
    next_remind = (base + timedelta(days=days)).isoformat()
    return C.update_record("tasks", task_id, {"remind_at": next_remind}, "任务不存在")


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    task = C.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def next_recurrence_date(planned_date: str | None, recurrence: str, interval: int) -> str | None:
    if not planned_date or recurrence in ("", "none", None):
        return None
    try:
        base = date.fromisoformat(planned_date)
    except ValueError:
        return None
    if recurrence == "weekly":
        return (base + timedelta(days=7)).isoformat()
    if recurrence == "monthly":
        month = base.month + 1
        year = base.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(base.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day).isoformat()
    return (base + timedelta(days=max(1, int(interval or 7)))).isoformat()


def spawn_recurring_task(connection, task: dict) -> dict | None:
    next_date = next_recurrence_date(task.get("planned_date"), task.get("recurrence") or "none", int(task.get("recurrence_interval") or 7))
    if not next_date:
        return None
    duplicate = connection.execute(
        """SELECT id FROM tasks WHERE title = ? AND planned_date = ?
           AND COALESCE(related_entity_id, '') = COALESCE(?, '') AND status != 'done'""",
        (task["title"], next_date, task.get("related_entity_id")),
    ).fetchone()
    if duplicate:
        return None
    now = utc_now()
    task_id = new_id("T")
    sort_order = connection.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM tasks WHERE planned_date IS ?",
        (next_date,),
    ).fetchone()[0]
    remind_at = None
    if task.get("remind_at") and task.get("planned_date"):
        try:
            delta = date.fromisoformat(next_date) - date.fromisoformat(task["planned_date"])
            remind_at = (date.fromisoformat(task["remind_at"][:10]) + delta).isoformat()
        except ValueError:
            remind_at = next_date
    connection.execute(
        """INSERT INTO tasks
        (id,title,status,priority,planned_date,due_at,type,related_entity_type,related_entity_id,notes,waiting_on,
         completion_result,actual_minutes,recurrence,recurrence_interval,remind_at,sort_order,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id, task["title"], "todo", task.get("priority") or "medium", next_date, task.get("due_at"),
            task.get("type") or "task", task.get("related_entity_type"), task.get("related_entity_id"),
            task.get("notes") or "", task.get("waiting_on") or "", "", 0,
            task.get("recurrence") or "none", int(task.get("recurrence_interval") or 7), remind_at,
            sort_order, now, now,
        ),
    )
    return row_to_dict(connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())


@router.post("/api/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> dict:
    now = utc_now()
    task_id = new_id("T")
    with transaction() as connection:
        sort_order = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM tasks WHERE planned_date IS ?",
            (payload.planned_date,),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO tasks
            (id,title,status,priority,planned_date,due_at,type,related_entity_type,related_entity_id,notes,waiting_on,
             completion_result,actual_minutes,recurrence,recurrence_interval,remind_at,sort_order,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id,
                payload.title,
                payload.status,
                payload.priority,
                payload.planned_date,
                payload.due_at,
                payload.type,
                payload.related_entity_type,
                payload.related_entity_id,
                payload.notes,
                payload.waiting_on,
                payload.completion_result,
                payload.actual_minutes,
                payload.recurrence,
                payload.recurrence_interval,
                payload.remind_at,
                sort_order,
                now,
                now,
            ),
        )
    return C.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate) -> dict:
    current = C.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not current:
        raise HTTPException(status_code=404, detail="任务不存在")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return current
    changes["updated_at"] = utc_now()
    spawned = None
    with transaction() as connection:
        assignments = ", ".join(f"{field} = ?" for field in changes)
        result = connection.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?",
            (*changes.values(), task_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="任务不存在")
        becoming_done = changes.get("status") == "done" and current.get("status") != "done"
        if becoming_done:
            refreshed = row_to_dict(connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
            spawned = spawn_recurring_task(connection, refreshed)
    result = C.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if spawned:
        result["spawned_next"] = spawned
    return result


@router.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str) -> Response:
    with transaction() as connection:
        result = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="任务不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def copy_task_to_next_week(connection, task: dict) -> tuple[dict | None, bool]:
    if not task.get("planned_date"):
        return None, False
    try:
        target_date = (date.fromisoformat(task["planned_date"]) + timedelta(days=7)).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="任务计划日期格式不正确") from exc
    duplicate = connection.execute(
        """SELECT * FROM tasks
        WHERE title = ? AND planned_date = ?
          AND COALESCE(related_entity_id, '') = COALESCE(?, '')""",
        (task["title"], target_date, task.get("related_entity_id")),
    ).fetchone()
    if duplicate:
        return row_to_dict(duplicate), False
    task_id = new_id("T")
    now = utc_now()
    sort_order = connection.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM tasks WHERE planned_date = ?",
        (target_date,),
    ).fetchone()[0]
    connection.execute(
        """INSERT INTO tasks
        (id,title,status,priority,planned_date,due_at,type,related_entity_type,related_entity_id,notes,sort_order,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id, task["title"], "todo", task["priority"], target_date,
            task["due_at"], task["type"], task["related_entity_type"],
            task["related_entity_id"], task["notes"], sort_order, now, now,
        ),
    )
    return row_to_dict(connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()), True


@router.post("/api/tasks/{task_id}/copy-next-week", status_code=status.HTTP_201_CREATED)
def copy_task(task_id: str) -> dict:
    with transaction() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="任务不存在")
        copied, created = copy_task_to_next_week(connection, row_to_dict(row))
        if not copied:
            raise HTTPException(status_code=400, detail="未排期任务不能复制到下周")
    return {"task": copied, "created": created}


@router.post("/api/tasks/batch-copy-next-week")
def batch_copy_tasks(payload: BatchTaskCopy) -> dict:
    copied: list[dict] = []
    skipped = 0
    with transaction() as connection:
        for task_id in payload.ids:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                skipped += 1
                continue
            task, created = copy_task_to_next_week(connection, row_to_dict(row))
            if task and created:
                copied.append(task)
            else:
                skipped += 1
    return {"copied": copied, "copied_count": len(copied), "skipped_count": skipped}


@router.get("/api/week-reviews/{week_start}")
def get_week_review(week_start: str) -> dict:
    try:
        date.fromisoformat(week_start)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="周开始日期格式不正确") from exc
    review = C.fetch_one("SELECT * FROM week_reviews WHERE week_start = ?", (week_start,))
    return review or {
        "id": None,
        "week_start": week_start,
        "accomplishments": "",
        "blockers": "",
        "next_week_focus": "",
        "energy_score": 3,
        "created_at": None,
        "updated_at": None,
    }


@router.put("/api/week-reviews/{week_start}")
def save_week_review(week_start: str, payload: WeekReviewUpsert) -> dict:
    try:
        date.fromisoformat(week_start)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="周开始日期格式不正确") from exc
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO week_reviews
            (id,week_start,accomplishments,blockers,next_week_focus,energy_score,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(week_start) DO UPDATE SET
              accomplishments=excluded.accomplishments,
              blockers=excluded.blockers,
              next_week_focus=excluded.next_week_focus,
              energy_score=excluded.energy_score,
              updated_at=excluded.updated_at""",
            (
                new_id("WR"), week_start, payload.accomplishments, payload.blockers,
                payload.next_week_focus, payload.energy_score, now, now,
            ),
        )
    return C.fetch_one("SELECT * FROM week_reviews WHERE week_start = ?", (week_start,))

