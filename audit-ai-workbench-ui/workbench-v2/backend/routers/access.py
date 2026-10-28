"""API routes: access."""

from fastapi import APIRouter, HTTPException, Request, Response

from .. import common as C
from ..schemas import AccessUnlock

router = APIRouter(tags=["access"])

@router.get("/api/health")
def health() -> dict:
    backups = sorted(C.backup_directory().glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True)
    latest = C.backup_info(backups[0]) if backups else None
    return {
        "status": "ok",
        "version": C.APP_VERSION,
        "access_required": C.access_password_required(),
        "ai_ready": C.public_ai_settings()["ready"],
        "secret_warning": C.secret_warning(),
        "mcp": {
            "enabled": C.mcp_token_configured(),
            "path": "/mcp",
            "transport": "streamable-http",
        },
        "backups": {
            "count": len(backups),
            "latest": latest,
            "retention": int(C.get_setting("backup_retention", 20) or 20),
        },
    }


@router.get("/api/access/status")
def access_status(request: Request) -> dict:
    required = C.access_password_required()
    token = request.cookies.get(C.ACCESS_COOKIE) or request.headers.get("X-Workbench-Access")
    client = request.client.host if request.client else None
    locked, remain = C.access_is_locked(client)
    return {
        "required": required,
        "unlocked": (not required) or C.access_token_valid(token),
        "expires_at": C.access_token_expires_at(token),
        "session_days": C.ACCESS_SESSION_SECONDS // 86400,
        "locked": locked,
        "lock_remaining_seconds": remain if locked else 0,
    }


@router.post("/api/access/unlock")
def access_unlock(payload: AccessUnlock, request: Request, response: Response) -> dict:
    stored = C.get_setting("access_password_hash", "") or ""
    if not stored:
        return {"unlocked": True, "required": False}
    client = request.client.host if request.client else None
    locked, remain = C.access_is_locked(client)
    if locked:
        raise HTTPException(status_code=429, detail=f"尝试过多，请 {remain} 秒后再试")
    if not C.verify_password(payload.password, stored):
        C.record_access_failure(client)
        locked_now, remain_now = C.access_is_locked(client)
        if locked_now:
            raise HTTPException(status_code=429, detail=f"尝试过多，请 {remain_now} 秒后再试")
        raise HTTPException(status_code=401, detail="访问密码不正确")
    C.clear_access_failures(client)
    token = C.issue_access_token()
    response.set_cookie(C.ACCESS_COOKIE, token, httponly=True, samesite="lax", max_age=C.ACCESS_SESSION_SECONDS)
    return {
        "unlocked": True,
        "required": True,
        "token": token,
        "expires_at": C.access_token_expires_at(token),
        "session_days": C.ACCESS_SESSION_SECONDS // 86400,
    }


@router.post("/api/access/lock")
def access_lock(response: Response) -> dict:
    response.delete_cookie(C.ACCESS_COOKIE)
    return {"unlocked": False, "required": C.access_password_required()}

