"""API routes: models."""
import json
import sqlite3

from fastapi import APIRouter, HTTPException, Response, status

from .. import common as C
from ..db import new_id, transaction, utc_now
from ..schemas import (
    ModelCreate,
    ModelRunCreate,
    ModelRunUpdate,
    ModelSqlVersionCreate,
    ModelUpdate,
)

router = APIRouter(tags=["models"])


def _model_sql_versions(model_id: str) -> list[dict]:
    return C.fetch_all(
        """SELECT * FROM model_sql_versions
        WHERE model_id = ? ORDER BY created_at DESC""",
        (model_id,),
    )


def _seed_model_sql_version(connection, model_id: str, version: str, sql_text: str, summary: str, now: str) -> None:
    if not (sql_text or "").strip():
        return
    connection.execute(
        """INSERT INTO model_sql_versions
        (id,model_id,version,sql_text,change_summary,created_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(model_id, version) DO UPDATE SET
          sql_text=excluded.sql_text,
          change_summary=excluded.change_summary""",
        (new_id("MSV"), model_id, version, sql_text, summary, now),
    )


def _enrich_model(model: dict) -> dict:
    model_id = model["id"]
    model["versions"] = C.fetch_all(
        "SELECT * FROM model_versions WHERE model_id = ? ORDER BY created_at DESC, rowid DESC",
        (model_id,),
    )
    model["sql_versions"] = _model_sql_versions(model_id)
    linked = C.fetch_all(
        """SELECT p.id, p.name, p.category, p.status
        FROM project_relations r
        INNER JOIN projects p ON p.id = r.project_id
        WHERE r.entity_type = 'model' AND r.entity_id = ?
        ORDER BY p.updated_at DESC""",
        (model_id,),
    )
    model["linked_projects"] = linked
    model["linked_project_id"] = linked[0]["id"] if linked else None
    return model


@router.get("/api/models")
def list_models() -> list[dict]:
    return C.fetch_all("SELECT * FROM monitoring_models ORDER BY updated_at DESC")


@router.post("/api/models", status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelCreate) -> dict:
    model_id = new_id("M")
    now = utc_now()
    values = payload.model_dump()
    change_summary = values.pop("change_summary")
    sql_text = values.pop("sql_text") or ""
    sql_version = values.pop("sql_current_version") or "v1.0"
    for field in ("rule_definitions", "dependency_ids", "related_sql_ids", "update_steps"):
        values[f"{field}_json"] = json.dumps(values.pop(field), ensure_ascii=False)
    with transaction() as connection:
        connection.execute(
            """INSERT INTO monitoring_models
            (id,name,purpose,status,schedule,current_version,rule_definitions_json,dependency_ids_json,
             related_sql_ids_json,update_steps_json,sql_text,sql_current_version,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                model_id, values["name"], values["purpose"], values["status"], values["schedule"],
                values["current_version"], values["rule_definitions_json"], values["dependency_ids_json"],
                values["related_sql_ids_json"], values["update_steps_json"], sql_text, sql_version, now, now,
            ),
        )
        connection.execute(
            "INSERT INTO model_versions (id,model_id,version,change_summary,created_at) VALUES (?,?,?,?,?)",
            (new_id("MV"), model_id, values["current_version"], change_summary, now),
        )
        _seed_model_sql_version(connection, model_id, sql_version, sql_text, "创建模型时记录 SQL", now)
    model = C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (model_id,))
    return _enrich_model(model)


@router.get("/api/models/{model_id}")
def get_model(model_id: str) -> dict:
    model = C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (model_id,))
    if not model:
        raise HTTPException(status_code=404, detail="监测模型不存在")
    return _enrich_model(model)


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
    if "sql_text" in changes:
        version = model.get("sql_current_version") or previous.get("sql_current_version") or "v1.0"
        with transaction() as connection:
            _seed_model_sql_version(
                connection,
                model_id,
                version,
                model.get("sql_text") or "",
                "通过模型编辑同步当前 SQL 版本",
                utc_now(),
            )
    return _enrich_model(model)


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


@router.get("/api/models/{model_id}/sql-versions")
def list_model_sql_versions(model_id: str) -> list[dict]:
    if not C.fetch_one("SELECT id FROM monitoring_models WHERE id = ?", (model_id,)):
        raise HTTPException(status_code=404, detail="监测模型不存在")
    return _model_sql_versions(model_id)


@router.post("/api/models/{model_id}/sql-versions", status_code=status.HTTP_201_CREATED)
def create_model_sql_version(model_id: str, payload: ModelSqlVersionCreate) -> dict:
    if not C.fetch_one("SELECT id FROM monitoring_models WHERE id = ?", (model_id,)):
        raise HTTPException(status_code=404, detail="监测模型不存在")
    version_id, now = new_id("MSV"), utc_now()
    with transaction() as connection:
        try:
            connection.execute(
                """INSERT INTO model_sql_versions
                (id,model_id,version,sql_text,change_summary,created_at)
                VALUES (?,?,?,?,?,?)""",
                (version_id, model_id, payload.version, payload.sql_text, payload.change_summary, now),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="该 SQL 版本号已存在") from exc
            raise
        connection.execute(
            """UPDATE monitoring_models
            SET sql_text = ?, sql_current_version = ?, updated_at = ?
            WHERE id = ?""",
            (payload.sql_text, payload.version, now, model_id),
        )
    return C.fetch_one("SELECT * FROM model_sql_versions WHERE id = ?", (version_id,))


@router.post("/api/models/{model_id}/sql-versions/{version_id}/restore")
def restore_model_sql_version(model_id: str, version_id: str) -> dict:
    version = C.fetch_one(
        "SELECT * FROM model_sql_versions WHERE id = ? AND model_id = ?",
        (version_id, model_id),
    )
    if not version:
        raise HTTPException(status_code=404, detail="SQL 版本不存在")
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """UPDATE monitoring_models
            SET sql_text = ?, sql_current_version = ?, updated_at = ?
            WHERE id = ?""",
            (version["sql_text"], version["version"], now, model_id),
        )
    model = C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (model_id,))
    return _enrich_model(model)


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
        _sync_model_run_stats(connection, model_id, now)
    return C.fetch_one("SELECT * FROM model_runs WHERE id = ?", (run_id,))


def _sync_model_run_stats(connection, model_id: str, now: str) -> None:
    """以时间最新的一次运行为准回写模型统计；补录历史运行不会覆盖最新状态。

    待复核数 = 最新一次运行的命中数 - 已复核数（不低于 0）。
    """
    latest = connection.execute(
        """SELECT started_at, finished_at, hit_count, reviewed_count
        FROM model_runs WHERE model_id = ?
        ORDER BY COALESCE(finished_at, started_at) DESC, started_at DESC, created_at DESC
        LIMIT 1""",
        (model_id,),
    ).fetchone()
    if not latest:
        connection.execute(
            """UPDATE monitoring_models SET last_run_at = NULL, hit_count = 0,
            pending_review_count = 0, updated_at = ? WHERE id = ?""",
            (now, model_id),
        )
        return
    hit = int(latest["hit_count"] or 0)
    reviewed = int(latest["reviewed_count"] or 0)
    connection.execute(
        """UPDATE monitoring_models SET last_run_at = ?, hit_count = ?,
        pending_review_count = ?, updated_at = ? WHERE id = ?""",
        (latest["finished_at"] or latest["started_at"], hit, max(hit - reviewed, 0), now, model_id),
    )


@router.patch("/api/models/{model_id}/runs/{run_id}")
def update_model_run(model_id: str, run_id: str, payload: ModelRunUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    now = utc_now()
    with transaction() as connection:
        run = connection.execute(
            "SELECT * FROM model_runs WHERE id = ? AND model_id = ?", (run_id, model_id)
        ).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        if changes:
            hit = int(changes.get("hit_count", run["hit_count"]) or 0)
            reviewed = int(changes.get("reviewed_count", run["reviewed_count"]) or 0)
            if reviewed > hit:
                raise HTTPException(status_code=400, detail="已复核数不能超过命中数")
            assignments = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(
                f"UPDATE model_runs SET {assignments} WHERE id = ?",
                (*changes.values(), run_id),
            )
        _sync_model_run_stats(connection, model_id, now)
    return C.fetch_one("SELECT * FROM model_runs WHERE id = ?", (run_id,))


@router.delete("/api/models/{model_id}/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_run(model_id: str, run_id: str) -> Response:
    with transaction() as connection:
        result = connection.execute(
            "DELETE FROM model_runs WHERE id = ? AND model_id = ?", (run_id, model_id)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        _sync_model_run_stats(connection, model_id, utc_now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
