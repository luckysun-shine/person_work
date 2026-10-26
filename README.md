# 数智审监工作台（Person Works）

面向审计监察数据分析师的本地单用户工作台，把日常工作串成可追溯闭环：

`工作请求 → 周计划 / 日程 → SQL 取数 → 模型维护 → 审监监测台账 → 记录复盘 → 周报输出`

正式应用位于 [`audit-ai-workbench-ui/workbench-v2`](audit-ai-workbench-ui/workbench-v2)，当前版本 **v1.9.28**。

界面主题：**Soft Welcome**（暖黄浅底、胶囊导航、大圆角卡片）。设计方向见 [`audit-ai-workbench-ui/direction-approved.md`](audit-ai-workbench-ui/direction-approved.md)。

## 快速开始

在 PowerShell 中：

```powershell
cd audit-ai-workbench-ui\workbench-v2
.\setup.ps1
.\run.ps1
```

然后打开：

- 工作台：http://127.0.0.1:8765/
- API 文档：http://127.0.0.1:8765/docs

## 仓库结构

| 路径 | 说明 |
|---|---|
| `audit-ai-workbench-ui/workbench-v2/` | 正式应用（HTML/JS + FastAPI + SQLite） |
| `audit-ai-workbench-ui/design-demos/` | Soft Welcome 等视觉方向 HTML 原型 |
| `audit-ai-workbench-ui/*.md` | 产品事实、设计规范与方向说明 |
| `审计监察数据分析师个人工作台产品需求说明书_v0.1.docx` | 产品需求原稿 |

## 能力概览

- 工作区：今日、本周计划、统计复盘、数据请求、统一检索、SQL 资产、存储过程、监测模型、**审监监测台账**、工作记录、常用导航、数据管理
- 本周计划：周一至周日看板；任务与日程同列；一键完成/恢复；本页可同步日历
- 审监监测台账：四大类 22 项预置监管条目；周期、规划逻辑、代码备份、更新步骤、执行记录
- 数据请求：可内嵌 SQL 代码记录，也可关联 SQL 资产
- 本地持久化：FastAPI + SQLite；导入/恢复前自动安全备份
- 钉钉 CalDAV / ICS 日程只读同步；AI 配置（OpenAI 兼容）；可选访问密码
- Docker 部署（数据卷持久化）
- **不连接、不执行**真实业务数据库 SQL

## 测试

```powershell
cd audit-ai-workbench-ui\workbench-v2
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Docker：

```powershell
cd audit-ai-workbench-ui\workbench-v2
$env:WORKBENCH_SECRET = "请替换为随机密钥"
docker compose up -d --build
```

更细的功能说明与版本记录见 [`audit-ai-workbench-ui/workbench-v2/README.md`](audit-ai-workbench-ui/workbench-v2/README.md)。
