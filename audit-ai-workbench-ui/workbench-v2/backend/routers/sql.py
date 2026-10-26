"""API routes: sql."""
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
    ai_ready,
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

router = APIRouter(tags=["sql"])

@router.get("/api/sql-assets")
def list_sql_assets(q: str | None = None, asset_status: str | None = Query(default=None, alias="status")) -> list[dict]:
    conditions: list[str] = []
    parameters: list[str] = []
    if q:
        conditions.append("(name LIKE ? OR purpose LIKE ? OR tags_json LIKE ? OR table_names_json LIKE ?)")
        keyword = f"%{q}%"
        parameters.extend([keyword, keyword, keyword, keyword])
    if asset_status:
        conditions.append("status = ?")
        parameters.append(asset_status)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return C.fetch_all(
        f"SELECT id,name,purpose,sql_text,current_version,status,tags_json,table_names_json,related_project_id,reuse_count,validation_note,created_at,updated_at FROM sql_assets{where} ORDER BY updated_at DESC",
        tuple(parameters),
    )


@router.post("/api/sql-assets/assist")
def assist_sql(payload: SqlAssistRequest) -> dict:
    sql_text = payload.sql_text.strip()
    cleaned = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql_text, flags=re.DOTALL)
    normalized = re.sub(r"\s+", " ", cleaned).strip()
    table_matches = re.findall(
        r"\b(?:from|join|update|into)\s+([`\"\[\]A-Za-z0-9_.$]+)",
        normalized,
        flags=re.IGNORECASE,
    )
    tables: list[str] = []
    for value in table_matches:
        table = value.strip("`\"[]")
        if table and table.lower() not in {"select", "values"} and table not in tables:
            tables.append(table)
    lowered = normalized.lower()
    if re.search(r"\bdelete\b", lowered):
        operation, operation_tag = "删除", "删除语句"
    elif re.search(r"\bupdate\b", lowered):
        operation, operation_tag = "更新", "更新语句"
    elif re.search(r"\binsert\b", lowered):
        operation, operation_tag = "写入", "写入语句"
    else:
        operation, operation_tag = "查询", "查询分析"
    parameters = sorted(set(re.findall(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)|@([A-Za-z_][A-Za-z0-9_]*)", normalized)))
    parameter_names = sorted({left or right for left, right in parameters})
    risk_notes: list[str] = []
    if re.search(r"\b(drop|truncate|alter)\b", lowered):
        risk_notes.append("检测到结构变更或清空语句，请确认当前资产仅用于留档且不会直接执行。")
    if operation in {"删除", "更新"} and not re.search(r"\bwhere\b", lowered):
        risk_notes.append(f"{operation}语句未检测到 WHERE 条件，存在全表影响风险。")
    if re.search(r"\bselect\s+\*", lowered):
        risk_notes.append("使用了 SELECT *，建议明确字段以减少口径漂移和不必要的数据暴露。")
    if operation == "查询" and not re.search(r"\b(limit|top|fetch\s+first)\b", lowered):
        risk_notes.append("未检测到结果行数限制，开发验证时建议增加限制条件。")
    if re.search(r"\bwhere\b", lowered) and not parameter_names:
        risk_notes.append("筛选条件未识别到命名参数，建议将日期和阈值参数化。")
    if not tables:
        risk_notes.append("未识别到明确表名，请检查动态 SQL、CTE 或方言写法。")
    sensitive = C.detect_sensitive_snippets(sql_text)
    if sensitive:
        risk_notes.append(f"检测到 {len(sensitive)} 处疑似敏感信息，保存前请确认是否需要脱敏。")
    combined = f"{payload.name} {' '.join(tables)}"
    domain_tags = [tag for tag in C.NOTE_TAGS if tag.lower() in combined.lower()]
    tags = list(dict.fromkeys([*domain_tags, operation_tag]))[:8]
    table_summary = "、".join(tables[:3]) if tables else "相关业务数据表"
    extra = f"等 {len(tables)} 张表" if len(tables) > 3 else ""
    subject = payload.name.strip() or "该 SQL"
    purpose = f"用于{operation}{subject}所需数据，主要涉及 {table_summary}{extra}；结果用于分析与人工复核，不直接形成审计结论。"
    validation = "；".join([
        "核对筛选时间、组织范围与业务口径",
        "抽样比对源系统记录",
        "确认关联键不会造成重复或遗漏",
    ])
    result = {
        "operation": operation,
        "purpose": purpose,
        "tables": tables,
        "tags": tags,
        "parameters": parameter_names,
        "risk_level": "high" if any("全表" in item or "清空" in item for item in risk_notes) else ("medium" if risk_notes else "low"),
        "risk_notes": risk_notes,
        "validation_note": validation,
        "sensitive_findings": sensitive,
        "ai_generated": False,
    }
    ai_settings = C.load_ai_settings()
    if ai_ready(ai_settings):
        try:
            result = enhance_sql_assist(
                ai_settings,
                payload.name,
                sql_text if ai_settings.get("include_sql_text", True) else "",
                result,
                bool(ai_settings.get("include_sql_text", True)),
            )
            result["sensitive_findings"] = sensitive
        except (AINotConfigured, AIRequestError) as exc:
            result["ai_error"] = str(exc)
    return result


@router.post("/api/sql-assets", status_code=status.HTTP_201_CREATED)
def create_sql_asset(payload: SqlAssetCreate) -> dict:
    asset_id = new_id("Q")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO sql_assets
            (id,name,purpose,sql_text,current_version,status,tags_json,table_names_json,related_project_id,reuse_count,validation_note,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,0,'',?,?)""",
            (
                asset_id,
                payload.name,
                payload.purpose,
                payload.sql_text,
                payload.current_version,
                payload.status,
                json.dumps(payload.tags, ensure_ascii=False),
                json.dumps(payload.table_names, ensure_ascii=False),
                payload.related_project_id,
                now,
                now,
            ),
        )
        connection.execute(
            """INSERT INTO sql_versions
            (id,sql_asset_id,version,sql_text,change_summary,validation_status,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (new_id("QV"), asset_id, payload.current_version, payload.sql_text, "创建 SQL 资产", payload.status, now),
        )
    return C.fetch_one("SELECT * FROM sql_assets WHERE id = ?", (asset_id,))


@router.post("/api/sql-assets/batch-delete")
def batch_delete_sql_assets(payload: BatchIds) -> dict:
    return C.batch_delete_records("sql_assets", payload.ids)


@router.post("/api/sql-assets/batch-status")
def batch_update_sql_status(payload: BatchSqlStatus) -> dict:
    return C.batch_update_status("sql_assets", payload.ids, payload.status)


@router.get("/api/sql-assets/{asset_id}")
def get_sql_asset(asset_id: str) -> dict:
    asset = C.fetch_one("SELECT * FROM sql_assets WHERE id = ?", (asset_id,))
    if not asset:
        raise HTTPException(status_code=404, detail="SQL 资产不存在")
    return asset


@router.get("/api/sql-assets/{asset_id}/versions")
def list_sql_versions(asset_id: str) -> list[dict]:
    if not C.fetch_one("SELECT id FROM sql_assets WHERE id = ?", (asset_id,)):
        raise HTTPException(status_code=404, detail="SQL 资产不存在")
    return C.fetch_all(
        "SELECT * FROM sql_versions WHERE sql_asset_id = ? ORDER BY created_at DESC, version DESC",
        (asset_id,),
    )


@router.get("/api/sql-assets/{asset_id}/versions/diff")
def diff_sql_versions(asset_id: str, left: str = Query(...), right: str = Query(...)) -> dict:
    if not C.fetch_one("SELECT id FROM sql_assets WHERE id = ?", (asset_id,)):
        raise HTTPException(status_code=404, detail="SQL 资产不存在")
    left_row = C.fetch_one(
        "SELECT * FROM sql_versions WHERE sql_asset_id = ? AND version = ?",
        (asset_id, left),
    )
    right_row = C.fetch_one(
        "SELECT * FROM sql_versions WHERE sql_asset_id = ? AND version = ?",
        (asset_id, right),
    )
    if not left_row or not right_row:
        raise HTTPException(status_code=404, detail="指定版本不存在")
    left_lines = (left_row.get("sql_text") or "").splitlines()
    right_lines = (right_row.get("sql_text") or "").splitlines()
    diff = list(difflib.unified_diff(left_lines, right_lines, fromfile=left, tofile=right, lineterm=""))
    return {
        "asset_id": asset_id,
        "left": left,
        "right": right,
        "left_summary": left_row.get("change_summary") or "",
        "right_summary": right_row.get("change_summary") or "",
        "diff": diff,
        "changed": bool(diff),
        "sensitive_findings": C.detect_sensitive_snippets(right_row.get("sql_text") or ""),
    }


@router.post("/api/sql-assets/sensitive-check")
def sql_sensitive_check(payload: SqlAssistRequest) -> dict:
    findings = C.detect_sensitive_snippets(payload.sql_text)
    return {"count": len(findings), "findings": findings}


@router.post("/api/sql-assets/{asset_id}/versions", status_code=status.HTTP_201_CREATED)
def create_sql_version(asset_id: str, payload: SqlVersionCreate) -> dict:
    version_id = new_id("QV")
    now = utc_now()
    with transaction() as connection:
        if not connection.execute("SELECT id FROM sql_assets WHERE id = ?", (asset_id,)).fetchone():
            raise HTTPException(status_code=404, detail="SQL 资产不存在")
        try:
            connection.execute(
                """INSERT INTO sql_versions
                (id,sql_asset_id,version,sql_text,change_summary,validation_status,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (version_id, asset_id, payload.version, payload.sql_text, payload.change_summary, payload.validation_status, now),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="该版本号已存在") from exc
            raise
        connection.execute(
            """UPDATE sql_assets
            SET current_version = ?, sql_text = ?, status = ?, validation_note = ?, updated_at = ?
            WHERE id = ?""",
            (payload.version, payload.sql_text, payload.validation_status, payload.change_summary, now, asset_id),
        )
    return C.fetch_one("SELECT * FROM sql_versions WHERE id = ?", (version_id,))


@router.patch("/api/sql-assets/{asset_id}")
def update_sql_asset(asset_id: str, payload: SqlAssetUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "tags" in changes:
        changes["tags_json"] = json.dumps(changes.pop("tags"), ensure_ascii=False)
    if "table_names" in changes:
        changes["table_names_json"] = json.dumps(changes.pop("table_names"), ensure_ascii=False)
    asset = C.update_record("sql_assets", asset_id, changes, "SQL 资产不存在")
    if "sql_text" in changes or "current_version" in changes:
        with transaction() as connection:
            connection.execute(
                """INSERT INTO sql_versions
                (id,sql_asset_id,version,sql_text,change_summary,validation_status,created_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(sql_asset_id, version) DO UPDATE SET
                  sql_text=excluded.sql_text,
                  validation_status=excluded.validation_status""",
                (
                    new_id("QV"), asset_id, asset["current_version"], asset["sql_text"],
                    "通过 SQL 资产编辑同步", asset["status"], utc_now(),
                ),
            )
    return asset


@router.delete("/api/sql-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sql_asset(asset_id: str) -> Response:
    return C.delete_record("sql_assets", asset_id, "SQL 资产不存在")

