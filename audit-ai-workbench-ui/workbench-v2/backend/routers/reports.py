"""API routes: reports."""
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import difflib
import io
import json
import re
import sqlite3
import time

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from .. import common as C
from ..ai_client import (
    AINotConfigured,
    AIRequestError,
    ai_ready,
    enhance_note_assist,
    enhance_sql_assist,
    enhance_weekly_report,
)
from ..calendar_sync import sync_subscription_events, window_for_settings
from ..db import PROJECT_DIR, connect, init_db, new_id, row_to_dict, transaction, utc_now
from ..report_exports import report_docx, report_markdown, report_pdf
from ..schemas import (
    AccessUnlock,
    BatchIds,
    BatchRequestStatus,
    BatchSqlStatus,
    BatchTaskCopy,
    CalendarSubscriptionCreate,
    CalendarSubscriptionUpdate,
    CsvImportPayload,
    DataImportPayload,
    DataRequestCreate,
    DataRequestUpdate,
    GenericReportGenerate,
    GenericReportUpsert,
    ModelCreate,
    ModelRunCreate,
    ModelUpdate,
    NavigationCreate,
    NavigationUpdate,
    NoteCreate,
    NoteAssistRequest,
    NoteUpdate,
    ProjectCreate,
    ProjectRelationCreate,
    ProjectTemplateCreate,
    ProjectTemplateUpdate,
    ProjectUpdate,
    ProcedureCreate,
    ProcedureDeploymentCreate,
    ProcedureUpdate,
    ReportTemplateCreate,
    ReportTemplateImport,
    ReportTemplateUpdate,
    SavedSearchCreate,
    SavedSearchUpdate,
    SettingsUpdate,
    SqlAssetCreate,
    SqlAssetUpdate,
    SqlAssistRequest,
    SqlVersionCreate,
    TableRestorePayload,
    TaskCreate,
    TaskUpdate,
    WeekReviewUpsert,
    WeeklyReportUpsert,
)
from ..secrets_util import decrypt_secret, encrypt_secret, mask_secret

router = APIRouter(tags=["reports"])

def parse_week_start(week_start: str) -> date:
    try:
        value = date.fromisoformat(week_start)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="周开始日期格式不正确") from exc
    if value.weekday() != 0:
        raise HTTPException(status_code=400, detail="周开始日期必须是周一")
    return value


def bullet_text(items: list[str], fallback: str) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else f"- {fallback}"


def generate_weekly_report(week_start: str) -> dict:
    start = parse_week_start(week_start)
    end = start + timedelta(days=6)
    next_start = start + timedelta(days=7)
    next_end = start + timedelta(days=13)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    tasks = C.fetch_all(
        "SELECT * FROM tasks WHERE planned_date BETWEEN ? AND ? ORDER BY planned_date, sort_order",
        (start_iso, end_iso),
    )
    next_tasks = C.fetch_all(
        "SELECT * FROM tasks WHERE planned_date BETWEEN ? AND ? ORDER BY planned_date, sort_order",
        (next_start.isoformat(), next_end.isoformat()),
    )
    requests = C.fetch_all(
        """SELECT * FROM data_requests
        WHERE substr(created_at, 1, 10) BETWEEN ? AND ? OR due_at BETWEEN ? AND ?
        ORDER BY updated_at DESC""",
        (start_iso, end_iso, start_iso, end_iso),
    )
    model_runs = C.fetch_all(
        """SELECT r.*, m.name AS model_name FROM model_runs r
        JOIN monitoring_models m ON m.id = r.model_id
        WHERE substr(r.started_at, 1, 10) BETWEEN ? AND ? ORDER BY r.started_at DESC""",
        (start_iso, end_iso),
    )
    notes = C.fetch_all(
        "SELECT * FROM work_notes WHERE substr(created_at, 1, 10) BETWEEN ? AND ? ORDER BY created_at DESC",
        (start_iso, end_iso),
    )
    projects = C.fetch_all(
        "SELECT * FROM projects WHERE status = 'active' ORDER BY progress DESC"
    )
    models = C.fetch_all(
        "SELECT * FROM monitoring_models WHERE status != 'archived' ORDER BY pending_review_count DESC"
    )
    review = C.fetch_one("SELECT * FROM week_reviews WHERE week_start = ?", (start_iso,))

    done_tasks = [item for item in tasks if item["status"] == "done"]
    blocked_tasks = [item for item in tasks if item["status"] == "blocked"]
    high_open_tasks = [item for item in tasks if item["priority"] == "high" and item["status"] != "done"]
    delivered_requests = [item for item in requests if item["status"] == "done"]
    waiting_requests = [item for item in requests if item["status"] in {"pending", "waiting"}]
    successful_runs = [item for item in model_runs if item["status"] == "success"]
    failed_runs = [item for item in model_runs if item["status"] == "failed"]

    highlight_items: list[str] = []
    if review and review["accomplishments"]:
        highlight_items.append(review["accomplishments"])
    highlight_items.extend(f"完成任务：{item['title']}（{item['id']}）" for item in done_tasks[:5])
    highlight_items.extend(f"交付数据请求：{item['title']}（{item['id']}）" for item in delivered_requests[:3])
    highlight_items.extend(
        f"{item['model_name']}运行成功，扫描 {item['scanned_count']} 条、命中 {item['hit_count']} 条、已复核 {item['reviewed_count']} 条"
        for item in successful_runs[:3]
    )
    highlight_items.extend(f"形成工作记录：{item['title']}（{item['id']}）" for item in notes[:2])

    risk_items: list[str] = []
    if review and review["blockers"]:
        risk_items.append(review["blockers"])
    risk_items.extend(f"受阻任务：{item['title']}（{item['id']}）" for item in blocked_tasks)
    risk_items.extend(f"高优先任务尚未完成：{item['title']}（{item['id']}）" for item in high_open_tasks[:5])
    risk_items.extend(f"数据请求待确认：{item['title']}（{item['id']}）" for item in waiting_requests[:5])
    risk_items.extend(f"模型运行失败：{item['model_name']}，{item['result_summary'] or '需排查运行日志'}" for item in failed_runs)
    risk_items.extend(
        f"{item['name']}仍有 {item['pending_review_count']} 条待复核"
        for item in models if item["pending_review_count"] > 0
    )

    plan_items: list[str] = []
    if review and review["next_week_focus"]:
        plan_items.append(review["next_week_focus"])
    plan_items.extend(f"{item['planned_date']}：{item['title']}（{item['id']}）" for item in next_tasks[:8])
    plan_items.extend(
        f"推进项目“{item['name']}”：{item['next_action']}"
        for item in projects if item["next_action"]
    )

    hit_total = sum(item["hit_count"] for item in model_runs)
    reviewed_total = sum(item["reviewed_count"] for item in model_runs)
    metrics = {
        "task_total": len(tasks),
        "task_done": len(done_tasks),
        "task_completion_rate": round(len(done_tasks) / len(tasks) * 100) if tasks else 0,
        "request_total": len(requests),
        "request_delivered": len(delivered_requests),
        "model_run_total": len(model_runs),
        "model_hit_total": hit_total,
        "model_reviewed_total": reviewed_total,
        "active_projects": len(projects),
        "note_total": len(notes),
        "risk_total": len(blocked_tasks) + len(high_open_tasks) + len(waiting_requests) + len(failed_runs),
    }
    executive_summary = (
        f"{start.month}月{start.day}日至{end.month}月{end.day}日，共安排 {len(tasks)} 项任务，"
        f"完成 {len(done_tasks)} 项，完成率 {metrics['task_completion_rate']}%；"
        f"处理 {len(requests)} 项数据请求，完成交付 {len(delivered_requests)} 项；"
        f"监测模型运行 {len(model_runs)} 次，命中 {hit_total} 条、已复核 {reviewed_total} 条。"
        f"当前推进 {len(projects)} 个项目，识别 {metrics['risk_total']} 项需关注事项。"
    )
    source_snapshot = {
        "generated_at": utc_now(),
        "week_end": end_iso,
        "task_ids": [item["id"] for item in tasks],
        "request_ids": [item["id"] for item in requests],
        "model_run_ids": [item["id"] for item in model_runs],
        "project_ids": [item["id"] for item in projects],
        "note_ids": [item["id"] for item in notes],
        "review_id": review["id"] if review else None,
    }
    return {
        "id": None,
        "week_start": start_iso,
        "title": f"{start.year}年第{start.isocalendar().week}周工作总结",
        "executive_summary": executive_summary,
        "highlights": bullet_text(highlight_items, "本周暂无已记录的完成事项，可补充阶段性进展。"),
        "risks": bullet_text(risk_items, "本周未识别到明确阻塞，继续关注待复核模型结果。"),
        "next_week_plan": bullet_text(plan_items, "结合项目优先级补充下周三项重点工作。"),
        "metrics": metrics,
        "source_snapshot": source_snapshot,
        "created_at": None,
        "updated_at": None,
        "saved": False,
    }


@router.post("/api/weekly-reports/{week_start}/generate")
def generate_report(week_start: str, use_ai: bool = Query(default=True)) -> dict:
    draft = generate_weekly_report(week_start)
    if use_ai:
        ai_settings = C.load_ai_settings()
        if ai_ready(ai_settings):
            try:
                draft = enhance_weekly_report(ai_settings, draft)
                draft["ai_generated"] = True
            except (AINotConfigured, AIRequestError) as exc:
                draft["ai_error"] = str(exc)
                draft["ai_generated"] = False
        else:
            draft["ai_generated"] = False
    return draft


@router.post("/api/weekly-reports/{week_start}/polish")
def polish_weekly_report(week_start: str, payload: WeeklyReportUpsert) -> dict:
    """对当前编辑中的周报正文做一键 AI 润色（不重新拉数）。"""
    parse_week_start(week_start)
    draft = {
        "week_start": week_start,
        "title": payload.title,
        "executive_summary": payload.executive_summary,
        "highlights": payload.highlights,
        "risks": payload.risks,
        "next_week_plan": payload.next_week_plan,
        "metrics": payload.metrics or {},
        "source_snapshot": payload.source_snapshot or {},
        "status": payload.status,
        "saved": False,
    }
    ai_settings = C.load_ai_settings()
    if not ai_ready(ai_settings):
        raise HTTPException(status_code=400, detail="AI 未就绪：请先在数据管理中启用并配置接口")
    try:
        polished = enhance_weekly_report(ai_settings, draft)
        polished["ai_polished"] = True
        polished["week_start"] = week_start
        return polished
    except AINotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIRequestError as exc:
        raise HTTPException(status_code=502, detail=f"AI 润色失败：{exc}") from exc


@router.get("/api/weekly-reports/{week_start}")
def get_weekly_report(week_start: str) -> dict:
    parse_week_start(week_start)
    report = C.fetch_one("SELECT * FROM weekly_reports WHERE week_start = ?", (week_start,))
    if report:
        report["saved"] = True
        return report
    return generate_weekly_report(week_start)


@router.put("/api/weekly-reports/{week_start}")
def save_weekly_report(week_start: str, payload: WeeklyReportUpsert) -> dict:
    parse_week_start(week_start)
    now = utc_now()
    with transaction() as connection:
        connection.execute(
            """INSERT INTO weekly_reports
            (id,week_start,title,executive_summary,highlights,risks,next_week_plan,metrics_json,source_snapshot_json,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(week_start) DO UPDATE SET
              title=excluded.title, executive_summary=excluded.executive_summary,
              highlights=excluded.highlights, risks=excluded.risks,
              next_week_plan=excluded.next_week_plan, metrics_json=excluded.metrics_json,
              source_snapshot_json=excluded.source_snapshot_json, status=excluded.status,
              updated_at=excluded.updated_at""",
            (
                new_id("RPT"), week_start, payload.title, payload.executive_summary,
                payload.highlights, payload.risks, payload.next_week_plan,
                json.dumps(payload.metrics, ensure_ascii=False),
                json.dumps(payload.source_snapshot, ensure_ascii=False), payload.status, now, now,
            ),
        )
    report = C.fetch_one("SELECT * FROM weekly_reports WHERE week_start = ?", (week_start,))
    C.snapshot_report_version(
        "weekly",
        week_start,
        payload.title,
        payload.status,
        {
            "title": payload.title,
            "executive_summary": payload.executive_summary,
            "highlights": payload.highlights,
            "risks": payload.risks,
            "next_week_plan": payload.next_week_plan,
            "metrics": payload.metrics,
            "source_snapshot": payload.source_snapshot,
            "status": payload.status,
        },
        payload.change_summary,
    )
    report["saved"] = True
    return report


@router.post("/api/weekly-reports/{week_start}/finalize")
def finalize_weekly_report(week_start: str) -> dict:
    report = C.fetch_one("SELECT * FROM weekly_reports WHERE week_start = ?", (week_start,))
    if not report:
        raise HTTPException(status_code=404, detail="周报尚未保存，无法定稿")
    return save_weekly_report(
        week_start,
        WeeklyReportUpsert(
            title=report["title"],
            executive_summary=report["executive_summary"],
            highlights=report["highlights"],
            risks=report["risks"],
            next_week_plan=report["next_week_plan"],
            metrics=report.get("metrics") or {},
            source_snapshot=report.get("source_snapshot") or {},
            status="final",
            change_summary="定稿",
        ),
    )


@router.get("/api/weekly-reports/{week_start}/versions")
def list_weekly_report_versions(week_start: str) -> list[dict]:
    parse_week_start(week_start)
    return C.fetch_all(
        "SELECT * FROM report_versions WHERE report_kind = 'weekly' AND report_key = ? ORDER BY version DESC",
        (week_start,),
    )


def weekly_report_markdown(report: dict) -> str:
    metrics = report.get("metrics", {})
    return (
        f"# {report['title']}\n\n"
        f"报告周期：{report['week_start']} 开始的一周\n\n"
        f"## 总体概览\n\n{report['executive_summary']}\n\n"
        f"## 关键指标\n\n"
        f"- 任务完成：{metrics.get('task_done', 0)} / {metrics.get('task_total', 0)}\n"
        f"- 数据请求交付：{metrics.get('request_delivered', 0)} / {metrics.get('request_total', 0)}\n"
        f"- 模型运行：{metrics.get('model_run_total', 0)} 次，命中 {metrics.get('model_hit_total', 0)} 条\n"
        f"- 活跃项目：{metrics.get('active_projects', 0)} 个\n\n"
        f"## 完成与进展\n\n{report['highlights']}\n\n"
        f"## 阻塞与风险\n\n{report['risks']}\n\n"
        f"## 下周计划\n\n{report['next_week_plan']}\n"
    )


@router.get("/api/weekly-reports/{week_start}/markdown")
def export_weekly_report_markdown(week_start: str) -> Response:
    report = get_weekly_report(week_start)
    return Response(
        content=weekly_report_markdown(report),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="weekly-report-{week_start}.md"'},
    )


def weekly_report_document(report: dict) -> dict:
    template = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", ("RT-WEEKLY",)) or {}
    return {
        "title": report["title"],
        "period_start": report["week_start"],
        "period_end": report.get("source_snapshot", {}).get("week_end") or report["week_start"],
        "status": report.get("status") or "draft",
        "cover": template.get("cover") or {},
        "sections": {
            "summary": report["executive_summary"],
            "highlights": report["highlights"],
            "risks": report["risks"],
            "next_plan": report["next_week_plan"],
        },
    }


@router.get("/api/weekly-reports/{week_start}/docx")
def export_weekly_report_docx(week_start: str) -> Response:
    content = report_docx(weekly_report_document(get_weekly_report(week_start)), {"next_plan": "下周计划"})
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="weekly-report-{week_start}.docx"'})


@router.get("/api/weekly-reports/{week_start}/pdf")
def export_weekly_report_pdf(week_start: str) -> Response:
    content = report_pdf(weekly_report_document(get_weekly_report(week_start)), {"next_plan": "下周计划"})
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="weekly-report-{week_start}.pdf"'})


@router.get("/api/report-templates")
def list_report_templates() -> list[dict]:
    return C.fetch_all("SELECT * FROM report_templates ORDER BY is_builtin DESC, name")


@router.post("/api/report-templates", status_code=status.HTTP_201_CREATED)
def create_report_template(payload: ReportTemplateCreate) -> dict:
    template_id, now = new_id("RT"), utc_now()
    labels = {key: value.strip() for key, value in payload.section_labels.items() if value.strip()}
    with transaction() as connection:
        connection.execute("""INSERT INTO report_templates
        (id,name,type,description,section_labels_json,cover_json,is_builtin,created_at,updated_at)
        VALUES (?,?,?,?,?,?,0,?,?)""", (template_id, payload.name, payload.type, payload.description,
        json.dumps(labels, ensure_ascii=False), json.dumps(payload.cover.model_dump(), ensure_ascii=False), now, now))
    return C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (template_id,))


@router.patch("/api/report-templates/{template_id}")
def update_report_template(template_id: str, payload: ReportTemplateUpdate) -> dict:
    current = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (template_id,))
    if not current:
        raise HTTPException(status_code=404, detail="报告模板不存在")
    if current["is_builtin"]:
        raise HTTPException(status_code=409, detail="内置模板不可修改，请创建自定义模板")
    changes = payload.model_dump(exclude_unset=True)
    if "section_labels" in changes:
        changes["section_labels_json"] = json.dumps({key: value.strip() for key, value in changes.pop("section_labels").items() if value.strip()}, ensure_ascii=False)
    if "cover" in changes and changes["cover"] is not None:
        changes["cover_json"] = json.dumps(changes.pop("cover"), ensure_ascii=False)
    return C.update_record("report_templates", template_id, changes, "报告模板不存在")


@router.delete("/api/report-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_template(template_id: str) -> Response:
    current = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (template_id,))
    if not current:
        raise HTTPException(status_code=404, detail="报告模板不存在")
    if current["is_builtin"]:
        raise HTTPException(status_code=409, detail="内置模板不可删除")
    if C.fetch_one("SELECT id FROM generated_reports WHERE template_id = ? LIMIT 1", (template_id,)):
        raise HTTPException(status_code=409, detail="该模板已有报告记录，暂不能删除")
    return C.delete_record("report_templates", template_id, "报告模板不存在")


@router.get("/api/report-templates/export")
def export_report_templates() -> Response:
    templates = C.fetch_all("SELECT * FROM report_templates WHERE is_builtin = 0 ORDER BY name")
    package = {
        "schema_version": C.APP_VERSION,
        "exported_at": utc_now(),
        "templates": [
            {
                "name": item["name"],
                "type": item["type"],
                "description": item["description"],
                "section_labels": item.get("section_labels") or {},
                "cover": item.get("cover") or {},
            }
            for item in templates
        ],
    }
    return Response(
        content=json.dumps(package, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="report-templates.json"'},
    )


@router.post("/api/report-templates/import")
def import_report_templates(payload: ReportTemplateImport) -> dict:
    imported = 0
    now = utc_now()
    with transaction() as connection:
        for template in payload.templates:
            existing = connection.execute(
                "SELECT id, is_builtin FROM report_templates WHERE name = ? AND type = ?",
                (template.name, template.type),
            ).fetchone()
            cover = json.dumps(template.cover.model_dump(), ensure_ascii=False)
            labels = json.dumps(
                {key: value.strip() for key, value in template.section_labels.items() if value.strip()},
                ensure_ascii=False,
            )
            if existing:
                if existing["is_builtin"] or payload.mode != "merge":
                    continue
                connection.execute(
                    """UPDATE report_templates
                    SET description=?, section_labels_json=?, cover_json=?, updated_at=?
                    WHERE id=?""",
                    (template.description, labels, cover, now, existing["id"]),
                )
                imported += 1
                continue
            connection.execute(
                """INSERT INTO report_templates
                (id,name,type,description,section_labels_json,cover_json,is_builtin,created_at,updated_at)
                VALUES (?,?,?,?,?,?,0,?,?)""",
                (new_id("RT"), template.name, template.type, template.description, labels, cover, now, now),
            )
            imported += 1
    return {"imported": imported, "mode": payload.mode}


@router.get("/api/reports")
def list_generated_reports(report_type: str | None = Query(default=None, alias="type")) -> list[dict]:
    if report_type:
        return C.fetch_all("SELECT * FROM generated_reports WHERE type = ? ORDER BY updated_at DESC", (report_type,))
    return C.fetch_all("SELECT * FROM generated_reports ORDER BY updated_at DESC")


def generate_generic_report(payload: GenericReportGenerate) -> dict:
    template = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (payload.template_id,))
    if not template:
        raise HTTPException(status_code=404, detail="报告模板不存在")
    if template["type"] == "weekly":
        weekly = generate_weekly_report(payload.period_start)
        return {"id": None, "template_id": template["id"], "type": "weekly", "title": weekly["title"],
                "period_start": weekly["week_start"], "period_end": weekly["source_snapshot"]["week_end"],
                "related_entity_id": None, "sections": {"summary": weekly["executive_summary"], "highlights": weekly["highlights"], "risks": weekly["risks"], "next_plan": weekly["next_week_plan"]},
                "metrics": weekly["metrics"], "source_snapshot": weekly["source_snapshot"], "status": "draft", "saved": False}
    entity = None
    if template["type"] == "project" and payload.related_entity_id:
        entity = C.fetch_one("SELECT * FROM projects WHERE id = ?", (payload.related_entity_id,))
    elif template["type"] == "model" and payload.related_entity_id:
        entity = C.fetch_one("SELECT * FROM monitoring_models WHERE id = ?", (payload.related_entity_id,))
    if template["type"] in {"project", "model"} and not entity:
        raise HTTPException(status_code=400, detail="请选择有效的关联项目或模型")
    requests = C.fetch_all("SELECT * FROM data_requests WHERE substr(updated_at,1,10) BETWEEN ? AND ? ORDER BY updated_at DESC", (payload.period_start, payload.period_end))
    notes = C.fetch_all("SELECT * FROM work_notes WHERE substr(updated_at,1,10) BETWEEN ? AND ? ORDER BY updated_at DESC", (payload.period_start, payload.period_end))
    if template["type"] == "project":
        title = f"{entity['name']}项目进展报告"
        summary = f"项目当前完成度 {entity['progress']}%，目标：{entity['goal'] or '待补充'}。"
        highlights = bullet_text([f"数据请求：{item['title']}" for item in requests if item.get("related_project_id") == entity["id"]], "本阶段成果待补充。")
        risks = f"- 当前状态：{entity['status']}\n- 计划结束：{entity['due_date'] or '未设置'}"
        next_plan = f"- {entity['next_action'] or '补充下一阶段行动计划'}"
    elif template["type"] == "model":
        title = f"{entity['name']}运行简报"
        runs = C.fetch_all("SELECT * FROM model_runs WHERE model_id = ? AND substr(started_at,1,10) BETWEEN ? AND ? ORDER BY started_at DESC", (entity["id"], payload.period_start, payload.period_end))
        summary = f"报告期内运行 {len(runs)} 次，累计命中 {sum(item['hit_count'] for item in runs)} 条，当前待复核 {entity['pending_review_count']} 条。"
        highlights = bullet_text([item["result_summary"] for item in runs if item["result_summary"]], "暂无运行摘要。")
        risks = bullet_text([f"运行失败：{item['started_at']}" for item in runs if item["status"] == "failed"], "未记录运行失败。")
        next_plan = "- 复核未处理命中结果\n- 评估规则准确率并记录版本调整"
    else:
        title = f"{payload.period_start} 至 {payload.period_end} 专项检查报告"
        summary = f"本次检查覆盖 {len(requests)} 项数据请求和 {len(notes)} 条工作记录。"
        highlights = bullet_text([item["title"] for item in notes[:8]], "主要检查发现待补充。")
        risks = bullet_text([item["caliber_notes"] for item in requests if item["status"] in {"pending", "waiting"}], "风险判断待补充。")
        next_plan = "- 明确问题责任与整改时限\n- 持续跟踪数据验证和整改结果"
    snapshot = {"generated_at": utc_now(), "request_ids": [item["id"] for item in requests], "note_ids": [item["id"] for item in notes]}
    return {"id": None, "template_id": template["id"], "type": template["type"], "title": title,
            "period_start": payload.period_start, "period_end": payload.period_end, "related_entity_id": payload.related_entity_id,
            "sections": {"summary": summary, "highlights": highlights, "risks": risks, "next_plan": next_plan},
            "metrics": {"request_total": len(requests), "note_total": len(notes)}, "source_snapshot": snapshot, "status": "draft", "saved": False}


@router.post("/api/reports/generate")
def generate_report_from_template(payload: GenericReportGenerate) -> dict:
    return generate_generic_report(payload)


def generated_report_payload(payload: GenericReportUpsert) -> dict:
    return {
        "template_id": payload.template_id,
        "title": payload.title,
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "related_entity_id": payload.related_entity_id,
        "sections": payload.sections,
        "metrics": payload.metrics,
        "source_snapshot": payload.source_snapshot,
        "status": payload.status,
    }


@router.post("/api/reports", status_code=status.HTTP_201_CREATED)
def save_generated_report(payload: GenericReportUpsert) -> dict:
    template = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (payload.template_id,))
    if not template:
        raise HTTPException(status_code=404, detail="报告模板不存在")
    report_id, now = new_id("GR"), utc_now()
    with transaction() as connection:
        connection.execute("""INSERT INTO generated_reports
        (id,template_id,type,title,period_start,period_end,related_entity_id,sections_json,metrics_json,source_snapshot_json,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (report_id, payload.template_id, template["type"], payload.title, payload.period_start, payload.period_end,
         payload.related_entity_id, json.dumps(payload.sections, ensure_ascii=False), json.dumps(payload.metrics, ensure_ascii=False),
         json.dumps(payload.source_snapshot, ensure_ascii=False), payload.status, now, now))
    C.snapshot_report_version("generated", report_id, payload.title, payload.status, generated_report_payload(payload), payload.change_summary)
    result = C.fetch_one("SELECT * FROM generated_reports WHERE id = ?", (report_id,)); result["saved"] = True
    return result


@router.get("/api/reports/{report_id}")
def get_generated_report(report_id: str) -> dict:
    report = C.fetch_one("SELECT * FROM generated_reports WHERE id = ?", (report_id,))
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    report["saved"] = True
    return report


@router.put("/api/reports/{report_id}")
def update_generated_report(report_id: str, payload: GenericReportUpsert) -> dict:
    if not C.fetch_one("SELECT id FROM generated_reports WHERE id = ?", (report_id,)):
        raise HTTPException(status_code=404, detail="报告不存在")
    template = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (payload.template_id,))
    if not template:
        raise HTTPException(status_code=404, detail="报告模板不存在")
    changes = {
        "template_id": payload.template_id, "type": template["type"], "title": payload.title,
        "period_start": payload.period_start, "period_end": payload.period_end,
        "related_entity_id": payload.related_entity_id,
        "sections_json": json.dumps(payload.sections, ensure_ascii=False),
        "metrics_json": json.dumps(payload.metrics, ensure_ascii=False),
        "source_snapshot_json": json.dumps(payload.source_snapshot, ensure_ascii=False),
        "status": payload.status,
    }
    result = C.update_record("generated_reports", report_id, changes, "报告不存在")
    C.snapshot_report_version("generated", report_id, payload.title, payload.status, generated_report_payload(payload), payload.change_summary)
    result["saved"] = True
    return result


@router.post("/api/reports/{report_id}/finalize")
def finalize_generated_report(report_id: str) -> dict:
    report = get_generated_report(report_id)
    return update_generated_report(
        report_id,
        GenericReportUpsert(
            template_id=report["template_id"],
            title=report["title"],
            period_start=report.get("period_start"),
            period_end=report.get("period_end"),
            related_entity_id=report.get("related_entity_id"),
            sections=report.get("sections") or {},
            metrics=report.get("metrics") or {},
            source_snapshot=report.get("source_snapshot") or {},
            status="final",
            change_summary="定稿",
        ),
    )


@router.get("/api/reports/{report_id}/versions")
def list_generated_report_versions(report_id: str) -> list[dict]:
    if not C.fetch_one("SELECT id FROM generated_reports WHERE id = ?", (report_id,)):
        raise HTTPException(status_code=404, detail="报告不存在")
    return C.fetch_all(
        "SELECT * FROM report_versions WHERE report_kind = 'generated' AND report_key = ? ORDER BY version DESC",
        (report_id,),
    )


@router.delete("/api/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generated_report(report_id: str) -> Response:
    return C.delete_record("generated_reports", report_id, "报告不存在")


def report_with_template(report_id: str) -> tuple[dict, dict]:
    report = C.fetch_one("SELECT * FROM generated_reports WHERE id = ?", (report_id,))
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    template = C.fetch_one("SELECT * FROM report_templates WHERE id = ?", (report["template_id"],)) or {}
    report = {**report, "cover": template.get("cover") or {}}
    return report, template


@router.get("/api/reports/{report_id}/markdown")
def export_generated_report_markdown(report_id: str) -> Response:
    report, template = report_with_template(report_id)
    return Response(content=report_markdown(report, template.get("section_labels")), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="report-{report_id}.md"'})


@router.get("/api/reports/{report_id}/docx")
def export_generated_report_docx(report_id: str) -> Response:
    report, template = report_with_template(report_id)
    return Response(content=report_docx(report, template.get("section_labels")),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="report-{report_id}.docx"'})


@router.get("/api/reports/{report_id}/pdf")
def export_generated_report_pdf(report_id: str) -> Response:
    report, template = report_with_template(report_id)
    return Response(content=report_pdf(report, template.get("section_labels")), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="report-{report_id}.pdf"'})

