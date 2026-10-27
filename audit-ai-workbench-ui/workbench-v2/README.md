# 数智审监工作台 V2（v1.9.30）

面向审计监察数据分析师的本地单用户工作台，围绕以下工作闭环组织：

`工作请求 → 周计划 / 日程 → SQL 取数 → 模型维护 → 审监监测台账 → 记录复盘 → 周报输出`

界面主题为 **Soft Welcome**（`ui-soft-welcome.css` + `theme-soft-welcome`）。同一应用可在电脑与手机浏览器打开；Docker 部署后可通过局域网 IP 在手机访问。

## 当前内容

- 12 个工作区：今日、本周计划、统计复盘、数据请求、统一检索、SQL 资产、存储过程、监测模型、审监监测台账、工作记录、常用导航、数据管理。
- 今日：焦点监管、本周日历、待办勾选完成、日程、数据请求/SQL/模型摘要、快捷入口；侧栏角标按真实未完成/待更新数量更新。
- 本周计划：周一至周日；任务计划与订阅日程同列展示；卡片「完成 / 恢复」；工具栏「同步日历」；本周/下周/以后/已完成；拖动改期；周复盘。
- 数据请求：独立日常取数存档；新增、编辑、删除、组合筛选与批量操作；记录主题、用途、需求人/部门、范围口径与 SQL；支持 **SQL 代码多版本**（另存、恢复、历史列表）。
- SQL 资产：版本历史、diff、敏感检查、详情抽屉、批量验证/删除。
- 监测模型：规则、依赖、关联 SQL、更新步骤勾选、运行记录。
- 审监监测台账：预置四大类 22 项；分类 Tab + 搜索 + 新增；详情五 Tab（概览与周期 / 规划与监管逻辑 / 代码备份 / 更新步骤 / 执行记录）；可关联 SQL/模型等。
- 工作记录：Markdown、收藏/归档、修订历史。
- 常用导航：分组、搜索、首页展示开关、访问统计。
- 存储过程：定义/回滚、版本、环境发布记录。
- 统一检索：键盘选择、最近搜索、保存条件；覆盖任务/请求/SQL/过程/模型/台账/记录。
- 数据管理：备份保留、导入差异预览、整库/按表恢复；AI / 访问密码 / 钉钉 CalDAV·ICS。
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
- `backend/routers/`：域路由（tasks / projects / calendar / requests 等）
- `backend/db.py`：表结构、迁移、台账种子
- `backend/calendar_sync.py`：ICS / CalDAV
- `tests/`：API 与冒烟测试

## 版本记录

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

- 任务重复/耗时；请求组合筛选；记录收藏归档；统计下钻；项目模板；定时备份。

### 更早版本

见 Git 历史；含 AI 配置、Docker、ICS、报告定稿与统一检索等。

## 测试

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```
