"""API routes: requests."""
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

router = APIRouter(tags=["requests"])

@router.get("/api/data-requests")
def list_data_requests(
    q: str | None = None,
    requester: str | None = None,
    department: str | None = None,
    request_status: str | None = Query(default=None, alias="status"),
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    conditions: list[str] = []
    parameters: list = []
    if q:
        keyword = f"%{q}%"
        conditions.append("(title LIKE ? OR purpose LIKE ? OR scope LIKE ? OR requester LIKE ? OR department LIKE ? OR sensitive_notes LIKE ?)")
        parameters.extend([keyword, keyword, keyword, keyword, keyword, keyword])
    if requester:
        conditions.append("requester LIKE ?")
        parameters.append(f"%{requester}%")
    if department:
        conditions.append("department LIKE ?")
        parameters.append(f"%{department}%")
    if request_status:
        conditions.append("status = ?")
        parameters.append(request_status)
    if date_from:
        conditions.append("substr(created_at, 1, 10) >= ?")
        parameters.append(date_from)
    if date_to:
        conditions.append("substr(created_at, 1, 10) <= ?")
        parameters.append(date_to)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return C.fetch_all(
        f"SELECT * FROM data_requests{where} ORDER BY created_at DESC",
        tuple(parameters),
    )


@router.post("/api/data-requests", status_code=status.HTTP_201_CREATED)
def create_data_request(payload: DataRequestCreate) -> dict:
    request_id = new_id("DR")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO data_requests
            (id,title,purpose,scope,caliber_notes,due_at,status,next_action,related_sql_ids_json,related_project_id,
             requester,department,waiting_on,delivery_method,delivery_location,sensitive_notes,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request_id,
                payload.title,
                payload.purpose,
                payload.scope,
                payload.caliber_notes,
                payload.due_at,
                payload.status,
                payload.next_action,
                json.dumps(payload.related_sql_ids, ensure_ascii=False),
                payload.related_project_id,
                payload.requester,
                payload.department,
                payload.waiting_on,
                payload.delivery_method,
                payload.delivery_location,
                payload.sensitive_notes,
                now,
                now,
            ),
        )
    return C.fetch_one("SELECT * FROM data_requests WHERE id = ?", (request_id,))


@router.post("/api/data-requests/batch-delete")
def batch_delete_data_requests(payload: BatchIds) -> dict:
    return C.batch_delete_records("data_requests", payload.ids)


@router.post("/api/data-requests/batch-status")
def batch_update_data_request_status(payload: BatchRequestStatus) -> dict:
    return C.batch_update_status("data_requests", payload.ids, payload.status)


@router.get("/api/data-requests/{request_id}")
def get_data_request(request_id: str) -> dict:
    request = C.fetch_one("SELECT * FROM data_requests WHERE id = ?", (request_id,))
    if not request:
        raise HTTPException(status_code=404, detail="数据请求不存在")
    return request


@router.patch("/api/data-requests/{request_id}")
def update_data_request(request_id: str, payload: DataRequestUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "related_sql_ids" in changes:
        changes["related_sql_ids_json"] = json.dumps(
            changes.pop("related_sql_ids"), ensure_ascii=False
        )
    return C.update_record("data_requests", request_id, changes, "数据请求不存在")


@router.delete("/api/data-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_request(request_id: str) -> Response:
    return C.delete_record("data_requests", request_id, "数据请求不存在")

