"""OpenAI-compatible chat client for local workbench AI features."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx


DEFAULT_AI_SETTINGS = {
    "enabled": False,
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "",
    "timeout_seconds": 60,
    "include_sql_text": True,
    "temperature": 0.2,
}


class AINotConfigured(Exception):
    pass


class AIRequestError(Exception):
    pass


def ai_ready(settings: dict) -> bool:
    return bool(settings.get("enabled") and settings.get("base_url") and settings.get("model") and settings.get("api_key"))


def chat_completion(settings: dict, system: str, user: str, *, json_mode: bool = False) -> str:
    if not ai_ready(settings):
        raise AINotConfigured("AI 未启用或未配置完整")
    base = str(settings["base_url"]).rstrip("/")
    url = f"{base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": settings["model"],
        "temperature": float(settings.get("temperature") or 0.2),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    timeout = float(settings.get("timeout_seconds") or 60)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise AIRequestError(f"调用 AI 服务失败：{exc}") from exc
    if response.status_code >= 400:
        detail = response.text[:400]
        raise AIRequestError(f"AI 服务返回 {response.status_code}：{detail}")
    payload = response.json()
    try:
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AIRequestError("AI 响应格式不正确") from exc


def parse_json_content(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
    raise AIRequestError("无法解析 AI 返回的 JSON")


def enhance_note_assist(settings: dict, title: str, content: str, local: dict) -> dict:
    system = (
        "你是审计监察数据分析师的工作记录助手。"
        "根据标题和正文，返回 JSON："
        '{"suggested_type":"随手记录|口径说明|问题排查|模型维护|项目复盘",'
        '"suggested_tags":["标签"],"suggested_relation":"编号或null","summary":"一句话摘要","reason":"简要理由"}。'
        "不要编造未出现的事实。"
    )
    user = f"标题：{title}\n正文：{content}\n本地规则建议：{json.dumps(local, ensure_ascii=False)}"
    data = parse_json_content(chat_completion(settings, system, user, json_mode=True))
    result = dict(local)
    if data.get("suggested_type"):
        result["suggested_type"] = str(data["suggested_type"])
    if isinstance(data.get("suggested_tags"), list):
        result["suggested_tags"] = [str(item) for item in data["suggested_tags"][:8]]
    if "suggested_relation" in data:
        result["suggested_relation"] = data["suggested_relation"] or None
    if data.get("reason"):
        result["reason"] = f"AI：{data['reason']}"
    if data.get("summary"):
        result["ai_summary"] = str(data["summary"])
    result["ai_generated"] = True
    result["confidence"] = max(int(result.get("confidence") or 50), 70)
    return result


def enhance_sql_assist(settings: dict, name: str, sql_text: str, local: dict, include_sql: bool) -> dict:
    system = (
        "你是审计数据分析 SQL 资产助手。返回 JSON："
        '{"purpose":"用途说明","tables":["表"],"tags":["标签"],"parameters":["参数"],'
        '"risk_level":"low|medium|high","risk_notes":["风险"],"validation_note":"验证建议"}。'
        "用途说明需标明结果供人工复核，不直接形成审计结论。明确标记分析依据。"
    )
    sql_part = sql_text if include_sql else "（用户选择不发送 SQL 正文，仅根据名称与本地解析结果增强）"
    user = (
        f"名称：{name}\nSQL：\n{sql_part}\n"
        f"本地解析：{json.dumps({k: local[k] for k in ('operation','tables','parameters','risk_notes','tags') if k in local}, ensure_ascii=False)}"
    )
    data = parse_json_content(chat_completion(settings, system, user, json_mode=True))
    result = dict(local)
    for key in ("purpose", "validation_note", "risk_level"):
        if data.get(key):
            result[key] = str(data[key])
    for key in ("tables", "tags", "parameters", "risk_notes"):
        if isinstance(data.get(key), list):
            result[key] = [str(item) for item in data[key][:30]]
    result["ai_generated"] = True
    return result


def enhance_weekly_report(settings: dict, draft: dict) -> dict:
    system = (
        "你是审计监察数据分析师的周报助手。基于提供的真实工作数据润色周报草稿，"
        "返回 JSON：{\"title\",\"executive_summary\",\"highlights\",\"risks\",\"next_week_plan\"}。"
        "不得虚构未提供的完成事项；可整理措辞与结构；保留可追溯编号。"
    )
    user = json.dumps(
        {
            "title": draft.get("title"),
            "executive_summary": draft.get("executive_summary"),
            "highlights": draft.get("highlights"),
            "risks": draft.get("risks"),
            "next_week_plan": draft.get("next_week_plan"),
            "metrics": draft.get("metrics"),
            "source_snapshot": {
                k: draft.get("source_snapshot", {}).get(k)
                for k in ("week_start", "week_end", "task_ids", "request_ids", "note_ids")
            },
        },
        ensure_ascii=False,
    )
    data = parse_json_content(chat_completion(settings, system, user, json_mode=True))
    result = dict(draft)
    for key in ("title", "executive_summary", "highlights", "risks", "next_week_plan"):
        if data.get(key):
            result[key] = str(data[key])
    snapshot = dict(result.get("source_snapshot") or {})
    snapshot["ai_enhanced"] = True
    result["source_snapshot"] = snapshot
    return result
