import csv
import difflib
import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, Response, status

from . import db as database
from .ai_client import DEFAULT_AI_SETTINGS, ai_ready
from .db import PROJECT_DIR, connect, new_id, row_to_dict, transaction, utc_now
from .secrets_util import decrypt_secret, encrypt_secret, machine_secret, mask_secret

# Shared domain tags (notes assist + SQL assist)
NOTE_TAGS = (
    "采购", "付款", "供应商", "固定资产", "费用", "审计报告", "知识库", "SQL",
    "模型", "数据请求", "口径", "风险", "数据质量", "规则变更", "项目复盘",
)

APP_VERSION = "1.9.33"

ACCESS_COOKIE = "workbench_access"
PUBLIC_API_PREFIXES = (
    "/api/health",
    "/api/access/",
)


def hash_password(password: str) -> str:
    salt = machine_secret().hex()[:16]
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    candidate = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate, digest)


ACCESS_SESSION_SECONDS = 60 * 60 * 24 * 14


def issue_access_token() -> str:
    expiry = int(time.time()) + ACCESS_SESSION_SECONDS
    version = current_access_token_version()
    payload = f"{expiry}:{version}"
    signature = hmac.new(machine_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def access_token_valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(machine_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    try:
        if ":" in payload:
            expiry_s, version_s = payload.split(":", 1)
            if int(version_s) != current_access_token_version():
                return False
            return int(expiry_s) >= int(time.time())
        # 旧格式（无版本）：仅在版本仍为 1 时有效
        return int(payload) >= int(time.time()) and current_access_token_version() == 1
    except ValueError:
        return False


def access_token_expires_at(token: str | None) -> str | None:
    if not access_token_valid(token):
        return None
    payload = token.rsplit(".", 1)[0]
    expiry_s = payload.split(":", 1)[0]
    try:
        return datetime.fromtimestamp(int(expiry_s)).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def access_password_required() -> bool:
    return bool(get_setting("access_password_hash", "") or "")


def load_ai_settings() -> dict:
    stored = get_setting("ai", None) or {}
    merged = {**DEFAULT_AI_SETTINGS, **(stored if isinstance(stored, dict) else {})}
    merged["api_key"] = decrypt_secret(merged.get("api_key") or "")
    return merged


def public_ai_settings() -> dict:
    settings = load_ai_settings()
    return {
        "enabled": bool(settings.get("enabled")),
        "base_url": settings.get("base_url") or "",
        "model": settings.get("model") or "",
        "api_key_masked": mask_secret(settings.get("api_key") or ""),
        "has_api_key": bool(settings.get("api_key")),
        "timeout_seconds": int(settings.get("timeout_seconds") or 60),
        "include_sql_text": bool(settings.get("include_sql_text", True)),
        "temperature": float(settings.get("temperature") or 0.2),
        "ready": ai_ready(settings),
    }


def load_dingtalk_calendar_settings() -> dict:
    stored = get_setting("dingtalk_calendar", None) or {}
    defaults = {
        "enabled": False,
        "provider": "caldav",
        "ics_url": "",
        "app_key": "",
        "app_secret": "",
        "calendar_id": "",
        "caldav_url": "https://calendar.dingtalk.com",
        "caldav_username": "",
        "caldav_password": "",
        "caldav_path": "",
        "sync_days_back": 7,
        "sync_days_forward": 21,
    }
    merged = {**defaults, **(stored if isinstance(stored, dict) else {})}
    merged["app_secret"] = decrypt_secret(merged.get("app_secret") or "")
    merged["caldav_password"] = decrypt_secret(merged.get("caldav_password") or "")
    return merged


def public_dingtalk_calendar_settings() -> dict:
    settings = load_dingtalk_calendar_settings()
    return {
        "enabled": bool(settings.get("enabled")),
        "provider": settings.get("provider") or "caldav",
        "ics_url": settings.get("ics_url") or "",
        "app_key": settings.get("app_key") or "",
        "has_app_secret": bool(settings.get("app_secret")),
        "calendar_id": settings.get("calendar_id") or "",
        "caldav_url": settings.get("caldav_url") or "https://calendar.dingtalk.com",
        "caldav_username": settings.get("caldav_username") or "",
        "has_caldav_password": bool(settings.get("caldav_password")),
        "caldav_path": settings.get("caldav_path") or "",
        "sync_days_back": int(settings.get("sync_days_back") or 7),
        "sync_days_forward": int(settings.get("sync_days_forward") or 21),
    }


def public_calendar_subscription(item: dict) -> dict:
    config = item.get("config") if isinstance(item.get("config"), dict) else {}
    if not config and isinstance(item.get("config_json"), str):
        try:
            config = json.loads(item.get("config_json") or "{}")
        except Exception:
            config = {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "provider": item.get("provider") or "ics",
        "ics_url": item.get("ics_url") or "",
        "enabled": bool(item.get("enabled")),
        "last_synced_at": item.get("last_synced_at"),
        "last_error": item.get("last_error") or "",
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "caldav_url": config.get("url") or "",
        "caldav_username": config.get("username") or "",
        "has_caldav_password": bool(config.get("password_enc") or config.get("password")),
        "caldav_path": config.get("calendar_path") or "",
    }


def detect_sensitive_snippets(text: str) -> list[dict]:
    patterns = [
        ("password_assignment", r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{4,}['\"]"),
        ("bearer_token", r"(?i)(bearer\s+[A-Za-z0-9\-._~+/]+=*)"),
        ("api_key", r"(?i)(api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
        ("china_mobile", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        ("china_id", r"(?<!\d)\d{17}[\dXx](?!\d)"),
    ]
    findings: list[dict] = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, text or ""):
            findings.append({"type": label, "snippet": match.group(0)[:48]})
            if len(findings) >= 20:
                return findings
    return findings



def get_setting(key: str, default=None):
    row = fetch_one("SELECT * FROM app_settings WHERE key = ?", (key,))
    if not row:
        return default
    return row.get("value", default)


def set_setting(key: str, value) -> dict:
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at""",
            (key, json.dumps(value, ensure_ascii=False), now),
        )
    return {"key": key, "value": value, "updated_at": now}


def prune_backups(retention: int | None = None) -> list[str]:
    keep = retention if retention is not None else int(get_setting("backup_retention", 20) or 20)
    keep = max(3, min(keep, 200))
    backups = sorted(backup_directory().glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for path in backups[keep:]:
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def snapshot_report_version(report_kind: str, report_key: str, title: str, status: str, payload: dict, change_summary: str = "") -> dict:
    latest = fetch_one(
        "SELECT COALESCE(MAX(version), 0) AS version FROM report_versions WHERE report_kind = ? AND report_key = ?",
        (report_kind, report_key),
    )
    version = int((latest or {}).get("version") or 0) + 1
    version_id, now = new_id("RV"), utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO report_versions
            (id,report_kind,report_key,version,title,status,payload_json,change_summary,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                version_id, report_kind, report_key, version, title, status,
                json.dumps(payload, ensure_ascii=False), change_summary or f"保存版本 v{version}", now,
            ),
        )
    return fetch_one("SELECT * FROM report_versions WHERE id = ?", (version_id,))


def fetch_all(query: str, parameters: tuple = ()) -> list[dict]:
    connection = connect()
    try:
        return [row_to_dict(row) for row in connection.execute(query, parameters).fetchall()]
    finally:
        connection.close()


def fetch_one(query: str, parameters: tuple = ()) -> dict | None:
    connection = connect()
    try:
        row = connection.execute(query, parameters).fetchone()
        return row_to_dict(row) if row else None
    finally:
        connection.close()


def update_record(table: str, record_id: str, changes: dict, not_found: str) -> dict:
    if not changes:
        current = fetch_one(f"SELECT * FROM {table} WHERE id = ?", (record_id,))
        if not current:
            raise HTTPException(status_code=404, detail=not_found)
        return current
    changes["updated_at"] = utc_now()
    assignments = ", ".join(f"{field} = ?" for field in changes)
    with transaction() as connection:
        result = connection.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            (*changes.values(), record_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=not_found)
    return fetch_one(f"SELECT * FROM {table} WHERE id = ?", (record_id,))


def delete_record(table: str, record_id: str, not_found: str) -> Response:
    with transaction() as connection:
        result = connection.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail=not_found)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def batch_delete_records(table: str, ids: list[str]) -> dict:
    placeholders = ",".join("?" for _ in ids)
    with transaction() as connection:
        result = connection.execute(
            f"DELETE FROM {table} WHERE id IN ({placeholders})",
            tuple(ids),
        )
    return {"affected": result.rowcount}


def batch_update_status(table: str, ids: list[str], value: str) -> dict:
    placeholders = ",".join("?" for _ in ids)
    with transaction() as connection:
        result = connection.execute(
            f"UPDATE {table} SET status = ?, updated_at = ? WHERE id IN ({placeholders})",
            (value, utc_now(), *ids),
        )
    return {"affected": result.rowcount}



EXPORT_TABLES = {
    "tasks": "任务",
    "work_notes": "工作记录",
    "sql_assets": "SQL 资产",
    "data_requests": "数据请求",
    "monitoring_models": "监测模型",
    "projects": "项目",
    "sql_versions": "SQL 版本",
    "model_runs": "模型运行",
    "model_versions": "模型版本",
    "project_relations": "项目关系",
    "navigation_items": "常用导航",
    "stored_procedures": "存储过程",
    "procedure_versions": "存储过程版本",
    "procedure_deployments": "存储过程发布",
    "report_templates": "报告模板",
    "generated_reports": "多类型报告",
    "report_versions": "报告版本",
    "week_reviews": "周复盘",
    "weekly_reports": "周工作报告",
    "saved_searches": "保存的检索",
    "recent_searches": "最近检索",
    "app_settings": "系统设置",
    "calendar_subscriptions": "日历订阅",
    "calendar_events": "日历事件",
    "work_note_revisions": "工作记录修订",
    "project_templates": "项目模板",
}



def backup_directory() -> Path:
    path = database.DB_PATH.parent / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_database_backup(label: str = "manual") -> Path:
    safe_label = "".join(character for character in label if character.isalnum() or character in "-_")[:24] or "backup"
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    target_path = backup_directory() / f"workbench-{stamp}-{safe_label}.db"
    source = connect()
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return target_path


def backup_info(path: Path) -> dict:
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "created_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
    }


def resolve_backup(name: str) -> Path:
    if Path(name).name != name or not name.endswith(".db"):
        raise HTTPException(status_code=400, detail="备份文件名不合法")
    path = backup_directory() / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="备份不存在")
    return path



def normalize_import_row(connection: sqlite3.Connection, table: str, row: dict) -> dict:
    columns = {item["name"] for item in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    normalized: dict = {}
    for column in columns:
        source_key = column.removesuffix("_json") if column.endswith("_json") else column
        if source_key not in row and column not in row:
            continue
        value = row.get(source_key, row.get(column))
        if column.endswith("_json") and not isinstance(value, str):
            value = json.dumps(value or [], ensure_ascii=False)
        normalized[column] = value
    now = utc_now()
    if "created_at" in columns and "created_at" not in normalized:
        normalized["created_at"] = now
    if "updated_at" in columns and "updated_at" not in normalized:
        normalized["updated_at"] = now
    if not normalized.get("id"):
        raise ValueError(f"{table} 中存在缺少 id 的记录")
    return normalized


def import_tables(tables: dict[str, list[dict]], mode: str) -> dict:
    unknown = set(tables) - set(EXPORT_TABLES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"包含不支持的数据表：{', '.join(sorted(unknown))}")
    backup = create_database_backup("before-import")
    counts: dict[str, int] = {}
    try:
        with transaction() as connection:
            for table, rows in tables.items():
                counts[table] = 0
                for source_row in rows:
                    row = normalize_import_row(connection, table, source_row)
                    columns = list(row)
                    placeholders = ",".join("?" for _ in columns)
                    if mode == "merge":
                        updates = ",".join(f"{column}=excluded.{column}" for column in columns if column != "id")
                        sql = (
                            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {updates}"
                            if updates else f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                        )
                    else:
                        sql = f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                    result = connection.execute(sql, tuple(row[column] for column in columns))
                    counts[table] += max(result.rowcount, 0)
    except (sqlite3.DatabaseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"导入失败：{exc}") from exc
    return {"imported": counts, "mode": mode, "safety_backup": backup.name}


def comparable_row(row: dict) -> str:
    filtered = {key: value for key, value in row.items() if key not in {"created_at", "updated_at"}}
    return json.dumps(filtered, ensure_ascii=False, sort_keys=True, default=str)




def secret_warning() -> str | None:
    """Warn when WORKBENCH_SECRET is unset (ephemeral machine key)."""
    if os.environ.get("WORKBENCH_SECRET"):
        return None
    return "未设置 WORKBENCH_SECRET，密钥派生自本机特征；换机或清环境后已加密字段可能无法解密。"


# Fail-lock for access password (in-memory, single-user)
_ACCESS_FAILS: dict[str, list[float]] = {}
ACCESS_FAIL_LIMIT = 5
ACCESS_FAIL_WINDOW_SEC = 300
ACCESS_LOCK_SEC = 600


def access_fail_key(request_client: str | None) -> str:
    return request_client or "local"


def access_is_locked(client: str | None) -> tuple[bool, int]:
    key = access_fail_key(client)
    now = time.time()
    stamps = [t for t in _ACCESS_FAILS.get(key, []) if now - t < ACCESS_FAIL_WINDOW_SEC]
    _ACCESS_FAILS[key] = stamps
    if len(stamps) < ACCESS_FAIL_LIMIT:
        return False, 0
    oldest = min(stamps)
    remain = int(ACCESS_LOCK_SEC - (now - oldest))
    if remain <= 0:
        _ACCESS_FAILS[key] = []
        return False, 0
    return True, remain


def record_access_failure(client: str | None) -> None:
    key = access_fail_key(client)
    _ACCESS_FAILS.setdefault(key, []).append(time.time())


def clear_access_failures(client: str | None) -> None:
    _ACCESS_FAILS.pop(access_fail_key(client), None)


def bump_access_token_version() -> int:
    version = int(get_setting("access_token_version", 1) or 1) + 1
    set_setting("access_token_version", version)
    return version


def current_access_token_version() -> int:
    return int(get_setting("access_token_version", 1) or 1)
