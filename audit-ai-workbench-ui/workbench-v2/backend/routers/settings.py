"""API routes: settings."""

from fastapi import APIRouter, HTTPException

from .. import common as C
from ..schemas import SettingsUpdate
from ..secrets_util import encrypt_secret

router = APIRouter(tags=["settings"])

HOME_LAYOUT_DEFAULT = ["tasks", "projects", "requests", "quick"]
HOME_LAYOUT_ALLOWED = set(HOME_LAYOUT_DEFAULT)


def normalize_home_layout(value) -> list[str]:
    if not isinstance(value, list):
        return list(HOME_LAYOUT_DEFAULT)
    ordered = [str(item) for item in value if str(item) in HOME_LAYOUT_ALLOWED]
    for key in HOME_LAYOUT_DEFAULT:
        if key not in ordered:
            ordered.append(key)
    return ordered[: len(HOME_LAYOUT_DEFAULT)]


@router.get("/api/settings")
def get_settings() -> dict:
    backups = sorted(C.backup_directory().glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    latest = C.backup_info(backups[0]) if backups else None
    return {
        "backup_retention": int(C.get_setting("backup_retention", 20) or 20),
        "auto_backup_hours": int(C.get_setting("auto_backup_hours", 0) or 0),
        "last_auto_backup_at": C.get_setting("last_auto_backup_at", "") or "",
        "home_layout": normalize_home_layout(C.get_setting("home_layout", HOME_LAYOUT_DEFAULT)),
        "version": C.APP_VERSION,
        "ai": C.public_ai_settings(),
        "dingtalk_calendar": C.public_dingtalk_calendar_settings(),
        "access_password_enabled": C.access_password_required(),
        "secret_warning": C.secret_warning(),
        "session_days": C.ACCESS_SESSION_SECONDS // 86400,
        "backups": {
            "count": len(backups),
            "latest": latest,
            "retention": int(C.get_setting("backup_retention", 20) or 20),
        },
    }


@router.put("/api/settings")
def update_settings(payload: SettingsUpdate) -> dict:
    if payload.backup_retention is not None:
        C.set_setting("backup_retention", payload.backup_retention)
        C.prune_backups(payload.backup_retention)
    if payload.auto_backup_hours is not None:
        C.set_setting("auto_backup_hours", payload.auto_backup_hours)
    if payload.home_layout is not None:
        C.set_setting("home_layout", normalize_home_layout(payload.home_layout))
    if payload.ai is not None:
        current = C.load_ai_settings()
        updates = payload.ai.model_dump(exclude_unset=True)
        if updates.pop("clear_api_key", False):
            current["api_key"] = ""
        if "api_key" in updates:
            key = updates.pop("api_key") or ""
            current["api_key"] = key
        current.update({k: v for k, v in updates.items() if v is not None})
        stored = dict(current)
        stored["api_key"] = encrypt_secret(current.get("api_key") or "")
        C.set_setting("ai", stored)
    if payload.dingtalk_calendar is not None:
        current = C.load_dingtalk_calendar_settings()
        updates = payload.dingtalk_calendar.model_dump(exclude_unset=True)
        if updates.pop("clear_app_secret", False):
            current["app_secret"] = ""
        if "app_secret" in updates:
            secret = updates.pop("app_secret") or ""
            current["app_secret"] = secret
        if updates.pop("clear_caldav_password", False):
            current["caldav_password"] = ""
        if "caldav_password" in updates:
            secret = updates.pop("caldav_password") or ""
            if secret.strip():
                current["caldav_password"] = secret
        current.update({k: v for k, v in updates.items() if v is not None})
        stored = dict(current)
        stored["app_secret"] = encrypt_secret(current.get("app_secret") or "")
        stored["caldav_password"] = encrypt_secret(current.get("caldav_password") or "")
        C.set_setting("dingtalk_calendar", stored)
    if payload.clear_access_password:
        C.set_setting("access_password_hash", "")
        C.bump_access_token_version()
    elif payload.access_password is not None:
        if not payload.access_password.strip():
            C.set_setting("access_password_hash", "")
            C.bump_access_token_version()
        else:
            password = payload.access_password.strip()
            if len(password) < 6:
                raise HTTPException(status_code=400, detail="访问密码至少 6 位")
            C.set_setting("access_password_hash", C.hash_password(password))
            C.bump_access_token_version()
    return get_settings()
