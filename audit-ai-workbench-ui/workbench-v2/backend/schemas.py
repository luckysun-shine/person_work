from typing import Any, Literal

from pydantic import BaseModel, Field


TaskStatus = Literal["todo", "doing", "done", "blocked"]
TaskPriority = Literal["low", "medium", "high"]


Recurrence = Literal["none", "weekly", "monthly", "custom"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    planned_date: str | None = None
    due_at: str | None = None
    type: str = Field(default="task", max_length=40)
    related_entity_type: str | None = Field(default=None, max_length=40)
    related_entity_id: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=4000)
    waiting_on: str = Field(default="", max_length=100)
    completion_result: str = Field(default="", max_length=4000)
    actual_minutes: int = Field(default=0, ge=0, le=100000)
    recurrence: Recurrence = "none"
    recurrence_interval: int = Field(default=7, ge=1, le=365)
    remind_at: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    planned_date: str | None = None
    due_at: str | None = None
    type: str | None = Field(default=None, max_length=40)
    related_entity_type: str | None = Field(default=None, max_length=40)
    related_entity_id: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=4000)
    waiting_on: str | None = Field(default=None, max_length=100)
    completion_result: str | None = Field(default=None, max_length=4000)
    actual_minutes: int | None = Field(default=None, ge=0, le=100000)
    recurrence: Recurrence | None = None
    recurrence_interval: int | None = Field(default=None, ge=1, le=365)
    remind_at: str | None = None


class BatchTaskCopy(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class WeekReviewUpsert(BaseModel):
    accomplishments: str = Field(default="", max_length=10000)
    blockers: str = Field(default="", max_length=10000)
    next_week_focus: str = Field(default="", max_length=10000)
    energy_score: int = Field(default=3, ge=1, le=5)


class WeeklyReportUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    executive_summary: str = Field(default="", max_length=10000)
    highlights: str = Field(default="", max_length=20000)
    risks: str = Field(default="", max_length=20000)
    next_week_plan: str = Field(default="", max_length=20000)
    metrics: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "final"] = "draft"
    change_summary: str = Field(default="", max_length=1000)


class NoteCreate(BaseModel):
    type: str = Field(default="随手记录", min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=100000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    related_entity_type: str | None = Field(default=None, max_length=40)
    related_entity_id: str | None = Field(default=None, max_length=80)
    is_favorite: bool = False
    is_archived: bool = False


class NoteUpdate(BaseModel):
    type: str | None = Field(default=None, min_length=1, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, max_length=100000)
    tags: list[str] | None = Field(default=None, max_length=20)
    related_entity_type: str | None = Field(default=None, max_length=40)
    related_entity_id: str | None = Field(default=None, max_length=80)
    is_favorite: bool | None = None
    is_archived: bool | None = None


class NoteAssistRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=20000)
    exclude_id: str | None = Field(default=None, max_length=80)


class SqlAssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=4000)
    sql_text: str = Field(default="", max_length=200000)
    current_version: str = Field(default="v1.0", max_length=30)
    status: Literal["draft", "validated", "archived"] = "draft"
    tags: list[str] = Field(default_factory=list, max_length=30)
    table_names: list[str] = Field(default_factory=list, max_length=100)
    related_project_id: str | None = Field(default=None, max_length=80)


class SqlAssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, max_length=4000)
    sql_text: str | None = Field(default=None, max_length=200000)
    current_version: str | None = Field(default=None, max_length=30)
    status: Literal["draft", "validated", "archived"] | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    table_names: list[str] | None = Field(default=None, max_length=100)
    related_project_id: str | None = Field(default=None, max_length=80)
    validation_note: str | None = Field(default=None, max_length=4000)


class SqlVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=30)
    sql_text: str = Field(default="", max_length=200000)
    change_summary: str = Field(default="", max_length=4000)
    validation_status: Literal["draft", "validated", "archived"] = "draft"


class SqlAssistRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    sql_text: str = Field(min_length=1, max_length=200000)


class ModelRunCreate(BaseModel):
    started_at: str
    finished_at: str | None = None
    status: Literal["running", "success", "failed", "cancelled"] = "success"
    scanned_count: int = Field(default=0, ge=0)
    hit_count: int = Field(default=0, ge=0)
    reviewed_count: int = Field(default=0, ge=0)
    result_summary: str = Field(default="", max_length=4000)


class ModelRunUpdate(BaseModel):
    finished_at: str | None = None
    status: Literal["running", "success", "failed", "cancelled"] | None = None
    scanned_count: int | None = Field(default=None, ge=0)
    hit_count: int | None = Field(default=None, ge=0)
    reviewed_count: int | None = Field(default=None, ge=0)
    result_summary: str | None = Field(default=None, max_length=4000)


class ModelStep(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    done: bool = False


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=4000)
    status: Literal["normal", "update_due", "paused", "archived"] = "normal"
    schedule: str = Field(default="", max_length=100)
    current_version: str = Field(default="v1.0", max_length=30)
    rule_definitions: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    dependency_ids: list[str] = Field(default_factory=list, max_length=100)
    related_sql_ids: list[str] = Field(default_factory=list, max_length=100)
    update_steps: list[ModelStep] = Field(default_factory=list, max_length=30)
    sql_text: str = Field(default="", max_length=200000)
    sql_current_version: str = Field(default="v1.0", min_length=1, max_length=40)
    change_summary: str = Field(default="创建监测模型", max_length=1000)


class ModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, max_length=4000)
    status: Literal["normal", "update_due", "paused", "archived"] | None = None
    schedule: str | None = Field(default=None, max_length=100)
    current_version: str | None = Field(default=None, max_length=30)
    rule_definitions: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    dependency_ids: list[str] | None = Field(default=None, max_length=100)
    related_sql_ids: list[str] | None = Field(default=None, max_length=100)
    update_steps: list[ModelStep] | None = Field(default=None, max_length=30)
    sql_text: str | None = Field(default=None, max_length=200000)
    sql_current_version: str | None = Field(default=None, min_length=1, max_length=40)
    change_summary: str | None = Field(default=None, max_length=1000)


class ModelSqlVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    sql_text: str = Field(default="", max_length=200000)
    change_summary: str = Field(default="", max_length=2000)


class ProjectRelationCreate(BaseModel):
    entity_type: Literal["task", "data_request", "sql_asset", "model", "note"]
    entity_id: str = Field(min_length=1, max_length=80)
    relation_type: Literal["supporting", "delivery", "dependency", "evidence"] = "supporting"
    note: str = Field(default="", max_length=1000)


MonitorCycle = Literal["日", "周", "月", "季", "年", "按需"]
LedgerCategory = Literal["员工监管类", "经销商监管类", "合作商监管类", "AI助力管理类", "其他"]


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, min_length=1, max_length=40)
    goal: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "paused", "done", "archived"] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    due_date: str | None = None
    next_action: str | None = Field(default=None, max_length=1000)
    category: LedgerCategory | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    monitor_cycle: MonitorCycle | None = None
    cycle_note: str | None = Field(default=None, max_length=2000)
    plan_detail: str | None = Field(default=None, max_length=20000)
    monitor_logic: str | None = Field(default=None, max_length=20000)
    code_backup: str | None = Field(default=None, max_length=200000)
    code_note: str | None = Field(default=None, max_length=4000)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(default="monitor", min_length=1, max_length=40)
    goal: str = Field(default="", max_length=4000)
    status: Literal["active", "paused", "done", "archived"] = "active"
    progress: int = Field(default=0, ge=0, le=100)
    due_date: str | None = None
    next_action: str = Field(default="", max_length=1000)
    template_id: str | None = Field(default=None, max_length=80)
    category: LedgerCategory = "员工监管类"
    sort_order: int = Field(default=0, ge=0, le=100000)
    monitor_cycle: MonitorCycle = "按需"
    cycle_note: str = Field(default="", max_length=2000)
    plan_detail: str = Field(default="", max_length=20000)
    monitor_logic: str = Field(default="", max_length=20000)
    code_backup: str = Field(default="", max_length=200000)
    code_note: str = Field(default="", max_length=4000)


class ProjectStepCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=4000)
    status: Literal["pending", "done"] = "pending"
    sort_order: int = Field(default=0, ge=0, le=100000)


class ProjectStepUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=4000)
    status: Literal["pending", "done"] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)


class ProjectExecutionCreate(BaseModel):
    executed_at: str | None = None
    result: Literal["success", "partial", "failed"] = "success"
    summary: str = Field(default="", max_length=4000)
    evidence_note: str = Field(default="", max_length=4000)


class ProjectExecutionUpdate(BaseModel):
    executed_at: str | None = None
    result: Literal["success", "partial", "failed"] | None = None
    summary: str | None = Field(default=None, max_length=4000)
    evidence_note: str | None = Field(default=None, max_length=4000)


class ProjectTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_type: str = Field(default="analysis", min_length=1, max_length=40)
    description: str = Field(default="", max_length=1000)
    goal_template: str = Field(default="", max_length=4000)
    next_action_template: str = Field(default="", max_length=1000)
    checklist: list[str] = Field(default_factory=list, max_length=40)


class ProjectTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    project_type: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=1000)
    goal_template: str | None = Field(default=None, max_length=4000)
    next_action_template: str | None = Field(default=None, max_length=1000)
    checklist: list[str] | None = Field(default=None, max_length=40)


class NavigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2000)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="常用工具", min_length=1, max_length=50)
    icon_text: str = Field(default="链", min_length=1, max_length=4)
    color: Literal["blue", "cyan", "green", "orange", "violet", "gray"] = "blue"
    sort_order: int = Field(default=0, ge=0, le=100000)
    show_on_home: bool = True


class NavigationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    icon_text: str | None = Field(default=None, min_length=1, max_length=4)
    color: Literal["blue", "cyan", "green", "orange", "violet", "gray"] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    show_on_home: bool | None = None


class ProcedureCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    database_name: str = Field(default="", max_length=100)
    schema_name: str = Field(default="", max_length=100)
    purpose: str = Field(default="", max_length=4000)
    status: Literal["draft", "testing", "active", "paused", "archived"] = "draft"
    current_version: str = Field(default="v1.0", max_length=30)
    owner: str = Field(default="", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)
    definition_text: str = Field(default="", max_length=300000)
    rollback_text: str = Field(default="", max_length=300000)
    related_project_id: str | None = Field(default=None, max_length=80)
    change_summary: str = Field(default="创建存储过程资产", max_length=2000)


class ProcedureUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    database_name: str | None = Field(default=None, max_length=100)
    schema_name: str | None = Field(default=None, max_length=100)
    purpose: str | None = Field(default=None, max_length=4000)
    status: Literal["draft", "testing", "active", "paused", "archived"] | None = None
    current_version: str | None = Field(default=None, max_length=30)
    owner: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None, max_length=30)
    definition_text: str | None = Field(default=None, max_length=300000)
    rollback_text: str | None = Field(default=None, max_length=300000)
    related_project_id: str | None = Field(default=None, max_length=80)
    change_summary: str | None = Field(default=None, max_length=2000)


class ProcedureDeploymentCreate(BaseModel):
    version: str = Field(min_length=1, max_length=30)
    environment: Literal["development", "testing", "production"]
    status: Literal["planned", "success", "failed", "rolled_back"] = "planned"
    deployed_at: str | None = None
    validation_result: str = Field(default="", max_length=4000)
    rollback_executed: bool = False
    notes: str = Field(default="", max_length=4000)


ReportTemplateType = Literal["weekly", "project", "model", "audit", "custom"]


class ReportCover(BaseModel):
    enabled: bool = False
    org_name: str = Field(default="", max_length=120)
    subtitle: str = Field(default="", max_length=200)
    footer: str = Field(default="", max_length=200)


class ReportTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: ReportTemplateType = "custom"
    description: str = Field(default="", max_length=1000)
    section_labels: dict[str, str] = Field(default_factory=dict)
    cover: ReportCover = Field(default_factory=ReportCover)


class ReportTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: ReportTemplateType | None = None
    description: str | None = Field(default=None, max_length=1000)
    section_labels: dict[str, str] | None = None
    cover: ReportCover | None = None


class ReportTemplateImport(BaseModel):
    templates: list[ReportTemplateCreate] = Field(min_length=1, max_length=50)
    mode: Literal["insert_only", "merge"] = "insert_only"


class GenericReportUpsert(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    period_start: str | None = None
    period_end: str | None = None
    related_entity_id: str | None = Field(default=None, max_length=80)
    sections: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "final"] = "draft"
    change_summary: str = Field(default="", max_length=1000)


class GenericReportGenerate(BaseModel):
    template_id: str = Field(min_length=1, max_length=80)
    period_start: str
    period_end: str
    related_entity_id: str | None = Field(default=None, max_length=80)


class DataImportPayload(BaseModel):
    schema_version: str = Field(default="0.8.0", max_length=20)
    mode: Literal["insert_only", "merge"] = "insert_only"
    tables: dict[str, list[dict[str, Any]]]


class CsvImportPayload(BaseModel):
    entity: str = Field(min_length=1, max_length=40)
    csv_text: str = Field(min_length=1, max_length=5_000_000)
    mode: Literal["insert_only", "merge"] = "insert_only"


class TableRestorePayload(BaseModel):
    tables: list[str] = Field(min_length=1, max_length=40)


class AISettingsUpdate(BaseModel):
    enabled: bool | None = None
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    timeout_seconds: int | None = Field(default=None, ge=10, le=300)
    include_sql_text: bool | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)


class DingTalkCalendarSettingsUpdate(BaseModel):
    enabled: bool | None = None
    provider: Literal["ics", "dingtalk", "caldav"] | None = None
    ics_url: str | None = Field(default=None, max_length=2000)
    app_key: str | None = Field(default=None, max_length=200)
    app_secret: str | None = Field(default=None, max_length=500)
    clear_app_secret: bool = False
    calendar_id: str | None = Field(default=None, max_length=200)
    caldav_url: str | None = Field(default=None, max_length=500)
    caldav_username: str | None = Field(default=None, max_length=200)
    caldav_password: str | None = Field(default=None, max_length=500)
    clear_caldav_password: bool = False
    caldav_path: str | None = Field(default=None, max_length=500)
    sync_days_back: int | None = Field(default=None, ge=0, le=90)
    sync_days_forward: int | None = Field(default=None, ge=1, le=120)


class SettingsUpdate(BaseModel):
    backup_retention: int | None = Field(default=None, ge=3, le=200)
    auto_backup_hours: int | None = Field(default=None, ge=0, le=720)
    home_layout: list[str] | None = Field(default=None, max_length=12)
    ai: AISettingsUpdate | None = None
    dingtalk_calendar: DingTalkCalendarSettingsUpdate | None = None
    access_password: str | None = Field(default=None, max_length=200)
    clear_access_password: bool = False


class AccessUnlock(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class CalendarSubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["ics", "dingtalk", "caldav"] = "ics"
    ics_url: str = Field(default="", max_length=2000)
    enabled: bool = True
    caldav_url: str = Field(default="", max_length=500)
    caldav_username: str = Field(default="", max_length=200)
    caldav_password: str = Field(default="", max_length=500)
    caldav_path: str = Field(default="", max_length=500)


class CalendarSubscriptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: Literal["ics", "dingtalk", "caldav"] | None = None
    ics_url: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    caldav_url: str | None = Field(default=None, max_length=500)
    caldav_username: str | None = Field(default=None, max_length=200)
    caldav_password: str | None = Field(default=None, max_length=500)
    clear_caldav_password: bool = False
    caldav_path: str | None = Field(default=None, max_length=500)


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=100)
    types: str = Field(default="", max_length=200)


class SavedSearchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    query: str | None = Field(default=None, min_length=1, max_length=100)
    types: str | None = Field(default=None, max_length=200)


RequestStatus = Literal["pending", "waiting", "working", "done", "archived"]


class DataRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=4000)
    scope: str = Field(default="", max_length=4000)
    caliber_notes: str = Field(default="", max_length=4000)
    due_at: str | None = None
    status: RequestStatus = "pending"
    requester: str = Field(default="", max_length=100)
    department: str = Field(default="", max_length=100)
    sql_text: str = Field(default="", max_length=200000)
    sql_current_version: str = Field(default="v1.0", min_length=1, max_length=40)


class DataRequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, max_length=4000)
    scope: str | None = Field(default=None, max_length=4000)
    caliber_notes: str | None = Field(default=None, max_length=4000)
    due_at: str | None = None
    status: RequestStatus | None = None
    requester: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    sql_text: str | None = Field(default=None, max_length=200000)
    sql_current_version: str | None = Field(default=None, min_length=1, max_length=40)


class DataRequestSqlVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    sql_text: str = Field(default="", max_length=200000)
    change_summary: str = Field(default="", max_length=2000)


class BatchIds(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class BatchSqlStatus(BatchIds):
    status: Literal["draft", "validated", "archived"]


class BatchRequestStatus(BatchIds):
    status: RequestStatus
