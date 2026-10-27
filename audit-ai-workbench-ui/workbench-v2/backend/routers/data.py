"""API routes: data."""
from datetime import date, datetime, timedelta
import csv
import io
import json
import sqlite3

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse

from .. import common as C
from ..db import connect, init_db, row_to_dict, transaction, utc_now
from ..schemas import CsvImportPayload, DataImportPayload, TableRestorePayload

router = APIRouter(tags=["data"])


def export_package() -> dict:
    return {
        "schema_version": C.APP_VERSION,
        "exported_at": utc_now(),
        "tables": {table: C.fetch_all(f"SELECT * FROM {table}") for table in C.EXPORT_TABLES},
    }


@router.get("/api/data/export.json")
def export_json() -> Response:
    content = json.dumps(export_package(), ensure_ascii=False, indent=2)
    headers = {"Content-Disposition": f'attachment; filename="audit-workbench-{date.today().isoformat()}.json"'}
    return Response(content=content, media_type="application/json; charset=utf-8", headers=headers)


@router.get("/api/data/export.csv")
def export_csv(entity: str = "tasks") -> Response:
    if entity not in C.EXPORT_TABLES:
        raise HTTPException(status_code=400, detail="不支持导出该数据类型")
    rows = C.fetch_all(f"SELECT * FROM {entity}")
    output = io.StringIO(newline="")
    fieldnames = list(rows[0]) if rows else ["id"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})
    headers = {"Content-Disposition": f'attachment; filename="{entity}-{date.today().isoformat()}.csv"'}
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/api/backups")
def list_backups() -> list[dict]:
    return [C.backup_info(path) for path in sorted(C.backup_directory().glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True)]


@router.post("/api/backups", status_code=status.HTTP_201_CREATED)
def create_backup() -> dict:
    info = C.backup_info(C.create_database_backup())
    removed = C.prune_backups()
    info["retention"] = int(C.get_setting("backup_retention", 20) or 20)
    info["pruned"] = removed
    return info


@router.post("/api/backups/auto-check")
def auto_backup_check() -> dict:
    hours = int(C.get_setting("auto_backup_hours", 0) or 0)
    if hours <= 0:
        return {"enabled": False, "created": False, "reason": "未启用定时备份"}
    last = C.get_setting("last_auto_backup_at", "") or ""
    now = datetime.now().astimezone()
    if last:
        try:
            previous = datetime.fromisoformat(last)
            if previous.tzinfo is None:
                previous = previous.astimezone()
            if now - previous < timedelta(hours=hours):
                return {
                    "enabled": True,
                    "created": False,
                    "reason": "未到备份间隔",
                    "last_auto_backup_at": last,
                    "next_due_hours": round(hours - (now - previous).total_seconds() / 3600, 2),
                }
        except ValueError:
            pass
    info = C.backup_info(C.create_database_backup("auto"))
    removed = C.prune_backups()
    stamp = utc_now()
    C.set_setting("last_auto_backup_at", stamp)
    return {
        "enabled": True,
        "created": True,
        "backup": info,
        "pruned": removed,
        "last_auto_backup_at": stamp,
    }


@router.delete("/api/backups/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(name: str) -> Response:
    C.resolve_backup(name).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/backups/{name}/download")
def download_backup(name: str) -> FileResponse:
    return FileResponse(C.resolve_backup(name), media_type="application/vnd.sqlite3", filename=name)


@router.post("/api/backups/{name}/restore")
def restore_backup(name: str) -> dict:
    backup_path = C.resolve_backup(name)
    validation = sqlite3.connect(backup_path)
    try:
        tables = {row[0] for row in validation.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    finally:
        validation.close()
    if not {"tasks", "sql_assets", "projects"}.issubset(tables):
        raise HTTPException(status_code=400, detail="备份结构不完整，已拒绝恢复")
    safety = C.create_database_backup("before-restore")
    source = sqlite3.connect(backup_path)
    target = connect()
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    init_db()
    return {"restored": name, "safety_backup": safety.name}


@router.post("/api/backups/{name}/restore-tables")
def restore_backup_tables(name: str, payload: TableRestorePayload) -> dict:
    unknown = set(payload.tables) - set(C.EXPORT_TABLES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"不支持恢复的数据表：{', '.join(sorted(unknown))}")
    backup_path = C.resolve_backup(name)
    safety = C.create_database_backup("before-table-restore")
    source = sqlite3.connect(backup_path)
    source.row_factory = sqlite3.Row
    restored: dict[str, int] = {}
    try:
        available = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        missing = [table for table in payload.tables if table not in available]
        if missing:
            raise HTTPException(status_code=400, detail=f"备份中缺少数据表：{', '.join(missing)}")
        with transaction() as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            for table in payload.tables:
                rows = [dict(row) for row in source.execute(f"SELECT * FROM {table}").fetchall()]
                connection.execute(f"DELETE FROM {table}")
                for row in rows:
                    columns = list(row)
                    placeholders = ",".join("?" for _ in columns)
                    connection.execute(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                        tuple(row[column] for column in columns),
                    )
                restored[table] = len(rows)
            connection.execute("PRAGMA foreign_keys = ON")
    finally:
        source.close()
    init_db()
    return {"restored_tables": restored, "safety_backup": safety.name, "backup": name}


@router.post("/api/data/import/preview")
def preview_import(payload: DataImportPayload) -> dict:
    unknown = set(payload.tables) - set(C.EXPORT_TABLES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"包含不支持的数据表：{', '.join(sorted(unknown))}")
    connection = connect()
    diffs: dict[str, dict] = {}
    try:
        for table, rows in payload.tables.items():
            new_ids: list[str] = []
            updated_ids: list[str] = []
            unchanged_ids: list[str] = []
            for source_row in rows:
                row = C.normalize_import_row(connection, table, source_row)
                existing = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (row["id"],)).fetchone()
                if not existing:
                    new_ids.append(row["id"])
                    continue
                existing_dict = row_to_dict(existing)
                existing_normalized = C.normalize_import_row(connection, table, existing_dict)
                if C.comparable_row(existing_normalized) == C.comparable_row(row):
                    unchanged_ids.append(row["id"])
                else:
                    updated_ids.append(row["id"])
            diffs[table] = {
                "incoming": len(rows),
                "new": len(new_ids),
                "updated": len(updated_ids),
                "unchanged": len(unchanged_ids),
                "sample_new": new_ids[:5],
                "sample_updated": updated_ids[:5],
                "sample_unchanged": unchanged_ids[:5],
            }
    except (sqlite3.DatabaseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"预检失败：{exc}") from exc
    finally:
        connection.close()
    return {
        "schema_version": payload.schema_version,
        "mode": payload.mode,
        "tables": {table: info["incoming"] for table, info in diffs.items()},
        "diff": diffs,
        "total": sum(info["incoming"] for info in diffs.values()),
        "summary": {
            "new": sum(info["new"] for info in diffs.values()),
            "updated": sum(info["updated"] for info in diffs.values()),
            "unchanged": sum(info["unchanged"] for info in diffs.values()),
        },
    }


@router.post("/api/data/import")
def import_json(payload: DataImportPayload) -> dict:
    return C.import_tables(payload.tables, payload.mode)


@router.post("/api/data/import.csv")
def import_csv(payload: CsvImportPayload) -> dict:
    if payload.entity not in C.EXPORT_TABLES:
        raise HTTPException(status_code=400, detail="不支持导入该数据类型")
    text = payload.csv_text.removeprefix("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(status_code=400, detail="CSV 中没有可导入的数据")
    return C.import_tables({payload.entity: rows}, payload.mode)

