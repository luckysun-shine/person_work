"""API routes: frontend."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..db import PROJECT_DIR

router = APIRouter(tags=["frontend"])

@router.get("/styles.css", include_in_schema=False)
def styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "styles.css", media_type="text/css")


@router.get("/ui-apple-hig.css", include_in_schema=False)
def apple_hig_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "ui-apple-hig.css", media_type="text/css")


@router.get("/ui-soft-welcome.css", include_in_schema=False)
def soft_welcome_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "ui-soft-welcome.css", media_type="text/css")


@router.get("/app.js", include_in_schema=False)
def javascript() -> FileResponse:
    return FileResponse(PROJECT_DIR / "app.js", media_type="application/javascript")


@router.get("/prototype-apple-hig.css", include_in_schema=False)
def apple_hig_prototype_styles() -> FileResponse:
    return FileResponse(PROJECT_DIR / "prototype-apple-hig.css", media_type="text/css")


@router.get("/prototype-apple-hig.js", include_in_schema=False)
def apple_hig_prototype_javascript() -> FileResponse:
    return FileResponse(PROJECT_DIR / "prototype-apple-hig.js", media_type="application/javascript")


@router.get("/prototype/apple-hig", include_in_schema=False)
def apple_hig_prototype() -> FileResponse:
    return FileResponse(PROJECT_DIR / "prototype-apple-hig.html")


@router.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(PROJECT_DIR / "index.html")


@router.get("/{path:path}", include_in_schema=False)
def frontend_fallback(path: str) -> FileResponse:
    if path.startswith("api/") or Path(path).suffix:
        raise HTTPException(status_code=404, detail="资源不存在")
    return FileResponse(PROJECT_DIR / "index.html")
