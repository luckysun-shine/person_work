"""API routes: requests."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import common as C
from ..db import new_id, transaction, utc_now
from ..schemas import (
    BatchIds,
    BatchRequestStatus,
    DataRequestCreate,
    DataRequestSqlVersionCreate,
    DataRequestUpdate,
)

router = APIRouter(tags=["requests"])

@router.get("/api/data-requests")
def list_data_requests(
    q: str | None = None,
    requester: str | None = None,
    department: str | None = None,
    request_status: Annotated[str | None, Query(alias="status")] = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    conditions: list[str] = []
    parameters: list = []
    if q:
        keyword = f"%{q}%"
        conditions.append(
            "(title LIKE ? OR purpose LIKE ? OR scope LIKE ? OR caliber_notes LIKE ? OR requester LIKE ? OR department LIKE ? OR sql_text LIKE ?)"
        )
        parameters.extend([keyword, keyword, keyword, keyword, keyword, keyword, keyword])
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


def _request_sql_versions(request_id: str) -> list[dict]:
    return C.fetch_all(
        """SELECT * FROM data_request_sql_versions
        WHERE request_id = ? ORDER BY created_at DESC""",
        (request_id,),
    )


def _seed_request_sql_version(connection, request_id: str, version: str, sql_text: str, summary: str, now: str) -> None:
    if not (sql_text or "").strip():
        return
    connection.execute(
        """INSERT INTO data_request_sql_versions
        (id,request_id,version,sql_text,change_summary,created_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(request_id, version) DO UPDATE SET
          sql_text=excluded.sql_text,
          change_summary=excluded.change_summary""",
        (new_id("DRV"), request_id, version, sql_text, summary, now),
    )


@router.post("/api/data-requests", status_code=status.HTTP_201_CREATED)
def create_data_request(payload: DataRequestCreate) -> dict:
    request_id = new_id("DR")
    now = utc_now()
    version = payload.sql_current_version or "v1.0"
    with transaction() as connection:
        connection.execute(
            """INSERT INTO data_requests
            (id,title,purpose,scope,caliber_notes,due_at,status,next_action,related_sql_ids_json,related_project_id,
             requester,department,waiting_on,delivery_method,delivery_location,sensitive_notes,
             sql_text,sql_current_version,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                request_id,
                payload.title,
                payload.purpose,
                payload.scope,
                payload.caliber_notes,
                payload.due_at,
                payload.status,
                "",
                "[]",
                None,
                payload.requester,
                payload.department,
                "",
                "",
                "",
                "",
                payload.sql_text,
                version,
                now,
                now,
            ),
        )
        _seed_request_sql_version(
            connection, request_id, version, payload.sql_text, "创建请求时记录", now
        )
    item = C.fetch_one("SELECT * FROM data_requests WHERE id = ?", (request_id,))
    item["sql_versions"] = _request_sql_versions(request_id)
    return item


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
    request["sql_versions"] = _request_sql_versions(request_id)
    return request


@router.patch("/api/data-requests/{request_id}")
def update_data_request(request_id: str, payload: DataRequestUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    item = C.update_record("data_requests", request_id, changes, "数据请求不存在")
    if "sql_text" in changes:
        version = item.get("sql_current_version") or "v1.0"
        with transaction() as connection:
            _seed_request_sql_version(
                connection,
                request_id,
                version,
                item.get("sql_text") or "",
                "通过请求编辑同步当前版本",
                utc_now(),
            )
    item["sql_versions"] = _request_sql_versions(request_id)
    return item


@router.get("/api/data-requests/{request_id}/sql-versions")
def list_data_request_sql_versions(request_id: str) -> list[dict]:
    if not C.fetch_one("SELECT id FROM data_requests WHERE id = ?", (request_id,)):
        raise HTTPException(status_code=404, detail="数据请求不存在")
    return _request_sql_versions(request_id)


@router.post("/api/data-requests/{request_id}/sql-versions", status_code=status.HTTP_201_CREATED)
def create_data_request_sql_version(request_id: str, payload: DataRequestSqlVersionCreate) -> dict:
    if not C.fetch_one("SELECT id FROM data_requests WHERE id = ?", (request_id,)):
        raise HTTPException(status_code=404, detail="数据请求不存在")
    version_id, now = new_id("DRV"), utc_now()
    with transaction() as connection:
        try:
            connection.execute(
                """INSERT INTO data_request_sql_versions
                (id,request_id,version,sql_text,change_summary,created_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    version_id,
                    request_id,
                    payload.version,
                    payload.sql_text,
                    payload.change_summary,
                    now,
                ),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="该 SQL 版本号已存在") from exc
            raise
        connection.execute(
            """UPDATE data_requests
            SET sql_text = ?, sql_current_version = ?, updated_at = ?
            WHERE id = ?""",
            (payload.sql_text, payload.version, now, request_id),
        )
    return C.fetch_one("SELECT * FROM data_request_sql_versions WHERE id = ?", (version_id,))


@router.post("/api/data-requests/{request_id}/sql-versions/{version_id}/restore")
def restore_data_request_sql_version(request_id: str, version_id: str) -> dict:
    version = C.fetch_one(
        "SELECT * FROM data_request_sql_versions WHERE id = ? AND request_id = ?",
        (version_id, request_id),
    )
    if not version:
        raise HTTPException(status_code=404, detail="SQL 版本不存在")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """UPDATE data_requests
            SET sql_text = ?, sql_current_version = ?, updated_at = ?
            WHERE id = ?""",
            (version["sql_text"], version["version"], now, request_id),
        )
    item = C.fetch_one("SELECT * FROM data_requests WHERE id = ?", (request_id,))
    item["sql_versions"] = _request_sql_versions(request_id)
    return item


@router.delete("/api/data-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_request(request_id: str) -> Response:
    return C.delete_record("data_requests", request_id, "数据请求不存在")

