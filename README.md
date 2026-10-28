# 数智审监工作台（Person Works）

面向审计监察数据分析师的本地单用户工作台，把日常工作串成可追溯闭环：

`工作请求 → 周计划 / 日程 → SQL 取数 → 模型维护 → 审监监测台账 → 记录复盘 → 周报输出`

正式应用位于 [`audit-ai-workbench-ui/workbench-v2`](audit-ai-workbench-ui/workbench-v2)，当前版本 **v1.9.37**。

界面主题：**Soft Welcome**（固定浅色）。同一套页面同时适配 **电脑浏览器** 与 **手机浏览器**（底部快捷栏 + 抽屉导航）。

## 快速开始（本机）

```powershell
cd audit-ai-workbench-ui\workbench-v2
.\setup.ps1
.\run.ps1
```

- 电脑：http://127.0.0.1:8765/
- 手机（同一 Wi‑Fi）：http://\<电脑局域网IP\>:8765/  
  （`run.ps1` 默认监听 `0.0.0.0`；可用 `$env:WORKBENCH_HOST='127.0.0.1'` 限制仅本机）

## Docker 部署（电脑 + 手机）

```powershell
cd audit-ai-workbench-ui\workbench-v2
$env:WORKBENCH_SECRET = "请替换为随机密钥"
docker compose up -d --build
```

- 电脑访问：http://127.0.0.1:8765/
- 手机访问：http://\<服务器或电脑局域网IP\>:8765/
- 数据卷：`workbench-data`（SQLite 持久化）
- 可选：`$env:WORKBENCH_PORT='8765'` 改映射端口

镜像已包含 Soft Welcome 主题样式（`ui-soft-welcome.css`）及完整前端资源。

## 手机端使用要点

| 能力 | 说明 |
|---|---|
| 底部栏 | 今日 / 本周 / 请求 / 台账 / 更多 |
| 更多 | 打开完整侧栏导航（检索、SQL 资产、存储过程、工作记录、常用导航、数据管理等） |
| 本周计划 | 横向滑动日列；可完成任务、同步日历 |
| 台账 / 请求 | 单列卡片与表单；弹窗适配窄屏 |
| 安全区 | 支持刘海屏 `safe-area` 与 `viewport-fit=cover` |

复杂编辑（长 SQL、数据管理）建议在电脑端完成；手机侧重查看、催办与轻量操作。

## 仓库结构

| 路径 | 说明 |
|---|---|
| `audit-ai-workbench-ui/workbench-v2/` | 正式应用（HTML/JS + FastAPI + SQLite + Docker） |
| `audit-ai-workbench-ui/design-demos/` | Soft Welcome 等视觉方向原型 |
| `audit-ai-workbench-ui/*.md` | 产品事实、设计规范与方向说明 |

## 能力概览

- 10 个工作区：今日、本周计划、数据请求、统一检索、SQL 资产、存储过程、审监监测台账（含监测模型）、工作记录、常用导航、数据管理
- 审监监测台账：总览指标、统一「待关注」口径、模型绑定 / 运行记录 / 复核、更新步骤与执行记录
- 数据请求独立存档与 SQL 多版本；本周计划与日程同列、拖动改期、周复盘
- Soft Welcome 响应式：电脑侧栏导航 / 手机底栏+抽屉
- FastAPI + SQLite；备份导入/合并同步/恢复；钉钉 CalDAV / ICS；可选访问密码
- MCP（`/mcp`，Bearer Token）：给 Cursor / 后期 Grok Bot 查询今日、周计划、台账与轻量写入
- **不连接、不执行**真实业务库 SQL

## 测试

```powershell
cd audit-ai-workbench-ui\workbench-v2
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

细节见 [`audit-ai-workbench-ui/workbench-v2/README.md`](audit-ai-workbench-ui/workbench-v2/README.md)。
