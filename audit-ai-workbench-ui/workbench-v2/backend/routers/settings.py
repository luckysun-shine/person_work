"""API routes: settings."""
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

router = APIRouter(tags=["settings"])

HOME_LAYOUT_DEFAULT = ["tasks", "projects", "requests", "quick"]
HOME_LAYOUT_ALLOWED = set(HOME_LAYOUT_DEFAULT)


def normalize_home_layout(value) -> list[str]:
    if not isinstance(value, list):
        return list(HOME_LAYOUT_DEFAULT)
    ordered = [str(item) for item in value if str(item) in HOME_LAYOUT_ALLOWED]
    for key in HOME_LAYOUT_DEFAULT:
        if key not in ordered:
            ordered.append(key)
    return ordered[: len(HOME_LAYOUT_DEFAULT)]


@router.get("/api/settings")
def get_settings() -> dict:
    backups = sorted(C.backup_directory().glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    latest = C.backup_info(backups[0]) if backups else None
    return {
        "backup_retention": int(C.get_setting("backup_retention", 20) or 20),
        "auto_backup_hours": int(C.get_setting("auto_backup_hours", 0) or 0),
        "last_auto_backup_at": C.get_setting("last_auto_backup_at", "") or "",
        "home_layout": normalize_home_layout(C.get_setting("home_layout", HOME_LAYOUT_DEFAULT)),
        "version": C.APP_VERSION,
        "ai": C.public_ai_settings(),
        "dingtalk_calendar": C.public_dingtalk_calendar_settings(),
        "access_password_enabled": C.access_password_required(),
        "secret_warning": C.secret_warning(),
        "session_days": C.ACCESS_SESSION_SECONDS // 86400,
        "backups": {
            "count": len(backups),
            "latest": latest,
            "retention": int(C.get_setting("backup_retention", 20) or 20),
        },
    }


@router.put("/api/settings")
def update_settings(payload: SettingsUpdate) -> dict:
    if payload.backup_retention is not None:
        C.set_setting("backup_retention", payload.backup_retention)
        C.prune_backups(payload.backup_retention)
    if payload.auto_backup_hours is not None:
        C.set_setting("auto_backup_hours", payload.auto_backup_hours)
    if payload.home_layout is not None:
        C.set_setting("home_layout", normalize_home_layout(payload.home_layout))
    if payload.ai is not None:
        current = C.load_ai_settings()
        updates = payload.ai.model_dump(exclude_unset=True)
        if updates.pop("clear_api_key", False):
            current["api_key"] = ""
        if "api_key" in updates:
            key = updates.pop("api_key") or ""
            current["api_key"] = key
        current.update({k: v for k, v in updates.items() if v is not None})
        stored = dict(current)
        stored["api_key"] = encrypt_secret(current.get("api_key") or "")
        C.set_setting("ai", stored)
    if payload.dingtalk_calendar is not None:
        current = C.load_dingtalk_calendar_settings()
        updates = payload.dingtalk_calendar.model_dump(exclude_unset=True)
        if updates.pop("clear_app_secret", False):
            current["app_secret"] = ""
        if "app_secret" in updates:
            secret = updates.pop("app_secret") or ""
            current["app_secret"] = secret
        if updates.pop("clear_caldav_password", False):
            current["caldav_password"] = ""
        if "caldav_password" in updates:
            secret = updates.pop("caldav_password") or ""
            if secret.strip():
                current["caldav_password"] = secret
        current.update({k: v for k, v in updates.items() if v is not None})
        stored = dict(current)
        stored["app_secret"] = encrypt_secret(current.get("app_secret") or "")
        stored["caldav_password"] = encrypt_secret(current.get("caldav_password") or "")
        C.set_setting("dingtalk_calendar", stored)
    if payload.clear_access_password:
        C.set_setting("access_password_hash", "")
        C.bump_access_token_version()
    elif payload.access_password is not None:
        if not payload.access_password.strip():
            C.set_setting("access_password_hash", "")
            C.bump_access_token_version()
        else:
            password = payload.access_password.strip()
            if len(password) < 6:
                raise HTTPException(status_code=400, detail="访问密码至少 6 位")
            C.set_setting("access_password_hash", C.hash_password(password))
            C.bump_access_token_version()
    return get_settings()


@router.get("/api/stats")
def workbench_stats(period: str = Query(default="week")) -> dict:
    today = date.today()
    if period == "month":
        start = today.replace(day=1)
        end = today
    elif period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, quarter_month, 1)
        end = today
    else:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        period = "week"
    start_iso, end_iso = start.isoformat(), end.isoformat()
    tasks = C.fetch_all("SELECT * FROM tasks")
    completed = [
        task for task in tasks
        if task.get("status") == "done"
        and (
            (task.get("planned_date") and start_iso <= task["planned_date"] <= end_iso)
            or (task.get("updated_at") and start_iso <= task["updated_at"][:10] <= end_iso)
        )
    ]
    overdue = [
        task for task in tasks
        if task.get("status") != "done" and task.get("planned_date") and task["planned_date"] < today.isoformat()
    ]
    created = [
        task for task in tasks
        if task.get("created_at") and start_iso <= task["created_at"][:10] <= end_iso
    ]
    minutes_total = sum(int(task.get("actual_minutes") or 0) for task in completed)
    by_type: dict[str, dict] = {}
    for task in completed:
        key = task.get("type") or "task"
        bucket = by_type.setdefault(key, {"type": key, "count": 0, "minutes": 0})
        bucket["count"] += 1
        bucket["minutes"] += int(task.get("actual_minutes") or 0)
    requests = C.fetch_all("SELECT * FROM data_requests")
    period_requests = [
        item for item in requests
        if item.get("created_at") and start_iso <= item["created_at"][:10] <= end_iso
    ]
    delivered = [item for item in period_requests if item.get("status") == "done"]
    on_time = 0
    for item in delivered:
        due = (item.get("due_at") or "")[:10]
        done_day = (item.get("updated_at") or "")[:10]
        if due and done_day and done_day <= due:
            on_time += 1
        elif not due:
            on_time += 1
    themes: dict[str, int] = {}
    for item in period_requests:
        theme = (item.get("purpose") or item.get("title") or "未分类").strip() or "未分类"
        themes[theme] = themes.get(theme, 0) + 1
    top_themes = sorted(({"theme": k, "count": v} for k, v in themes.items()), key=lambda x: x["count"], reverse=True)[:8]
    return {
        "period": {"name": period, "start": start_iso, "end": end_iso},
        "tasks": {
            "completed": len(completed),
            "overdue": len(overdue),
            "created": len(created),
            "minutes_total": minutes_total,
            "by_type": sorted(by_type.values(), key=lambda item: item["minutes"], reverse=True),
            "drilldown": {
                "completed": completed[:50],
                "overdue": overdue[:50],
                "created": created[:50],
            },
        },
        "requests": {
            "total": len(period_requests),
            "delivered": len(delivered),
            "on_time_rate": round(on_time / len(delivered), 3) if delivered else None,
            "top_themes": top_themes,
            "items": period_requests[:50],
        },
    }

