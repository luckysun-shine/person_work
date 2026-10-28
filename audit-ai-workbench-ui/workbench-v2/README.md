# 数智审监工作台 V2（v1.9.36）

面向审计监察数据分析师的本地单用户工作台，围绕以下工作闭环组织：

`工作请求 → 周计划 / 日程 → SQL 取数 → 模型维护 → 审监监测台账 → 记录复盘 → 周报输出`

界面主题为 **Soft Welcome**（`ui-soft-welcome.css` + `theme-soft-welcome`），固定浅色外观。同一应用可在电脑与手机浏览器打开；Docker 部署后可通过局域网 IP 在手机访问。

## 当前内容

- 10 个工作区：今日、本周计划、数据请求、统一检索、SQL 资产、存储过程、审监监测台账（含监测模型）、工作记录、常用导航、数据管理。
- 顶栏：全局搜索（`Ctrl/⌘ K`）、AI 状态芯片（点击进入 AI 配置）、快速新建。
- 今日：焦点监管、本周日历、待办勾选完成、日程、数据请求/SQL/模型摘要、快捷入口；侧栏角标按真实未完成/待更新数量更新。
- 本周计划：周一至周日；任务计划与订阅日程同列展示；卡片「完成 / 恢复」；工具栏「同步日历」；本周/下周/以后/已完成；拖动改期；周复盘。
- 数据请求：独立日常取数存档；摘要指标为「全部请求 / 处理中 / 本月已交付 / 平均交付用时」；新增、编辑、删除、组合筛选与批量操作；记录主题、用途、需求人/部门、范围口径与 SQL；支持 **SQL 代码多版本**（另存、恢复、历史列表）。
- SQL 资产：版本历史、diff、敏感检查、详情抽屉、批量验证/删除。
- 审监监测台账：预置四大类监管项；总览五指标（监管项 / 进行中 / 绑定模型 / 待关注 / 待办步骤）+ 分类/待关注筛选，列表、卡片与详情共用同一套「待关注」口径；详情六 Tab（概览 / 规划逻辑 / **监测模型** / 代码备份 / 更新步骤 / 执行记录），模型 Tab 数据按需加载；模型可新建绑定、从下拉选择已有模型绑定、记录运行、标记运行已复核、删除运行记录、解除绑定；详情有未保存修改时关闭会二次确认。
- 工作记录：Markdown、收藏/归档、修订历史。
- 常用导航：分组、搜索、首页展示开关、访问统计。
- 存储过程：定义/回滚、版本、环境发布记录。
- 统一检索：键盘选择、最近搜索、保存条件；覆盖任务/请求/SQL/过程/模型/台账/记录。
- 数据管理：备份保留、导入 `.db` 备份后合并同步或整库/按表恢复、JSON/CSV 差异预览；AI / 访问密码 / 钉钉 CalDAV·ICS。
- 本地持久化：FastAPI + SQLite 增量迁移；离线演示模式降级。
- Docker：`Dockerfile` + `docker-compose.yml`。
- **不连接、不执行**真实业务库 SQL。

## 首次安装

```powershell
.\setup.ps1
```

## 启动

```powershell
.\run.ps1
```

访问 http://127.0.0.1:8765/ ，API 文档见 `/docs`。

## Docker（电脑 + 手机）

```powershell
$env:WORKBENCH_SECRET = "请替换为随机密钥"
docker compose up -d --build
```

- 电脑：http://127.0.0.1:8765/
- 手机：http://\<主机局域网IP\>:8765/（容器已监听 `0.0.0.0`）
- 端口：`WORKBENCH_PORT`（默认 8765）
- 数据卷：`workbench-data` → `/data`
- 环境变量：`WORKBENCH_SECRET`、`WORKBENCH_PORT`、`WORKBENCH_DATA_DIR`、`WORKBENCH_HOST`
- 镜像包含：`index.html`、`app.js`、`styles.css`、`ui-apple-hig.css`、`ui-soft-welcome.css`、`backend/`

## 手机浏览

- ≤760px：底部快捷栏（今日 / 本周 / 请求 / 台账 / 更多）+ 抽屉完整导航
- 本周计划日列横向滑动；列表/台账/表单改为单列；弹层与抽屉适配安全区
- 本机开发：`.\run.ps1` 默认 `--host 0.0.0.0`，手机用电脑 IP 访问

## 关键文件

- `index.html` / `app.js`：页面与交互
- `ui-soft-welcome.css`：Soft Welcome 主题层
- `ui-apple-hig.css` / `styles.css`：基础组件与兼容层
- `backend/main.py`：FastAPI 入口
- `backend/routers/`：域路由（access / tasks / reports / notes / sql / procedures / requests / models / projects / search / settings / calendar / data / frontend）
- `backend/common.py`：共享工具（鉴权、查询、通知）与 `APP_VERSION`
- `backend/db.py`：表结构、迁移、台账种子
- `backend/calendar_sync.py`：ICS / CalDAV
- `tests/`：API 与冒烟测试

## 主要 API（节选）

| 资源 | 端点 |
|---|---|
| 台账 | `GET/POST /api/projects`、`GET/PATCH/DELETE /api/projects/{id}`、`/api/projects/{id}/relations`、`/api/projects/{id}/steps`、`/api/projects/{id}/executions` |
| 监测模型 | `GET/POST /api/models`、`GET/PATCH/DELETE /api/models/{id}`、`GET/POST /api/models/{id}/runs`、`PATCH/DELETE /api/models/{id}/runs/{run_id}`、`/api/models/{id}/sql-versions` |
| 数据请求 | `GET/POST /api/data-requests`、`PATCH/DELETE /api/data-requests/{id}`、`/api/data-requests/{id}/sql-versions`、批量 `batch-status` / `batch-delete` |
| 任务 / 周报 | `/api/tasks`、`GET/PUT /api/weekly-reports/{week_start}`（`generate` / `polish` / `finalize` / `markdown` / `docx` / `pdf`） |
| 设置 / 访问 | `GET/PUT /api/settings`、`/api/access/status` / `unlock` / `lock` |

完整列表见运行后的 `/docs`。

## MCP（Cursor / Grok Bot）

工作台在同一端口提供 Streamable HTTP MCP，供智能体查询计划与台账。默认关闭，设置环境变量后启用：

```powershell
$env:WORKBENCH_MCP_TOKEN = "请换成足够长的随机口令"
```

- 地址：`http://<主机>:8765/mcp`
- 鉴权：`Authorization: Bearer <WORKBENCH_MCP_TOKEN>`
- 传输：Streamable HTTP（JSON-RPC `initialize` / `tools/list` / `tools/call`）
- 工具：`get_today`、`get_week_plan`、`search_workbench`、`get_ledger_attention`、`get_open_requests`、`get_task`、`get_note`、`get_project`、`create_task`、`complete_task`、`add_note`
- 不返回 SQL 正文、备份、密码或密钥

Cursor 本机可直接填上述地址。Grok Bot 需要公网 HTTPS（家里 NAS 可用 Cloudflare Tunnel 等把 `/mcp` 暴露出去）；公司内网通常打不出隧道，那时请用 Cursor 走局域网。

Docker：

```powershell
$env:WORKBENCH_SECRET = "请替换为随机密钥"
$env:WORKBENCH_MCP_TOKEN = "请换成足够长的随机口令"
docker compose up -d --build
```

## 版本记录

### v1.9.36

- 导入的 `.db` 备份改为优先整库恢复；按表恢复会自动带上台账步骤、执行记录、关联等子表。
- 备份里为空的表不再先清空再写入，避免把当前库清成空白。直接复制正在运行的 `workbench.db`（WAL）会被识别为空备份并拒绝恢复。

### v1.9.35

- 数据管理支持导入另一台电脑下载的 SQLite `.db` 备份：校验后加入备份列表，可合并同步到当前库，或整库/按表恢复。
- 合并同步按编号新增或更新任务、请求、SQL、台账等业务数据；访问密码与 AI 密钥不会被覆盖。导入前会自动创建安全备份。

### v1.9.34

- 新增 `/mcp` Streamable HTTP 服务，Bearer Token 鉴权，可供 Cursor 与后期 Grok Bot 连接。
- 登录由简陋弹窗改为整页访问门；首页按时段问候并在右侧显示时钟。
- 手机端布局、筛选栏与搜索框继续按窄屏操作习惯收紧。

### v1.9.33

- 台账列表卡片与详情顶栏均可删除监管项（确认后删除步骤/执行/关联，不删除已绑定模型）。
- 新建监测模型时随 `project_id` 在同一事务写入绑定关系；保存失败会提示，不再静默跳过绑定。
- 解绑模型后台账卡片即时同步，不再需要再保存项目概览。
- 删除、解绑、未保存关闭、AI 确认等改为应用内对话框，不再使用浏览器弹窗。
- 本周计划与首页本周日历的日期改为圆角徽章，今天/周末状态更清晰。

### v1.9.32

- 下线「统计复盘」页面及 `/api/stats`；移除浅色/深色外观切换与头像按钮，界面固定浅色。
- 数据请求摘要去掉「等待确认」指标。
- 台账：统一「待关注」口径；总览改为五指标；模型 Tab 按需加载；支持绑定已有模型、标记运行已复核、删除运行记录；删除监管项时同步清理 SQL / 请求 / 过程 / 任务 / 记录中的软引用；详情未保存修改关闭确认。
- 后端：批量查询台账摘要与最近执行；运行记录新增 PATCH / DELETE；清理路由拆分遗留的近千行无用导入；`APP_VERSION` 与 README 对齐。
- 前端：移除深色模式与外观按钮相关 CSS。

### v1.9.31

- 监测模型并入审监监测台账：独立「监测模型」导航下线，改为台账详情「监测模型」Tab。
- 台账列表增加总览指标、待关注/已绑模型筛选、卡片模型状态；详情支持新建绑定、记录运行、解除绑定。
- 种子补齐采购/资产监测监管项，并与 M-014、M-011 建立关联。

### v1.9.30

- 数据请求改为独立日常取数存档：去掉等待对象、交付方式/位置、敏感说明、下一步、关联 SQL/项目。
- 支持 SQL 代码多版本：另存新版本、版本历史、一键恢复；详情抽屉展示当前版本与历史。

### v1.9.29

- 手机端壳层：底栏快捷导航、抽屉遮罩、安全区与关键页单列/横滑布局。
- Docker 镜像补齐 `ui-soft-welcome.css`；本机 `run.ps1` 默认监听 `0.0.0.0` 便于手机访问。

### v1.9.28

- Soft Welcome 主题全面接入正式工作台。
- 审监监测台账替换「项目与报告」；22 项幂等种子；详情五 Tab。
- 本周计划：整周看板 + 日程同列 + 一键完成 + 本页同步日历。
- 侧栏角标改为真实计数；健康提示显示当前连接时间。
- 钉钉 CalDAV 日程同步能力完善。

### v1.9.24

- 审监监测台账首版：分类列表、详情字段与子资源 API。

### v1.9.0

- 后端路由拆分；访问加固；催办；周报润色确认；CalDAV；冒烟测试。

### v1.8.0

- 首页拖拽布局；工作记录 Markdown；今日数据请求真实数据。

### v1.7.0（P1）

- 任务重复/耗时；请求组合筛选；记录收藏归档；统计下钻（已于 v1.9.32 下线）；项目模板；定时备份。

### 更早版本

见 Git 历史；含 AI 配置、Docker、ICS、报告定稿与统一检索等。

## 测试

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```
