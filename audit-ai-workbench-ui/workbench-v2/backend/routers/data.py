"""API routes: data."""
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import io
import json
import sqlite3

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

from .. import common as C
from ..db import connect, init_db, transaction, utc_now
from ..schemas import BackupMergePayload, CsvImportPayload, DataImportPayload, TableRestorePayload

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


@router.post("/api/backups/import", status_code=status.HTTP_201_CREATED)
def import_backup_file(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "imported.db"
    if not filename.lower().endswith(".db"):
        raise HTTPException(status_code=400, detail="请上传 .db 备份文件")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > C.MAX_BACKUP_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="备份文件超过 200MB 上限")
        chunks.append(chunk)
    path = C.save_uploaded_backup(b"".join(chunks), filename)
    info = C.backup_info(path)
    validation = C.validate_sqlite_backup(path)
    removed = C.prune_backups()
    info.update({
        "imported": True,
        "original_name": Path(filename).name,
        "counts": validation["counts"],
        "pruned": removed,
        "retention": int(C.get_setting("backup_retention", 20) or 20),
    })
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
    C.validate_sqlite_backup(backup_path)
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


@router.post("/api/backups/{name}/merge-preview")
def preview_backup_merge(name: str, payload: BackupMergePayload = BackupMergePayload()) -> dict:
    path = C.resolve_backup(name)
    C.validate_sqlite_backup(path)
    tables = C.extract_tables_from_backup(path, payload.tables)
    result = C.preview_import_tables(tables, payload.mode)
    result["backup"] = name
    result["skipped_tables"] = sorted(C.BACKUP_MERGE_SKIP_TABLES)
    return result


@router.post("/api/backups/{name}/merge")
def merge_backup(name: str, payload: BackupMergePayload = BackupMergePayload()) -> dict:
    path = C.resolve_backup(name)
    C.validate_sqlite_backup(path)
    tables = C.extract_tables_from_backup(path, payload.tables)
    if not tables:
        raise HTTPException(status_code=400, detail="备份中没有可合并的数据表")
    result = C.import_tables(tables, payload.mode)
    result["backup"] = name
    result["skipped_tables"] = sorted(C.BACKUP_MERGE_SKIP_TABLES)
    return result


@router.post("/api/data/import/preview")
def preview_import(payload: DataImportPayload) -> dict:
    result = C.preview_import_tables(payload.tables, payload.mode)
    result["schema_version"] = payload.schema_version
    return result


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

