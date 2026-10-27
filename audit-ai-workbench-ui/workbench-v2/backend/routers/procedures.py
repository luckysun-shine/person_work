"""API routes: procedures."""
import json

from fastapi import APIRouter, HTTPException, Query, Response, status

from .. import common as C
from ..db import new_id, transaction, utc_now
from ..schemas import ProcedureCreate, ProcedureDeploymentCreate, ProcedureUpdate

router = APIRouter(tags=["procedures"])

@router.get("/api/procedures")
def list_procedures(q: str | None = None, procedure_status: str | None = Query(default=None, alias="status")) -> list[dict]:
    conditions, parameters = [], []
    if q:
        conditions.append("(name LIKE ? OR purpose LIKE ? OR tags_json LIKE ? OR database_name LIKE ?)")
        keyword = f"%{q}%"; parameters.extend([keyword] * 4)
    if procedure_status:
        conditions.append("status = ?"); parameters.append(procedure_status)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return C.fetch_all(f"SELECT * FROM stored_procedures{where} ORDER BY updated_at DESC", tuple(parameters))


@router.post("/api/procedures", status_code=status.HTTP_201_CREATED)
def create_procedure(payload: ProcedureCreate) -> dict:
    procedure_id, now = new_id("SP"), utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO stored_procedures
            (id,name,database_name,schema_name,purpose,status,current_version,owner,tags_json,
             definition_text,rollback_text,related_project_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (procedure_id, payload.name, payload.database_name, payload.schema_name, payload.purpose,
             payload.status, payload.current_version, payload.owner, json.dumps(payload.tags, ensure_ascii=False),
             payload.definition_text, payload.rollback_text, payload.related_project_id, now, now),
        )
        connection.execute(
            """INSERT INTO procedure_versions
            (id,procedure_id,version,definition_text,rollback_text,change_summary,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (new_id("SPV"), procedure_id, payload.current_version, payload.definition_text,
             payload.rollback_text, payload.change_summary, now),
        )
    return C.fetch_one("SELECT * FROM stored_procedures WHERE id = ?", (procedure_id,))


@router.get("/api/procedures/{procedure_id}")
def get_procedure(procedure_id: str) -> dict:
    item = C.fetch_one("SELECT * FROM stored_procedures WHERE id = ?", (procedure_id,))
    if not item:
        raise HTTPException(status_code=404, detail="存储过程不存在")
    item["versions"] = C.fetch_all("SELECT * FROM procedure_versions WHERE procedure_id = ? ORDER BY created_at DESC, rowid DESC", (procedure_id,))
    item["deployments"] = C.fetch_all("SELECT * FROM procedure_deployments WHERE procedure_id = ? ORDER BY created_at DESC, rowid DESC", (procedure_id,))
    return item


@router.patch("/api/procedures/{procedure_id}")
def update_procedure(procedure_id: str, payload: ProcedureUpdate) -> dict:
    previous = C.fetch_one("SELECT * FROM stored_procedures WHERE id = ?", (procedure_id,))
    if not previous:
        raise HTTPException(status_code=404, detail="存储过程不存在")
    changes = payload.model_dump(exclude_unset=True); summary = changes.pop("change_summary", None)
    if "tags" in changes:
        changes["tags_json"] = json.dumps(changes.pop("tags"), ensure_ascii=False)
    version_changed = "current_version" in changes and changes["current_version"] != previous["current_version"]
    if version_changed and C.fetch_one("SELECT id FROM procedure_versions WHERE procedure_id = ? AND version = ?", (procedure_id, changes["current_version"])):
        raise HTTPException(status_code=409, detail="该存储过程版本已经存在")
    item = C.update_record("stored_procedures", procedure_id, changes, "存储过程不存在")
    if version_changed:
        with transaction() as connection:
            connection.execute(
                """INSERT INTO procedure_versions
                (id,procedure_id,version,definition_text,rollback_text,change_summary,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (new_id("SPV"), procedure_id, item["current_version"], item["definition_text"],
                 item["rollback_text"], summary or "更新存储过程版本", utc_now()),
            )
    return item


@router.post("/api/procedures/{procedure_id}/deployments", status_code=status.HTTP_201_CREATED)
def create_procedure_deployment(procedure_id: str, payload: ProcedureDeploymentCreate) -> dict:
    if not C.fetch_one("SELECT id FROM stored_procedures WHERE id = ?", (procedure_id,)):
        raise HTTPException(status_code=404, detail="存储过程不存在")
    deployment_id, now = new_id("SPD"), utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO procedure_deployments
            (id,procedure_id,version,environment,status,deployed_at,validation_result,rollback_executed,notes,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (deployment_id, procedure_id, payload.version, payload.environment, payload.status,
             payload.deployed_at, payload.validation_result, int(payload.rollback_executed), payload.notes, now),
        )
    return C.fetch_one("SELECT * FROM procedure_deployments WHERE id = ?", (deployment_id,))


@router.delete("/api/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_procedure(procedure_id: str) -> Response:
    return C.delete_record("stored_procedures", procedure_id, "存储过程不存在")

