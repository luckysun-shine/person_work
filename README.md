# 审计 AI 个人工作台

面向审计监察数据分析师的本地单用户工作台，把日常工作串成可追溯闭环：

`工作请求 → 周计划 → SQL 取数 → 模型维护 → 项目推进 → 记录复盘 → 周报输出`

正式应用位于 [`audit-ai-workbench-ui/workbench-v2`](audit-ai-workbench-ui/workbench-v2)，当前版本 **v1.9.0**。

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
| `audit-ai-workbench-ui/design-demos/` | 早期视觉方向 HTML 原型 |
| `audit-ai-workbench-ui/*.md` | 产品事实、设计规范与方向说明 |
| `审计监察数据分析师个人工作台产品需求说明书_v0.1.docx` | 产品需求原稿 |

## 能力概览

- 12 个工作区：今日、本周计划、报告助手、数据请求、统一检索、SQL 资产、存储过程、监测模型、项目与报告、工作记录、常用导航、数据管理
- 本地持久化：FastAPI + SQLite；导入/恢复前自动安全备份
- 报告输出：Markdown、Word、PDF；支持定稿、版本历史与封面配置
- 数据安全：备份保留策略、导入差异预览、按表恢复
- 统一检索：键盘选择、最近搜索、保存检索条件
- AI 配置（OpenAI 兼容）、可选访问密码、钉钉/ICS 日程只读同步
- Docker 部署（数据卷持久化）
- 统计复盘下钻、任务重复/耗时、项目模板、记录收藏归档
- 首页拖拽布局、工作记录 Markdown 预览
- 今日催办条、周报一键润色、访问密码失败锁定与备份可见性
- **不连接、不执行**真实业务数据库 SQL（只读 SQL 执行另开设计，未纳入本版）

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
