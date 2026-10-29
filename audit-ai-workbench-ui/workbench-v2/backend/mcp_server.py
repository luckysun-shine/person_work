"""Remote MCP (Streamable HTTP) for Grok Bot / Cursor. Endpoint: POST /mcp."""
from __future__ import annotations

import inspect
import json
from datetime import date, timedelta
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import ValidationError

from . import common as C
from .routers import calendar as calendar_routes
from .routers import notes as notes_routes
from .routers import projects as project_routes
from .routers import requests as request_routes
from .routers import search as search_routes
from .routers import tasks as task_routes
from .schemas import NoteCreate, TaskCreate, TaskUpdate

router = APIRouter(tags=["mcp"])

PROTOCOL_VERSION = "2025-03-26"
INSTRUCTIONS = (
    "这是个人审监数据分析工作台的 MCP。先用 get_today 或 get_week_plan 了解当前工作，"
    "再用 search_workbench 检索。不要索取或复述 SQL 正文、备份、密码或密钥。"
    "写入仅限 create_task、complete_task、add_note。"
)


def _clip(value, limit: int = 400):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _pick(item: dict | None, keys: tuple[str, ...]) -> dict:
    if not item:
        return {}
    return {key: item.get(key) for key in keys}


def _public_task(task: dict) -> dict:
    payload = _pick(task, (
        "id", "title", "status", "priority", "planned_date", "due_at", "type",
        "notes", "waiting_on", "related_entity_type", "related_entity_id",
        "is_overdue", "overdue_days", "needs_nudge", "nudge_reason", "bucket",
    ))
    payload["notes"] = _clip(payload.get("notes"), 280)
    return payload


def _public_request(item: dict) -> dict:
    payload = _pick(item, (
        "id", "title", "status", "purpose", "requester", "department",
        "created_at", "updated_at", "current_version",
    ))
    payload["purpose"] = _clip(payload.get("purpose"), 280)
    return payload


def _public_project(item: dict) -> dict:
    models = [
        _pick(model, ("id", "name", "status", "current_version", "pending_review_count"))
        for model in (item.get("linked_models") or [])[:8]
    ]
    return {
        **_pick(item, (
            "id", "name", "category", "status", "next_action", "pending_steps",
            "model_count", "model_attention",
        )),
        "goal": _clip(item.get("goal"), 240),
        "linked_models": models,
        "needs_attention": bool(item.get("model_attention") or item.get("pending_steps")),
    }


def _public_note(note: dict, *, include_body: bool = False) -> dict:
    payload = _pick(note, ("id", "type", "title", "tags", "related_entity_type", "related_entity_id", "updated_at"))
    if include_body:
        payload["content"] = _clip(note.get("content"), 4000)
    else:
        payload["excerpt"] = _clip(note.get("content"), 180)
    return payload


def _public_event(event: dict) -> dict:
    return _pick(event, ("id", "title", "start_at", "end_at", "all_day", "location"))


def _week_bounds(focus: date | None = None) -> tuple[date, date]:
    target = focus or date.today()
    start = target - timedelta(days=target.weekday())
    return start, start + timedelta(days=6)


def get_today() -> dict:
    """今日焦点：待办、逾期、催办摘要。查看当天该做什么时优先调用。"""
    focus = task_routes.task_focus()
    summary = focus.get("summary") or {}
    return {
        "date": summary.get("focus_date") or date.today().isoformat(),
        "summary": summary,
        "nudges": [_public_task(task) for task in (focus.get("nudges") or [])],
        "tasks": [_public_task(task) for task in (focus.get("tasks") or [])],
    }


def get_week_plan() -> dict:
    """本周一至周日的任务和日历日程。"""
    start, end = _week_bounds()
    tasks = [
        _public_task(task)
        for task in task_routes.list_tasks(date_from=start.isoformat(), date_to=end.isoformat())
    ]
    events = [
        _public_event(event)
        for event in calendar_routes.list_calendar_events(date_from=start.isoformat(), date_to=end.isoformat())
    ]
    days = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        days.append({
            "date": iso,
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][cursor.weekday()],
            "tasks": [task for task in tasks if task.get("planned_date") == iso],
            "events": [event for event in events if str(event.get("start_at") or "")[:10] == iso],
        })
        cursor += timedelta(days=1)
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "task_count": len(tasks),
        "event_count": len(events),
        "days": days,
    }


def search_workbench(query: str, types: str | None = None) -> dict:
    """跨任务、请求、台账、记录、SQL 资产名称检索。types 为逗号分隔，例如 task,project,note。"""
    keyword = str(query or "").strip()
    if len(keyword) < 1:
        return {"query": "", "total": 0, "results": []}
    if isinstance(types, (list, tuple)):
        types = ",".join(str(item).strip() for item in types if str(item).strip()) or None
    elif types is not None:
        types = str(types).strip() or None
    payload = search_routes.unified_search(q=keyword[:100], types=types)
    results = [
        {
            "entity_type": item.get("entity_type"),
            "id": item.get("id"),
            "title": item.get("title"),
            "subtitle": _clip(item.get("subtitle"), 160),
            "view": item.get("view"),
            "updated_at": item.get("updated_at"),
        }
        for item in (payload.get("results") or [])
    ]
    return {"query": payload.get("query"), "total": payload.get("total") or 0, "results": results[:40]}


def get_ledger_attention() -> dict:
    """待关注的审监监测台账：模型待更新/待复核，或仍有未完成更新步骤。"""
    items = project_routes.list_projects()
    attention = [_public_project(item) for item in items if item.get("model_attention") or item.get("pending_steps")]
    return {"count": len(attention), "items": attention}


def get_open_requests() -> dict:
    """进行中的数据请求（不含已交付、已归档）。不返回 SQL 正文。"""
    items = [
        _public_request(item)
        for item in request_routes.list_data_requests()
        if item.get("status") not in ("done", "archived")
    ]
    return {"count": len(items), "items": items[:40]}


def get_task(task_id: str) -> dict:
    """按编号查看一条任务。"""
    return _public_task(task_routes.get_task(str(task_id).strip()))


def get_note(note_id: str) -> dict:
    """按编号查看一条工作记录（正文截断，不含修订历史）。"""
    note = notes_routes.get_note(str(note_id).strip())
    note.pop("revisions", None)
    return _public_note(note, include_body=True)


def get_project(project_id: str) -> dict:
    """按编号查看监管项摘要：下一步、待办步骤、绑定模型。不含规划原文和代码备份。"""
    detail = project_routes.get_project(str(project_id).strip())
    project = _public_project(detail.get("project") or {})
    project["tasks"] = [_public_task(task) for task in (detail.get("tasks") or [])[:12]]
    project["open_requests"] = [
        _public_request(item)
        for item in (detail.get("requests") or [])
        if item.get("status") not in ("done", "archived")
    ][:8]
    project["pending_step_titles"] = [
        _clip(step.get("title") or step.get("name") or step.get("content"), 80)
        for step in (detail.get("update_steps") or [])
        if step.get("status") != "done"
    ][:12]
    return project


def create_task(title: str, planned_date: str | None = None, priority: str = "medium", notes: str = "") -> dict:
    """新建一条周计划任务。planned_date 用 YYYY-MM-DD，缺省为今天。"""
    payload = TaskCreate(
        title=str(title or "").strip(),
        planned_date=(str(planned_date).strip() if planned_date else "") or date.today().isoformat(),
        priority=priority if str(priority or "") in ("low", "medium", "high") else "medium",
        notes=str(notes or ""),
    )
    return _public_task(task_routes.create_task(payload))


def complete_task(task_id: str, completion_result: str = "") -> dict:
    """将任务标记为已完成。"""
    payload = TaskUpdate(status="done")
    result = str(completion_result or "").strip()
    if result:
        payload.completion_result = result
    return _public_task(task_routes.update_task(str(task_id).strip(), payload))


def add_note(title: str, content: str = "", note_type: str = "随手记录") -> dict:
    """新增一条工作记录。"""
    payload = NoteCreate(
        title=str(title or "").strip(),
        content=str(content or ""),
        type=(str(note_type or "").strip() or "随手记录"),
    )
    return _public_note(notes_routes.create_note(payload), include_body=True)


def _schema_for(func: Callable) -> dict:
    properties: dict[str, Any] = {}
    required: list[str] = []
    hints = {
        "query": "检索关键词",
        "types": "可选，逗号分隔的类型：task,project,note,data_request,sql_asset",
        "task_id": "任务编号，如 T-001",
        "note_id": "工作记录编号，如 N-001",
        "project_id": "监管项编号，如 P-001",
        "title": "标题",
        "planned_date": "计划日期 YYYY-MM-DD，缺省今天",
        "priority": "low / medium / high",
        "notes": "备注",
        "content": "记录正文",
        "note_type": "记录类型：随手记录 / 口径说明 / 底表信息 / 问题排查 / 模型维护 / 项目复盘，默认随手记录",
        "completion_result": "完成说明",
    }
    signature = inspect.signature(func)
    for name, param in signature.parameters.items():
        schema: dict[str, Any] = {"type": "string", "description": hints.get(name, name)}
        if param.default is inspect.Parameter.empty:
            required.append(name)
        elif param.default is None:
            schema["description"] += "（可选）"
        else:
            schema["description"] += f"（默认 {param.default}）"
        properties[name] = schema
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS: dict[str, Callable] = {
    "get_today": get_today,
    "get_week_plan": get_week_plan,
    "search_workbench": search_workbench,
    "get_ledger_attention": get_ledger_attention,
    "get_open_requests": get_open_requests,
    "get_task": get_task,
    "get_note": get_note,
    "get_project": get_project,
    "create_task": create_task,
    "complete_task": complete_task,
    "add_note": add_note,
}


def _tool_list() -> list[dict]:
    items = []
    for name, func in TOOLS.items():
        items.append({
            "name": name,
            "description": (inspect.getdoc(func) or name).strip(),
            "inputSchema": _schema_for(func),
        })
    return items


def _normalize_arguments(func: Callable, arguments: dict | None) -> dict:
    incoming = arguments if isinstance(arguments, dict) else {}
    kwargs: dict[str, Any] = {}
    for name in inspect.signature(func).parameters:
        if name not in incoming:
            continue
        value = incoming[name]
        if value is None:
            continue
        if name == "types" and isinstance(value, (list, tuple)):
            value = ",".join(str(item).strip() for item in value if str(item).strip())
            if not value:
                continue
        elif not isinstance(value, str):
            value = str(value)
        kwargs[name] = value
    return kwargs


def _call_tool(name: str, arguments: dict | None) -> dict:
    func = TOOLS.get(name)
    if not func:
        return {"content": [{"type": "text", "text": f"未知工具：{name}"}], "isError": True}
    try:
        result = func(**_normalize_arguments(func, arguments))
        text = json.dumps(result, ensure_ascii=False, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except HTTPException as exc:
        return {"content": [{"type": "text", "text": str(exc.detail)}], "isError": True}
    except (TypeError, ValidationError) as exc:
        return {"content": [{"type": "text", "text": f"参数不正确：{exc}"}], "isError": True}
    except Exception as exc:
        return {"content": [{"type": "text", "text": f"调用失败：{exc}"}], "isError": True}


def _rpc_result(request_id, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_rpc(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if method == "initialize":
        return _rpc_result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "数智审监工作台", "version": C.APP_VERSION},
            "instructions": INSTRUCTIONS,
        })
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return None
    if method == "ping":
        return _rpc_result(request_id, {})
    if method == "tools/list":
        return _rpc_result(request_id, {"tools": _tool_list()})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        return _rpc_result(request_id, _call_tool(name, arguments))
    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return _rpc_result(request_id, {key: []})
    if request_id is None:
        return None
    return _rpc_error(request_id, -32601, f"不支持的方法：{method}")


def _wants_sse(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept and "application/json" not in accept


def _mcp_response(request: Request, payload: dict | None, *, notification: bool = False) -> Response:
    if notification or payload is None:
        return Response(status_code=202)
    if _wants_sse(request):
        body = f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        return PlainTextResponse(body, media_type="text/event-stream")
    return JSONResponse(payload)


@router.api_route("/mcp", methods=["POST", "GET"], include_in_schema=False)
@router.api_route("/mcp/", methods=["POST", "GET"], include_in_schema=False)
async def mcp_endpoint(request: Request):
    if request.method == "GET":
        return JSONResponse({
            "name": "数智审监工作台",
            "version": C.APP_VERSION,
            "transport": "streamable-http",
            "hint": "使用 POST JSON-RPC（initialize / tools/list / tools/call）。",
        })
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "请求不是合法 JSON"), status_code=400)
    if isinstance(payload, list):
        replies = [handle_rpc(item) for item in payload if isinstance(item, dict)]
        replies = [item for item in replies if item is not None]
        if not replies:
            return Response(status_code=202)
        return _mcp_response(request, replies)
    if not isinstance(payload, dict):
        return JSONResponse(_rpc_error(None, -32600, "请求格式不正确"), status_code=400)
    reply = handle_rpc(payload)
    return _mcp_response(request, reply, notification=payload.get("id") is None and reply is None)
