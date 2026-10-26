"""Calendar subscription sync: ICS feeds and CalDAV (DingTalk-oriented)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
NS = {"D": DAV, "C": CALDAV}


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
                "external_id": fields.get("UID") or f"{fields.get('SUMMARY', 'event')}-{start_at}",
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
    headers = {"User-Agent": "AuditAI-Workbench/1.7"}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"拉取 ICS 失败：HTTP {response.status_code}")
    return response.text


def _normalize_caldav_base(url: str) -> str:
    value = (url or "").strip()
    if not value:
        value = "https://calendar.dingtalk.com"
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    return value.rstrip("/")


def _join_url(base: str, path: str) -> str:
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path.rstrip("/")
    return urljoin(base.rstrip("/") + "/", path.lstrip("/")).rstrip("/")


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _caldav_request(
    method: str,
    url: str,
    *,
    auth: tuple[str, str],
    body: str = "",
    depth: str | None = "1",
    timeout: float = 45,
) -> httpx.Response:
    headers = {
        "User-Agent": "AuditAI-Workbench/1.7",
        "Content-Type": "application/xml; charset=utf-8",
        "Accept": "application/xml, text/xml, */*",
    }
    if depth is not None:
        headers["Depth"] = depth
    with httpx.Client(timeout=timeout, follow_redirects=True, auth=auth) as client:
        response = client.request(method, url, content=body.encode("utf-8") if body else None, headers=headers)
    return response


def _parse_multistatus(xml_text: str) -> list[dict[str, Any]]:
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"CalDAV 响应无法解析：{exc}") from exc
    items: list[dict[str, Any]] = []
    for response in root.iter():
        if _local_name(response.tag) != "response":
            continue
        href = ""
        displayname = ""
        is_calendar = False
        calendar_data = ""
        status = ""
        for child in response.iter():
            name = _local_name(child.tag)
            if name == "href" and not href:
                href = _text(child)
            elif name == "displayname":
                displayname = _text(child)
            elif name == "calendar":
                is_calendar = True
            elif name == "calendar-data":
                calendar_data = "".join(child.itertext()).strip()
            elif name == "status" and not status:
                status = _text(child)
        if href:
            items.append(
                {
                    "href": href,
                    "displayname": displayname,
                    "is_calendar": is_calendar,
                    "calendar_data": calendar_data,
                    "status": status,
                }
            )
    return items


def _absolute_href(base: str, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return urljoin(origin + "/", href.lstrip("/"))


def _candidate_homes(base: str, username: str) -> list[str]:
    user = username.strip().strip("/")
    candidates = [
        f"{base}/dav/{user}/",
        f"{base}/dav/users/{user}/",
        f"{base}/dav/{user}/primary/",
        f"{base}/dav/",
        f"{base}/",
    ]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        key = item.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def discover_caldav_calendars(base: str, username: str, password: str) -> list[str]:
    auth = (username, password)
    found: list[str] = []
    errors: list[str] = []

    propfind_body = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:displayname/>
    <D:resourcetype/>
    <C:calendar-home-set/>
    <D:current-user-principal/>
  </D:prop>
</D:propfind>
"""

    for home in _candidate_homes(base, username):
        try:
            response = _caldav_request("PROPFIND", home, auth=auth, body=propfind_body, depth="1")
        except httpx.HTTPError as exc:
            errors.append(f"{home} 网络错误：{exc}")
            continue
        if response.status_code in {401, 403}:
            raise RuntimeError("CalDAV 认证失败，请检查用户名与密码（钉钉生成的 CalDAV 专用密码）")
        if response.status_code >= 400:
            errors.append(f"{home} HTTP {response.status_code}")
            continue
        for item in _parse_multistatus(response.text):
            href = _absolute_href(base, item["href"])
            if item["is_calendar"]:
                found.append(href if href.endswith("/") else href + "/")
            # Follow calendar-home-set / principal if present via nested props is already covered by Depth:1 on candidates.

    # Unique preserve order
    unique: list[str] = []
    seen: set[str] = set()
    for href in found:
        key = href.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        unique.append(href)

    if unique:
        return unique

    # Last resort: treat candidate "primary" style paths as calendars even if PROPFIND did not mark them.
    for home in _candidate_homes(base, username):
        if home.rstrip("/").endswith("primary"):
            unique.append(home if home.endswith("/") else home + "/")
            break
    if unique:
        return unique

    detail = "；".join(errors[:3]) if errors else "未返回日历集合"
    raise RuntimeError(f"未能发现 CalDAV 日历。{detail}")


def report_caldav_events(calendar_url: str, username: str, password: str, *, date_from: date, date_to: date) -> list[str]:
    start = date_from.strftime("%Y%m%dT000000Z")
    end = (date_to + timedelta(days=1)).strftime("%Y%m%dT000000Z")
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}" end="{end}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>
"""
    response = _caldav_request("REPORT", calendar_url, auth=(username, password), body=body, depth="1")
    if response.status_code in {401, 403}:
        raise RuntimeError("CalDAV 认证失败，请检查用户名与密码")
    if response.status_code >= 400:
        raise RuntimeError(f"CalDAV 查询失败：HTTP {response.status_code}")
    payloads = []
    for item in _parse_multistatus(response.text):
        if item.get("calendar_data"):
            payloads.append(item["calendar_data"])
    # Some servers return raw ICS instead of multistatus.
    if not payloads and "BEGIN:VCALENDAR" in (response.text or ""):
        payloads.append(response.text)
    return payloads


def fetch_caldav_events(
    *,
    url: str,
    username: str,
    password: str,
    calendar_path: str = "",
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    if not username.strip() or not password.strip():
        raise RuntimeError("请填写 CalDAV 用户名和密码")
    base = _normalize_caldav_base(url)
    if calendar_path.strip():
        calendars = [_join_url(base, calendar_path.strip())]
        calendars = [item if item.endswith("/") else item + "/" for item in calendars]
    else:
        calendars = discover_caldav_calendars(base, username.strip(), password)

    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    last_error = ""
    for calendar_url in calendars:
        try:
            payloads = report_caldav_events(
                calendar_url,
                username.strip(),
                password,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception as exc:  # noqa: BLE001 - collect and continue other calendars
            last_error = str(exc)
            continue
        for text in payloads:
            for event in parse_ics_events(text, date_from=date_from, date_to=date_to):
                key = event["external_id"]
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                events.append(event)
    if not events and last_error:
        raise RuntimeError(last_error)
    return events


def sync_subscription_events(
    *,
    provider: str,
    ics_url: str,
    dingtalk_settings: dict,
    date_from: date,
    date_to: date,
    config: dict | None = None,
) -> list[dict[str, Any]]:
    config = config or {}
    provider = (provider or "ics").strip().lower()

    if provider in {"ics", "dingtalk"} and (ics_url or "").strip():
        text = fetch_ics(ics_url.strip())
        return parse_ics_events(text, date_from=date_from, date_to=date_to)

    if provider == "caldav" or (provider == "dingtalk" and not (ics_url or "").strip()):
        url = (
            (config.get("url") or "").strip()
            or (dingtalk_settings.get("caldav_url") or "").strip()
            or "https://calendar.dingtalk.com"
        )
        username = (config.get("username") or dingtalk_settings.get("caldav_username") or "").strip()
        password = (
            (config.get("password") or "").strip()
            or (dingtalk_settings.get("caldav_password") or "").strip()
        )
        calendar_path = (
            (config.get("calendar_path") or "").strip()
            or (dingtalk_settings.get("caldav_path") or "").strip()
            or (dingtalk_settings.get("calendar_id") or "").strip()
        )
        return fetch_caldav_events(
            url=url,
            username=username,
            password=password,
            calendar_path=calendar_path,
            date_from=date_from,
            date_to=date_to,
        )

    if provider == "dingtalk":
        raise RuntimeError(
            "钉钉日程请改用 CalDAV：在钉钉日历设置中获取账号/密码/服务器，"
            "填入本页 CalDAV 配置后同步。"
        )
    raise RuntimeError(f"不支持的日历类型：{provider}")


def window_for_settings(settings: dict) -> tuple[date, date]:
    today = date.today()
    back = int(settings.get("sync_days_back") or 7)
    forward = int(settings.get("sync_days_forward") or 21)
    return today - timedelta(days=back), today + timedelta(days=forward)
