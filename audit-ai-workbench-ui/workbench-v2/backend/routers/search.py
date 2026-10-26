"""API routes: search."""
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

router = APIRouter(tags=["search"])

SEARCH_ENTITIES = {
    "task": ("tasks", "title", ["title", "notes", "related_entity_id"], "week"),
    "data_request": ("data_requests", "title", ["title", "purpose", "scope", "caliber_notes", "sql_text"], "requests"),
    "sql_asset": ("sql_assets", "name", ["name", "purpose", "sql_text", "tags_json", "table_names_json"], "sql"),
    "model": ("monitoring_models", "name", ["name", "purpose", "rule_definitions_json"], "models"),
    "project": ("projects", "name", ["name", "goal", "next_action"], "projects"),
    "note": ("work_notes", "title", ["title", "content", "tags_json"], "notes"),
    "procedure": ("stored_procedures", "name", ["name", "database_name", "schema_name", "purpose", "definition_text", "tags_json"], "procedures"),
    "generated_report": ("generated_reports", "title", ["title", "sections_json"], "reports"),
}


def record_recent_search(query: str, types: str | None, result_count: int) -> None:
    now = utc_now()
    with transaction() as connection:
        connection.execute("DELETE FROM recent_searches WHERE query = ? AND types = ?", (query, types or ""))
        connection.execute(
            """INSERT INTO recent_searches (id, query, types, result_count, searched_at)
            VALUES (?, ?, ?, ?, ?)""",
            (new_id("RS"), query, types or "", result_count, now),
        )
        stale = connection.execute(
            "SELECT id FROM recent_searches ORDER BY searched_at DESC LIMIT -1 OFFSET 20"
        ).fetchall()
        if stale:
            connection.execute(
                f"DELETE FROM recent_searches WHERE id IN ({','.join('?' for _ in stale)})",
                tuple(row["id"] for row in stale),
            )


@router.get("/api/search")
def unified_search(q: str = Query(min_length=1, max_length=100), types: str | None = None) -> dict:
    requested = set(types.split(",")) if types else set(SEARCH_ENTITIES)
    keyword = f"%{q.strip()}%"
    results: list[dict] = []
    for entity_type, (table, title_field, fields, view) in SEARCH_ENTITIES.items():
        if entity_type not in requested:
            continue
        conditions = " OR ".join(["id LIKE ?", *(f"{field} LIKE ?" for field in fields)])
        rows = C.fetch_all(
            f"SELECT * FROM {table} WHERE {conditions} ORDER BY updated_at DESC LIMIT 20",
            tuple(keyword for _ in range(len(fields) + 1)),
        )
        for row in rows:
            subtitle = {
                "task": row.get("notes") or row.get("planned_date"),
                "data_request": row.get("purpose") or row.get("next_action"),
                "sql_asset": row.get("purpose") or row.get("current_version"),
                "model": row.get("purpose") or row.get("current_version"),
                "project": row.get("goal") or row.get("next_action"),
                "note": row.get("content"),
                "procedure": row.get("purpose") or row.get("current_version"),
                "generated_report": (row.get("sections") or {}).get("summary") or row.get("period_start"),
            }[entity_type]
            results.append({
                "entity_type": entity_type,
                "id": row["id"],
                "title": row[title_field],
                "subtitle": (subtitle or "")[:180],
                "view": view,
                "updated_at": row.get("updated_at") or row.get("created_at"),
            })
    results.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    limited = results[:100]
    counts = {entity_type: sum(item["entity_type"] == entity_type for item in limited) for entity_type in SEARCH_ENTITIES}
    record_recent_search(q.strip(), types, len(limited))
    return {"query": q.strip(), "total": len(limited), "counts": counts, "results": limited}


@router.get("/api/recent-searches")
def list_recent_searches() -> list[dict]:
    return C.fetch_all("SELECT * FROM recent_searches ORDER BY searched_at DESC LIMIT 20")


@router.delete("/api/recent-searches", status_code=status.HTTP_204_NO_CONTENT)
def clear_recent_searches() -> Response:
    with transaction() as connection:
        connection.execute("DELETE FROM recent_searches")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/saved-searches")
def list_saved_searches() -> list[dict]:
    return C.fetch_all("SELECT * FROM saved_searches ORDER BY updated_at DESC")


@router.post("/api/saved-searches", status_code=status.HTTP_201_CREATED)
def create_saved_search(payload: SavedSearchCreate) -> dict:
    search_id, now = new_id("SS"), utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO saved_searches (id, name, query, types, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (search_id, payload.name, payload.query, payload.types, now, now),
        )
    return C.fetch_one("SELECT * FROM saved_searches WHERE id = ?", (search_id,))


@router.patch("/api/saved-searches/{search_id}")
def update_saved_search(search_id: str, payload: SavedSearchUpdate) -> dict:
    return C.update_record("saved_searches", search_id, payload.model_dump(exclude_unset=True), "保存的检索不存在")


@router.delete("/api/saved-searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(search_id: str) -> Response:
    return C.delete_record("saved_searches", search_id, "保存的检索不存在")

