"""Calendar subscription sync: ICS feeds and DingTalk-oriented config."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import unquote

import httpx


def _unfold_ics(text: str) -> str:
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_ics_datetime(value: str) -> tuple[str, bool]:
    raw = value.strip()
    all_day = "T" not in raw
    if raw.endswith("Z"):
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone().isoformat(timespec="seconds"), False
    if "T" in raw:
        dt = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
        return dt.isoformat(timespec="seconds"), False
    dt = datetime.strptime(raw[:8], "%Y%m%d")
    return dt.date().isoformat(), True


def parse_ics_events(text: str, *, date_from: date, date_to: date) -> list[dict[str, Any]]:
    content = _unfold_ics(text)
    events: list[dict[str, Any]] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, flags=re.DOTALL | re.IGNORECASE):
        fields: dict[str, str] = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0].upper()
            fields[key] = value.strip()
        if "DTSTART" not in fields:
            continue
        start_at, all_day = _parse_ics_datetime(fields["DTSTART"])
        end_at = None
        if "DTEND" in fields:
            end_at, end_all_day = _parse_ics_datetime(fields["DTEND"])
            all_day = all_day or end_all_day
        start_day = start_at[:10]
        if start_day < date_from.isoformat() or start_day > date_to.isoformat():
            continue
        events.append(
            {
                "external_id": fields.get("UID") or f"{fields.get('SUMMARY','event')}-{start_at}",
                "title": _unescape(fields.get("SUMMARY") or "未命名日程"),
                "description": _unescape(fields.get("DESCRIPTION") or ""),
                "location": _unescape(fields.get("LOCATION") or ""),
                "start_at": start_at,
                "end_at": end_at,
                "all_day": 1 if all_day else 0,
                "raw": fields,
            }
        )
    return events


def fetch_ics(url: str, timeout: float = 30) -> str:
    headers = {"User-Agent": "AuditAI-Workbench/1.6"}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"拉取 ICS 失败：HTTP {response.status_code}")
    return response.text


def sync_subscription_events(
    *,
    provider: str,
    ics_url: str,
    dingtalk_settings: dict,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    if provider == "ics" or (provider == "dingtalk" and ics_url):
        if not ics_url.strip():
            raise RuntimeError("请先配置 ICS 订阅地址")
        text = fetch_ics(ics_url.strip())
        return parse_ics_events(text, date_from=date_from, date_to=date_to)
    if provider == "dingtalk":
        # DingTalk personal calendars are commonly exposed via ICS export URL.
        # OpenAPI sync requires enterprise app credentials and calendar scopes;
        # keep ICS as the supported path and surface a clear error otherwise.
        raise RuntimeError(
            "钉钉日程请使用日历导出的 ICS 订阅地址（钉钉日历 → 订阅 → 复制链接）。"
            "企业开放平台直连接口将在后续版本补充。"
        )
    raise RuntimeError(f"不支持的日历类型：{provider}")


def window_for_settings(settings: dict) -> tuple[date, date]:
    today = date.today()
    back = int(settings.get("sync_days_back") or 7)
    forward = int(settings.get("sync_days_forward") or 21)
    return today - timedelta(days=back), today + timedelta(days=forward)
