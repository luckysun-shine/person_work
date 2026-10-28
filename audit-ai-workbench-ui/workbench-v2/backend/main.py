"""审计 AI 个人工作台 — FastAPI 入口（路由已拆至 routers/）。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import common as C
from .db import init_db
from . import mcp_server
from .routers import (
    access,
    calendar,
    data,
    frontend,
    models,
    notes,
    procedures,
    projects,
    reports,
    requests,
    search,
    settings,
    sql,
    tasks,
)


def _is_mcp_path(path: str) -> bool:
    return path == "/mcp" or path.startswith("/mcp/")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    C.reconcile_machine_bound_secrets()
    yield


app = FastAPI(
    title="审计 AI 个人工作台 API",
    version=C.APP_VERSION,
    description="单用户、本地优先的审计数据分析工作台。",
    lifespan=lifespan,
)


@app.middleware("http")
async def access_guard(request: Request, call_next):
    path = request.url.path
    if _is_mcp_path(path):
        if not C.mcp_token_configured():
            return JSONResponse({"detail": "未配置 WORKBENCH_MCP_TOKEN，MCP 未启用"}, status_code=503)
        provided = C.bearer_token(request.headers.get("authorization"))
        if not C.mcp_token_valid(provided):
            return JSONResponse({"detail": "MCP 需要有效的 Bearer Token"}, status_code=401)
        return await call_next(request)
    if path.startswith("/api/") and not any(path.startswith(prefix) for prefix in C.PUBLIC_API_PREFIXES):
        if C.access_password_required():
            token = request.cookies.get(C.ACCESS_COOKIE) or request.headers.get("X-Workbench-Access")
            if not C.access_token_valid(token):
                return JSONResponse({"detail": "需要访问密码"}, status_code=401)
    return await call_next(request)


for module in (
    access,
    tasks,
    reports,
    notes,
    sql,
    procedures,
    requests,
    models,
    projects,
    search,
    settings,
    calendar,
    data,
):
    app.include_router(module.router)

app.include_router(mcp_server.router)
app.include_router(frontend.router)
