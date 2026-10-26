"""API routes: calendar."""
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

router = APIRouter(tags=["calendar"])

@router.get("/api/calendar/events")
def list_calendar_events(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    start = date.fromisoformat(date_from) if date_from else date.today()
    end = date.fromisoformat(date_to) if date_to else start + timedelta(days=14)
    return C.fetch_all(
        """SELECT * FROM calendar_events
        WHERE substr(start_at, 1, 10) BETWEEN ? AND ?
        ORDER BY start_at""",
        (start.isoformat(), end.isoformat()),
    )


def _subscription_config(item: dict) -> dict:
    config = item.get("config")
    if isinstance(config, dict):
        return dict(config)
    raw = item.get("config_json")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _build_caldav_config(
    *,
    existing: dict | None = None,
    caldav_url: str | None = None,
    caldav_username: str | None = None,
    caldav_password: str | None = None,
    clear_caldav_password: bool = False,
    caldav_path: str | None = None,
) -> dict:
    config = dict(existing or {})
    if caldav_url is not None:
        config["url"] = caldav_url.strip()
    if caldav_username is not None:
        config["username"] = caldav_username.strip()
    if caldav_path is not None:
        config["calendar_path"] = caldav_path.strip()
    if clear_caldav_password:
        config.pop("password_enc", None)
        config.pop("password", None)
    elif caldav_password is not None and caldav_password.strip():
        config["password_enc"] = encrypt_secret(caldav_password.strip())
        config.pop("password", None)
    return config


def _runtime_caldav_config(item: dict, settings: dict) -> dict:
    config = _subscription_config(item)
    password = decrypt_secret(config.get("password_enc") or "")
    if not password:
        password = settings.get("caldav_password") or ""
    return {
        "url": (config.get("url") or settings.get("caldav_url") or "https://calendar.dingtalk.com").strip(),
        "username": (config.get("username") or settings.get("caldav_username") or "").strip(),
        "password": password,
        "calendar_path": (config.get("calendar_path") or settings.get("caldav_path") or "").strip(),
    }


@router.get("/api/calendar/subscriptions")
def list_calendar_subscriptions() -> list[dict]:
    return [C.public_calendar_subscription(item) for item in C.fetch_all("SELECT * FROM calendar_subscriptions ORDER BY updated_at DESC")]


@router.post("/api/calendar/subscriptions", status_code=status.HTTP_201_CREATED)
def create_calendar_subscription(payload: CalendarSubscriptionCreate) -> dict:
    item_id, now = new_id("CAL"), utc_now()
    config = {}
    if payload.provider == "caldav":
        config = _build_caldav_config(
            caldav_url=payload.caldav_url or "https://calendar.dingtalk.com",
            caldav_username=payload.caldav_username,
            caldav_password=payload.caldav_password,
            caldav_path=payload.caldav_path,
        )
    with transaction() as connection:
        connection.execute(
            """INSERT INTO calendar_subscriptions
            (id,name,provider,ics_url,config_json,enabled,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                item_id,
                payload.name,
                payload.provider,
                payload.ics_url or "",
                json.dumps(config, ensure_ascii=False),
                1 if payload.enabled else 0,
                now,
                now,
            ),
        )
    item = C.fetch_one("SELECT * FROM calendar_subscriptions WHERE id = ?", (item_id,))
    return C.public_calendar_subscription(item)


@router.patch("/api/calendar/subscriptions/{subscription_id}")
def update_calendar_subscription(subscription_id: str, payload: CalendarSubscriptionUpdate) -> dict:
    item = C.fetch_one("SELECT * FROM calendar_subscriptions WHERE id = ?", (subscription_id,))
    if not item:
        raise HTTPException(status_code=404, detail="日历订阅不存在")
    changes = payload.model_dump(exclude_unset=True)
    if "enabled" in changes:
        changes["enabled"] = 1 if changes["enabled"] else 0
    config_fields = {
        "caldav_url",
        "caldav_username",
        "caldav_password",
        "clear_caldav_password",
        "caldav_path",
    }
    if any(key in changes for key in config_fields) or changes.get("provider") == "caldav":
        config = _build_caldav_config(
            existing=_subscription_config(item),
            caldav_url=changes.pop("caldav_url", None),
            caldav_username=changes.pop("caldav_username", None),
            caldav_password=changes.pop("caldav_password", None),
            clear_caldav_password=bool(changes.pop("clear_caldav_password", False)),
            caldav_path=changes.pop("caldav_path", None),
        )
        changes["config_json"] = json.dumps(config, ensure_ascii=False)
    else:
        changes.pop("caldav_url", None)
        changes.pop("caldav_username", None)
        changes.pop("caldav_password", None)
        changes.pop("clear_caldav_password", None)
        changes.pop("caldav_path", None)
    updated = C.update_record("calendar_subscriptions", subscription_id, changes, "日历订阅不存在")
    return C.public_calendar_subscription(updated)


@router.delete("/api/calendar/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_subscription(subscription_id: str) -> Response:
    return C.delete_record("calendar_subscriptions", subscription_id, "日历订阅不存在")


@router.post("/api/calendar/subscriptions/{subscription_id}/sync")
def sync_calendar_subscription(subscription_id: str) -> dict:
    item = C.fetch_one("SELECT * FROM calendar_subscriptions WHERE id = ?", (subscription_id,))
    if not item:
        raise HTTPException(status_code=404, detail="日历订阅不存在")
    settings = C.load_dingtalk_calendar_settings()
    date_from, date_to = window_for_settings(settings)
    try:
        events = sync_subscription_events(
            provider=item["provider"],
            ics_url=item.get("ics_url") or settings.get("ics_url") or "",
            dingtalk_settings=settings,
            date_from=date_from,
            date_to=date_to,
            config=_runtime_caldav_config(item, settings),
        )
    except Exception as exc:
        with transaction() as connection:
            connection.execute(
                "UPDATE calendar_subscriptions SET last_error = ?, updated_at = ? WHERE id = ?",
                (str(exc), utc_now(), subscription_id),
            )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = utc_now()
    with transaction() as connection:
        connection.execute("DELETE FROM calendar_events WHERE subscription_id = ?", (subscription_id,))
        for event in events:
            connection.execute(
                """INSERT INTO calendar_events
                (id,subscription_id,external_id,title,description,location,start_at,end_at,all_day,source,raw_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("CE"), subscription_id, event["external_id"], event["title"], event["description"],
                    event["location"], event["start_at"], event.get("end_at"), event.get("all_day", 0),
                    item["provider"], json.dumps(event.get("raw") or {}, ensure_ascii=False), now, now,
                ),
            )
        connection.execute(
            "UPDATE calendar_subscriptions SET last_synced_at = ?, last_error = '', updated_at = ? WHERE id = ?",
            (now, now, subscription_id),
        )
    return {"synced": len(events), "subscription_id": subscription_id, "from": date_from.isoformat(), "to": date_to.isoformat()}


@router.post("/api/calendar/sync")
def sync_all_calendars() -> dict:
    settings = C.load_dingtalk_calendar_settings()
    results = []
    subscriptions = C.fetch_all("SELECT * FROM calendar_subscriptions WHERE enabled = 1")
    if settings.get("enabled") and not subscriptions:
        provider = settings.get("provider") or "caldav"
        if provider == "caldav" and settings.get("caldav_username") and settings.get("caldav_password"):
            created = create_calendar_subscription(
                CalendarSubscriptionCreate(
                    name="钉钉 CalDAV",
                    provider="caldav",
                    caldav_url=settings.get("caldav_url") or "https://calendar.dingtalk.com",
                    caldav_username=settings.get("caldav_username") or "",
                    caldav_password=settings.get("caldav_password") or "",
                    caldav_path=settings.get("caldav_path") or "",
                    enabled=True,
                )
            )
            subscriptions = [C.fetch_one("SELECT * FROM calendar_subscriptions WHERE id = ?", (created["id"],))]
        elif settings.get("ics_url"):
            created = create_calendar_subscription(
                CalendarSubscriptionCreate(
                    name="钉钉/ICS 默认订阅",
                    provider="ics",
                    ics_url=settings.get("ics_url") or "",
                    enabled=True,
                )
            )
            subscriptions = [C.fetch_one("SELECT * FROM calendar_subscriptions WHERE id = ?", (created["id"],))]
    for item in subscriptions:
        results.append(sync_calendar_subscription(item["id"]))
    return {"subscriptions": len(results), "results": results}

