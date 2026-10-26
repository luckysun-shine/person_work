"""API routes: frontend."""
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

router = APIRouter(tags=["frontend"])

@router.get("/styles.css", include_in_schema=False)
def styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "styles.css", media_type="text/css")


@router.get("/ui-apple-hig.css", include_in_schema=False)
def apple_hig_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "ui-apple-hig.css", media_type="text/css")


@router.get("/ui-soft-welcome.css", include_in_schema=False)
def soft_welcome_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "ui-soft-welcome.css", media_type="text/css")


@router.get("/app.js", include_in_schema=False)
def javascript() -> FileResponse:
    return FileResponse(PROJECT_DIR / "app.js", media_type="application/javascript")


@router.get("/prototype-apple-hig.css", include_in_schema=False)
def apple_hig_prototype_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "prototype-apple-hig.css", media_type="text/css")


@router.get("/prototype-apple-hig.js", include_in_schema=False)
def apple_hig_prototype_javascript() -> FileResponse:
    return FileResponse(PROJECT_DIR / "prototype-apple-hig.js", media_type="application/javascript")


@router.get("/prototype/apple-hig", include_in_schema=False)
def apple_hig_prototype() -> FileResponse:
    return FileResponse(PROJECT_DIR / "prototype-apple-hig.html")


@router.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(PROJECT_DIR / "index.html")


@router.get("/{path:path}", include_in_schema=False)
def frontend_fallback(path: str) -> FileResponse:
    if Path(path).suffix:
        raise HTTPException(status_code=404, detail="资源不存在")
