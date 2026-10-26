import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4


PROJECT_DIR = Path(__file__).resolve().parents[1]
_env_data = os.environ.get("WORKBENCH_DATA_DIR", "").strip()
DATA_DIR = Path(_env_data) if _env_data else (PROJECT_DIR / "data")
DB_PATH = DATA_DIR / "workbench.db"


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(db_path: Path | None = None):
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'medium',
    planned_date TEXT,
    due_at TEXT,
    type TEXT NOT NULL DEFAULT 'task',
    related_entity_type TEXT,
    related_entity_id TEXT,
    notes TEXT NOT NULL DEFAULT '',
    waiting_on TEXT NOT NULL DEFAULT '',
    completion_result TEXT NOT NULL DEFAULT '',
    actual_minutes INTEGER NOT NULL DEFAULT 0,
    recurrence TEXT NOT NULL DEFAULT 'none',
    recurrence_interval INTEGER NOT NULL DEFAULT 7,
    remind_at TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_notes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    related_entity_type TEXT,
    related_entity_id TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_note_revisions (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (note_id) REFERENCES work_notes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    project_type TEXT NOT NULL DEFAULT 'analysis',
    description TEXT NOT NULL DEFAULT '',
    goal_template TEXT NOT NULL DEFAULT '',
    next_action_template TEXT NOT NULL DEFAULT '',
    checklist_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sql_assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    sql_text TEXT NOT NULL DEFAULT '',
    current_version TEXT NOT NULL DEFAULT 'v1.0',
    status TEXT NOT NULL DEFAULT 'draft',
    tags_json TEXT NOT NULL DEFAULT '[]',
    table_names_json TEXT NOT NULL DEFAULT '[]',
    related_project_id TEXT,
    reuse_count INTEGER NOT NULL DEFAULT 0,
    validation_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_requests (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    caliber_notes TEXT NOT NULL DEFAULT '',
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    next_action TEXT NOT NULL DEFAULT '',
    related_sql_ids_json TEXT NOT NULL DEFAULT '[]',
    related_project_id TEXT,
    requester TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    waiting_on TEXT NOT NULL DEFAULT '',
    delivery_method TEXT NOT NULL DEFAULT '',
    delivery_location TEXT NOT NULL DEFAULT '',
    sensitive_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitoring_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'normal',
    schedule TEXT NOT NULL DEFAULT '',
    current_version TEXT NOT NULL DEFAULT 'v1.0',
    rule_definitions_json TEXT NOT NULL DEFAULT '[]',
    dependency_ids_json TEXT NOT NULL DEFAULT '[]',
    related_sql_ids_json TEXT NOT NULL DEFAULT '[]',
    update_steps_json TEXT NOT NULL DEFAULT '[]',
    last_run_at TEXT,
    hit_count INTEGER NOT NULL DEFAULT 0,
    pending_review_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_versions (
    id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    version TEXT NOT NULL,
    change_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES monitoring_models(id) ON DELETE CASCADE,
    UNIQUE (model_id, version)
);

CREATE TABLE IF NOT EXISTS navigation_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '常用工具',
    icon_text TEXT NOT NULL DEFAULT '链',
    color TEXT NOT NULL DEFAULT 'blue',
    sort_order INTEGER NOT NULL DEFAULT 0,
    visit_count INTEGER NOT NULL DEFAULT 0,
    last_visited_at TEXT,
    show_on_home INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stored_procedures (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    database_name TEXT NOT NULL DEFAULT '',
    schema_name TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    current_version TEXT NOT NULL DEFAULT 'v1.0',
    owner TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    definition_text TEXT NOT NULL DEFAULT '',
    rollback_text TEXT NOT NULL DEFAULT '',
    related_project_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS procedure_versions (
    id TEXT PRIMARY KEY,
    procedure_id TEXT NOT NULL,
    version TEXT NOT NULL,
    definition_text TEXT NOT NULL DEFAULT '',
    rollback_text TEXT NOT NULL DEFAULT '',
    change_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (procedure_id) REFERENCES stored_procedures(id) ON DELETE CASCADE,
    UNIQUE (procedure_id, version)
);

CREATE TABLE IF NOT EXISTS procedure_deployments (
    id TEXT PRIMARY KEY,
    procedure_id TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    deployed_at TEXT,
    validation_result TEXT NOT NULL DEFAULT '',
    rollback_executed INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (procedure_id) REFERENCES stored_procedures(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    section_labels_json TEXT NOT NULL DEFAULT '{}',
    cover_json TEXT NOT NULL DEFAULT '{}',
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_reports (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    related_entity_id TEXT,
    sections_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source_snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (template_id) REFERENCES report_templates(id)
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    progress INTEGER NOT NULL DEFAULT 0,
    due_date TEXT,
    next_action TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sql_versions (
    id TEXT PRIMARY KEY,
    sql_asset_id TEXT NOT NULL,
    version TEXT NOT NULL,
    sql_text TEXT NOT NULL DEFAULT '',
    change_summary TEXT NOT NULL DEFAULT '',
    validation_status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    FOREIGN KEY (sql_asset_id) REFERENCES sql_assets(id) ON DELETE CASCADE,
    UNIQUE (sql_asset_id, version)
);

CREATE TABLE IF NOT EXISTS model_runs (
    id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    scanned_count INTEGER NOT NULL DEFAULT 0,
    hit_count INTEGER NOT NULL DEFAULT 0,
    reviewed_count INTEGER NOT NULL DEFAULT 0,
    result_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES monitoring_models(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_relations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'supporting',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE (project_id, entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS week_reviews (
    id TEXT PRIMARY KEY,
    week_start TEXT NOT NULL UNIQUE,
    accomplishments TEXT NOT NULL DEFAULT '',
    blockers TEXT NOT NULL DEFAULT '',
    next_week_focus TEXT NOT NULL DEFAULT '',
    energy_score INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    id TEXT PRIMARY KEY,
    week_start TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    executive_summary TEXT NOT NULL DEFAULT '',
    highlights TEXT NOT NULL DEFAULT '',
    risks TEXT NOT NULL DEFAULT '',
    next_week_plan TEXT NOT NULL DEFAULT '',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source_snapshot_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL DEFAULT 'null',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    types TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recent_searches (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    types TEXT NOT NULL DEFAULT '',
    result_count INTEGER NOT NULL DEFAULT 0,
    searched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_versions (
    id TEXT PRIMARY KEY,
    report_kind TEXT NOT NULL,
    report_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    payload_json TEXT NOT NULL DEFAULT '{}',
    change_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (report_kind, report_key, version)
);

CREATE TABLE IF NOT EXISTS calendar_subscriptions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'ics',
    ics_url TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_synced_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    subscription_id TEXT,
    external_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    start_at TEXT NOT NULL,
    end_at TEXT,
    all_day INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'ics',
    raw_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (subscription_id) REFERENCES calendar_subscriptions(id) ON DELETE CASCADE,
    UNIQUE (subscription_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_planned_date ON tasks(planned_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON work_notes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sql_assets_updated_at ON sql_assets(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sql_versions_asset ON sql_versions(sql_asset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_runs_model ON model_runs(model_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_versions_model ON model_versions(model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_navigation_category ON navigation_items(category, sort_order);
CREATE INDEX IF NOT EXISTS idx_procedure_versions ON procedure_versions(procedure_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_procedure_deployments ON procedure_deployments(procedure_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generated_reports ON generated_reports(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_relations_project ON project_relations(project_id);
CREATE INDEX IF NOT EXISTS idx_week_reviews_start ON week_reviews(week_start DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_reports_start ON weekly_reports(week_start DESC);
CREATE INDEX IF NOT EXISTS idx_saved_searches_updated ON saved_searches(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_recent_searches_at ON recent_searches(searched_at DESC);
CREATE INDEX IF NOT EXISTS idx_report_versions_key ON report_versions(report_kind, report_key, version DESC);
CREATE INDEX IF NOT EXISTS idx_calendar_events_start ON calendar_events(start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_subscriptions_enabled ON calendar_subscriptions(enabled);
"""

DEFAULT_SETTINGS = {
    "backup_retention": 20,
    "auto_backup_hours": 0,
    "last_auto_backup_at": "",
    "home_layout": ["tasks", "projects", "requests", "quick"],
    "ai": {
        "enabled": False,
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key": "",
        "timeout_seconds": 60,
        "include_sql_text": True,
        "temperature": 0.2,
    },
    "access_password_hash": "",
    "dingtalk_calendar": {
        "enabled": False,
        "provider": "ics",
        "ics_url": "",
        "app_key": "",
        "app_secret": "",
        "calendar_id": "",
        "sync_days_back": 7,
        "sync_days_forward": 21,
    },
}


def row_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    for key in list(item):
        if key.endswith("_json"):
            item[key.removesuffix("_json")] = json.loads(item.pop(key) or "[]")
    return item


def ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(db_path: Path | None = None) -> None:
    with transaction(db_path) as connection:
        connection.executescript(SCHEMA)
        ensure_column(connection, "monitoring_models", "update_steps_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(connection, "weekly_reports", "status", "TEXT NOT NULL DEFAULT 'draft'")
        ensure_column(connection, "report_templates", "cover_json", "TEXT NOT NULL DEFAULT '{}'")
        for column, definition in (
            ("requester", "TEXT NOT NULL DEFAULT ''"),
            ("department", "TEXT NOT NULL DEFAULT ''"),
            ("waiting_on", "TEXT NOT NULL DEFAULT ''"),
            ("delivery_method", "TEXT NOT NULL DEFAULT ''"),
            ("delivery_location", "TEXT NOT NULL DEFAULT ''"),
            ("sensitive_notes", "TEXT NOT NULL DEFAULT ''"),
        ):
            ensure_column(connection, "data_requests", column, definition)
        ensure_column(connection, "tasks", "waiting_on", "TEXT NOT NULL DEFAULT ''")
        for column, definition in (
            ("completion_result", "TEXT NOT NULL DEFAULT ''"),
            ("actual_minutes", "INTEGER NOT NULL DEFAULT 0"),
            ("recurrence", "TEXT NOT NULL DEFAULT 'none'"),
            ("recurrence_interval", "INTEGER NOT NULL DEFAULT 7"),
            ("remind_at", "TEXT"),
        ):
            ensure_column(connection, "tasks", column, definition)
        ensure_column(connection, "work_notes", "is_favorite", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "work_notes", "is_archived", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "navigation_items", "show_on_home", "INTEGER NOT NULL DEFAULT 1")
        for key, value in DEFAULT_SETTINGS.items():
            existing = connection.execute("SELECT key FROM app_settings WHERE key = ?", (key,)).fetchone()
            if not existing:
                connection.execute(
                    "INSERT INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value, ensure_ascii=False), utc_now()),
                )
        seed_database(connection)


def seed_database(connection: sqlite3.Connection) -> None:
    now = utc_now()
    today = datetime.now().astimezone().date().isoformat()

    if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
        tasks = [
            ("T-001", "复核采购异常模型本周命中样本", "todo", "high", today, "09:30", "model", "model", "M-014", "核对 3 条边界规则", 10),
            ("T-002", "交付固定资产盘点差异明细", "todo", "high", today, "11:20", "request", "data_request", "DR-0261", "等待确认统计截止日", 20),
            ("T-003", "更新供应商关联识别 SQL 参数", "todo", "medium", today, "14:00", "sql", "sql_asset", "Q-126", "补充参数与使用说明", 30),
            ("T-004", "整理审计报告数据支撑清单", "todo", "medium", today, "15:40", "report", "project", "P-009", "本周阶段交付", 40),
            ("T-005", "记录制度知识库向量化测试结论", "todo", "low", today, "17:00", "note", "project", "P-012", "记录召回率测试结果", 50),
        ]
        connection.executemany(
            """INSERT INTO tasks
            (id,title,status,priority,planned_date,due_at,type,related_entity_type,related_entity_id,notes,sort_order,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(*task, now, now) for task in tasks],
        )

    if connection.execute("SELECT COUNT(*) FROM work_notes").fetchone()[0] == 0:
        notes = [
            ("N-001", "口径说明", "固定资产盘点差异的统计截止日", "盘点结果以 9 月 30 日资产台账为基准；10 月新增资产不进入本次差异统计。", '["固定资产","数据请求"]', "data_request", "DR-0261"),
            ("N-002", "模型维护", "采购异常模型 v2.4 调整原因", "原 3 日观察窗口无法覆盖周末前后的连续拆单付款，调整为 7 日。", '["采购审计","规则变更"]', "model", "M-014"),
        ]
        connection.executemany(
            """INSERT INTO work_notes
            (id,type,title,content,tags_json,related_entity_type,related_entity_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            [(*note, now, now) for note in notes],
        )

    if connection.execute("SELECT COUNT(*) FROM sql_assets").fetchone()[0] == 0:
        sql_assets = [
            ("Q-128", "采购付款异常明细", "识别拆单付款、非工作时段付款和审批倒挂。", "WITH payment_base AS (\n  SELECT p.payment_id, p.vendor_id, p.amount, p.payment_time, a.approved_at\n  FROM dwd.purchase_payment p\n  LEFT JOIN dwd.approval_flow a ON p.order_id = a.order_id\n  WHERE p.payment_date BETWEEN :start_date AND :end_date\n)\nSELECT * FROM payment_base WHERE payment_time < approved_at;", "v2.4", "validated", '["采购","付款"]', '["dwd.purchase_payment","dwd.approval_flow","dim.vendor","dim.organization"]', "P-001", 18, "2026-10-20 完成抽样验证"),
            ("Q-126", "供应商关联交易识别", "匹配股东、联系方式及地址重合关系。", "SELECT * FROM ads.vendor_relation WHERE relation_score >= :threshold;", "v1.3", "draft", '["供应商","关联"]', '["ads.vendor_relation","dim.vendor"]', "P-001", 23, "待补充边界样本"),
            ("Q-121", "固定资产处置审批链", "还原申请、评估、审批与处置时间线。", "SELECT * FROM dwd.asset_disposal_flow WHERE disposed_at BETWEEN :start_date AND :end_date;", "v1.7", "validated", '["资产","审批"]', '["dwd.asset_disposal_flow"]', "P-006", 11, "验证通过"),
        ]
        connection.executemany(
            """INSERT INTO sql_assets
            (id,name,purpose,sql_text,current_version,status,tags_json,table_names_json,related_project_id,reuse_count,validation_note,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(*asset, now, now) for asset in sql_assets],
        )

    if connection.execute("SELECT COUNT(*) FROM data_requests").fetchone()[0] == 0:
        requests = [
            ("DR-0261", "固定资产盘点差异", "专项审计检查", "资产编号、账面价值、盘点状态", "待确认统计截止日", today, "waiting", "确认统计截止日", '[]', "P-006"),
            ("DR-0258", "采购付款明细", "采购审计", "付款单、供应商、审批链", "已确认时间范围", today, "working", "发送结果文件", '["Q-128"]', "P-001"),
            ("DR-0253", "供应商关联分析", "风险监测", "股东、联系人、地址", "已交付", None, "done", "归档查询逻辑", '["Q-126"]', "P-001"),
        ]
        connection.executemany(
            """INSERT INTO data_requests
            (id,title,purpose,scope,caliber_notes,due_at,status,next_action,related_sql_ids_json,related_project_id,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(*request, now, now) for request in requests],
        )

    if connection.execute("SELECT COUNT(*) FROM monitoring_models").fetchone()[0] == 0:
        default_steps = json.dumps([
            {"title": "更新前检查", "description": "备份当前规则与近 30 天运行结果", "done": False},
            {"title": "修改规则", "description": "记录规则、阈值与依赖调整", "done": False},
            {"title": "测试并发布", "description": "测试账期验证后发布并准备回滚", "done": False},
        ], ensure_ascii=False)
        models = [
            ("M-014", "采购异常监测模型", "识别采购付款异常", "normal", "每日 06:30", "v2.4", '[{"id":"R-01","name":"同供应商短期拆单"},{"id":"R-02","name":"非工作时段付款"},{"id":"R-03","name":"审批时间倒挂"}]', '["dwd.purchase_payment","dwd.approval_flow"]', '["Q-128"]', default_steps, now, 86, 12),
            ("M-011", "资产处置合规模型", "识别资产处置流程异常", "update_due", "每周一", "v1.8", '[]', '["dwd.asset_disposal_flow"]', '["Q-121"]', default_steps, now, 31, 5),
        ]
        connection.executemany(
            """INSERT INTO monitoring_models
            (id,name,purpose,status,schedule,current_version,rule_definitions_json,dependency_ids_json,related_sql_ids_json,update_steps_json,last_run_at,hit_count,pending_review_count,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(*model, now, now) for model in models],
        )

    if connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
        projects = [
            ("P-001", "采购异常监测模型", "model", "建立采购付款异常监测闭环", "active", 78, "2026-10-23", "完成 v2.4 抽样验证"),
            ("P-009", "审计报告数据支撑", "report", "支撑年度审计报告数据分析", "active", 52, "2026-10-30", "补充季度趋势口径"),
            ("P-012", "制度知识库", "ai", "搭建制度检索与问答知识库", "active", 34, "2026-11-15", "评估 50 条问答召回结果"),
        ]
        connection.executemany(
            """INSERT INTO projects
            (id,name,type,goal,status,progress,due_date,next_action,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [(*project, now, now) for project in projects],
        )

    if connection.execute("SELECT COUNT(*) FROM sql_versions").fetchone()[0] == 0:
        assets = connection.execute(
            "SELECT id,current_version,sql_text,status,validation_note FROM sql_assets"
        ).fetchall()
        connection.executemany(
            """INSERT INTO sql_versions
            (id,sql_asset_id,version,sql_text,change_summary,validation_status,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            [
                (
                    new_id("QV"), asset["id"], asset["current_version"], asset["sql_text"],
                    asset["validation_note"] or "从当前 SQL 资产生成初始版本",
                    asset["status"], now,
                )
                for asset in assets
            ],
        )

    if connection.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 0:
        models = connection.execute(
            "SELECT id,last_run_at,hit_count,pending_review_count FROM monitoring_models"
        ).fetchall()
        connection.executemany(
            """INSERT INTO model_runs
            (id,model_id,started_at,finished_at,status,scanned_count,hit_count,reviewed_count,result_summary,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    new_id("MR"), model["id"], model["last_run_at"] or now,
                    model["last_run_at"] or now, "success", max(model["hit_count"] * 100, 1000),
                    model["hit_count"], max(model["hit_count"] - model["pending_review_count"], 0),
                    "由现有模型汇总数据生成的初始运行记录", now,
                )
                for model in models
            ],
        )

    if connection.execute("SELECT COUNT(*) FROM model_versions").fetchone()[0] == 0:
        models = connection.execute("SELECT id,current_version FROM monitoring_models").fetchall()
        connection.executemany(
            "INSERT INTO model_versions (id,model_id,version,change_summary,created_at) VALUES (?,?,?,?,?)",
            [(new_id("MV"), model["id"], model["current_version"], "当前模型版本", now) for model in models],
        )

    if connection.execute("SELECT COUNT(*) FROM navigation_items").fetchone()[0] == 0:
        navigation_items = [
            ("NAV-001", "审计管理系统", "https://example.com/audit", "项目、底稿与问题整改", "核心系统", "审", "blue", 10),
            ("NAV-002", "数据仓库", "https://example.com/data", "查询开发与数据目录", "核心系统", "数", "cyan", 20),
            ("NAV-003", "分析看板平台", "https://example.com/bi", "审计监测与管理看板", "核心系统", "BI", "green", 30),
            ("NAV-004", "法规制度库", "https://example.com/rules", "制度检索与版本对照", "核心系统", "法", "orange", 40),
            ("NAV-005", "AI 知识库", "https://example.com/knowledge", "制度问答与技能检索", "核心系统", "知", "violet", 50),
            ("NAV-006", "工单系统", "https://example.com/ticket", "数据权限与问题反馈", "核心系统", "工", "gray", 60),
        ]
        connection.executemany(
            """INSERT INTO navigation_items
            (id,title,url,description,category,icon_text,color,sort_order,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [(*item, now, now) for item in navigation_items],
        )

    if connection.execute("SELECT COUNT(*) FROM report_templates").fetchone()[0] == 0:
        default_cover = '{"enabled":true,"org_name":"审计监察部","subtitle":"内部工作报告","footer":"内部资料 · 请复核后使用"}'
        templates = [
            ("RT-WEEKLY", "周工作总结", "weekly", "汇总一周任务、请求、模型和项目进展", '{"summary":"总体概览","highlights":"完成与进展","risks":"阻塞与风险","next_plan":"下周计划"}', default_cover, 1),
            ("RT-PROJECT", "项目进展报告", "project", "围绕项目目标、交付物和风险形成阶段汇报", '{"summary":"项目概览","highlights":"阶段成果","risks":"风险与依赖","next_plan":"下一阶段计划"}', default_cover, 1),
            ("RT-MODEL", "模型运行简报", "model", "汇总模型运行、命中和复核情况", '{"summary":"运行概览","highlights":"运行与复核结果","risks":"异常与数据质量","next_plan":"规则优化计划"}', default_cover, 1),
            ("RT-AUDIT", "专项检查报告", "audit", "形成检查范围、发现、风险及整改建议", '{"summary":"检查概览","highlights":"主要发现","risks":"风险判断","next_plan":"整改与跟进"}', default_cover, 1),
        ]
        connection.executemany(
            """INSERT INTO report_templates
            (id,name,type,description,section_labels_json,cover_json,is_builtin,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            [(*item, now, now) for item in templates],
        )

    if connection.execute("SELECT COUNT(*) FROM project_templates").fetchone()[0] == 0:
        templates = [
            (
                "PT-ANALYSIS", "数据分析项目", "analysis", "常规取数分析与口径沉淀",
                "明确分析目标、数据范围与交付口径", "确认数据源与字段清单",
                '["确认需求口径","梳理涉及表","编写/复用 SQL","样本验证","输出结论"]',
            ),
            (
                "PT-MODEL", "监测模型项目", "model", "模型规则建设与运行维护",
                "建立可验证的监测规则并完成上线验证", "核对规则与样本命中",
                '["定义规则","关联 SQL/过程","测试验证","记录运行","复核命中"]',
            ),
            (
                "PT-REPORT", "报告交付项目", "report", "阶段汇报与专项检查材料",
                "形成可复核的阶段报告", "汇总本周成果与风险",
                '["明确读者与用途","收集证据","起草报告","复核定稿","归档"]',
            ),
            (
                "PT-SKILL", "岗位技能项目", "skill", "个人能力与知识沉淀",
                "沉淀可复用的方法、模板与案例", "整理本周学习与实践",
                '["设定主题","收集材料","整理模板","形成记录","复盘改进"]',
            ),
        ]
        connection.executemany(
            """INSERT INTO project_templates
            (id,name,project_type,description,goal_template,next_action_template,checklist_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            [(*item, now, now) for item in templates],
        )

    if connection.execute("SELECT COUNT(*) FROM project_relations").fetchone()[0] == 0:
        relations: list[tuple] = []
        for asset in connection.execute(
            """SELECT s.id,s.related_project_id FROM sql_assets s
            INNER JOIN projects p ON p.id = s.related_project_id"""
        ).fetchall():
            relations.append((new_id("PR"), asset["related_project_id"], "sql_asset", asset["id"], "supporting", "SQL 资产", now))
        for task in connection.execute(
            "SELECT id,related_entity_id FROM tasks WHERE related_entity_type = 'project' AND related_entity_id IS NOT NULL"
        ).fetchall():
            relations.append((new_id("PR"), task["related_entity_id"], "task", task["id"], "delivery", "项目任务", now))
        if relations:
            connection.executemany(
                """INSERT OR IGNORE INTO project_relations
                (id,project_id,entity_type,entity_id,relation_type,note,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                relations,
            )
