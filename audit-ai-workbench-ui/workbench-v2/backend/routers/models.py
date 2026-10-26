"""API routes: models."""
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

router = APIRouter(tags=["models"])

@router.get("/api/models")
def list_models() -> list[dict]:
    return C.fetch_all("SELECT * FROM monitoring_models ORDER BY updated_at DESC")


@router.post("/api/models", status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelCreate) -> dict:
    model_id = new_id("M")
    now = utc_now()
    values = payload.model_dump()
    change_summary = values.pop("change_summary")
    for field in ("rule_definitions", "dependency_ids", "related_sql_ids", "update_steps"):
        values[f"{field}_json"] = json.dumps(values.pop(field), ensure_ascii=False)
    with transaction() as connection:
        connection.execute(
            """INSERT INTO monitoring_models
            (id,name,purpose,status,schedule,current_version,rule_definitions_json,dependency_ids_json,
             related_sql_ids_json,update_steps_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (model_id, values["name"], values["purpose"], values["status"], values["schedule"],
             values["current_version"], values["rule_definitions_json"], values["dependency_ids_json"],
             values["related_sql_ids_json"], values["update_steps_json"], now, now),
        )
        connection.execute(
            "INSERT INTO model_versions (id,model_id,version,change_summary,created_at) VALUES (?,?,?,?,?)",
            (new_id("MV"), model_id, values["current_version"], change_summary, now),
        )
    return C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (model_id,))


@router.get("/api/models/{model_id}")
def get_model(model_id: str) -> dict:
    model = C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (model_id,))
    if not model:
        raise HTTPException(status_code=404, detail="监测模型不存在")
    model["versions"] = C.fetch_all(
        "SELECT * FROM model_versions WHERE model_id = ? ORDER BY created_at DESC, rowid DESC", (model_id,)
    )
    return model


@router.patch("/api/models/{model_id}")
def update_model(model_id: str, payload: ModelUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    change_summary = changes.pop("change_summary", None)
    for field in ("rule_definitions", "dependency_ids", "related_sql_ids", "update_steps"):
        if field in changes:
            changes[f"{field}_json"] = json.dumps(changes.pop(field), ensure_ascii=False)
    previous = C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (model_id,))
    if not previous:
        raise HTTPException(status_code=404, detail="监测模型不存在")
    if "current_version" in changes and changes["current_version"] != previous["current_version"]:
        if C.fetch_one("SELECT id FROM model_versions WHERE model_id = ? AND version = ?", (model_id, changes["current_version"])):
            raise HTTPException(status_code=409, detail="该模型版本已经存在")
    model = C.update_record("monitoring_models", model_id, changes, "监测模型不存在")
    if "current_version" in changes and changes["current_version"] != previous["current_version"]:
        with transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO model_versions (id,model_id,version,change_summary,created_at) VALUES (?,?,?,?,?)",
                    (new_id("MV"), model_id, model["current_version"], change_summary or "更新模型版本", utc_now()),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="该模型版本已经存在") from exc
    return model


@router.delete("/api/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: str) -> Response:
    with transaction() as connection:
        connection.execute(
            "DELETE FROM project_relations WHERE entity_type = 'model' AND entity_id = ?", (model_id,)
        )
        result = connection.execute("DELETE FROM monitoring_models WHERE id = ?", (model_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="监测模型不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/models/{model_id}/runs")
def list_model_runs(model_id: str) -> list[dict]:
    if not C.fetch_one("SELECT id FROM monitoring_models WHERE id = ?", (model_id,)):
        raise HTTPException(status_code=404, detail="监测模型不存在")
    return C.fetch_all(
        "SELECT * FROM model_runs WHERE model_id = ? ORDER BY started_at DESC",
        (model_id,),
    )


@router.post("/api/models/{model_id}/runs", status_code=status.HTTP_201_CREATED)
def create_model_run(model_id: str, payload: ModelRunCreate) -> dict:
    run_id = new_id("MR")
    now = utc_now()
    with transaction() as connection:
        if not connection.execute("SELECT id FROM monitoring_models WHERE id = ?", (model_id,)).fetchone():
            raise HTTPException(status_code=404, detail="监测模型不存在")
        connection.execute(
            """INSERT INTO model_runs
            (id,model_id,started_at,finished_at,status,scanned_count,hit_count,reviewed_count,result_summary,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, model_id, payload.started_at, payload.finished_at, payload.status,
                payload.scanned_count, payload.hit_count, payload.reviewed_count,
                payload.result_summary, now,
            ),
        )
        connection.execute(
            """UPDATE monitoring_models SET last_run_at = ?, hit_count = ?,
            pending_review_count = ?, updated_at = ? WHERE id = ?""",
            (
                payload.finished_at or payload.started_at,
                payload.hit_count,
                max(payload.hit_count - payload.reviewed_count, 0),
                now,
                model_id,
            ),
        )
    return C.fetch_one("SELECT * FROM model_runs WHERE id = ?", (run_id,))
