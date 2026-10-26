# 审计 AI 个人工作台 UI 设计规范

版本：1.0  
目标版本：工作台 UI v1 视觉重构  
适用终端：桌面浏览器优先，兼容 iPad 横屏与窄屏窗口

## 1. 设计依据

本规范参考 Apple 官方设计资源与 Human Interface Guidelines，并针对 Web 桌面生产力工具进行转译，不复刻 Apple 品牌页面，也不直接使用 Apple 专有素材。

- [Apple Design](https://developer.apple.com/design/)
- [Design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles)
- [Layout](https://developer.apple.com/design/human-interface-guidelines/layout)
- [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)
- [Color](https://developer.apple.com/design/human-interface-guidelines/color)
- [Typography](https://developer.apple.com/design/human-interface-guidelines/typography)
- [Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Split views](https://developer.apple.com/design/human-interface-guidelines/split-views)
- [Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)
- [Lists and tables](https://developer.apple.com/design/human-interface-guidelines/lists-and-tables)
- [Searching](https://developer.apple.com/design/human-interface-guidelines/searching)
- [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)

## 2. 产品体验目标

### 2.1 核心感受

1. **安静**：界面不与审计数据竞争注意力，减少大面积深色、高饱和色和密集分割线。
2. **清晰**：用户始终知道“我在哪、现在最重要的是什么、下一步能做什么”。
3. **可靠**：状态、风险、自动生成内容和破坏性操作有稳定、可预期的表达。
4. **高效**：鼠标、键盘和触控都能完成主要任务；常用动作不超过两步。
5. **可追溯**：AI 建议与人工内容、草稿与已保存状态必须清楚区分。

### 2.2 设计原则

- 内容优先，控件退后；只有当前可执行操作获得强调。
- 使用留白、对齐和字号建立层级，减少依赖边框和色块。
- 采用渐进披露：先展示结论和关键指标，详细说明按需展开。
- 同一颜色只表达一种含义；颜色不是唯一的状态信息。
- 导航选择持续高亮，保持用户在多栏结构中的位置感。
- 主要动作使用动词，如“新建记录”“保存报告”“运行检查”。

## 3. 信息架构

### 3.1 一级导航

侧栏只保留稳定的工作域，不展示过多计数。

| 分组 | 页面 | 主要目的 |
|---|---|---|
| 工作 | 今日、周计划、报告助手 | 安排与完成工作 |
| 资产 | 数据请求、SQL、监测模型、项目 | 管理审计分析资产 |
| 知识 | 工作记录、统一检索 | 沉淀和查找知识 |
| 系统 | 数据管理 | 备份、导入和导出 |

### 3.2 页面结构

宽屏采用两栏或三栏结构：

```text
┌──────────┬────────────────────────────────────┬──────────────┐
│ Sidebar  │ Toolbar + Content Canvas           │ Inspector    │
│ 240 px   │ flexible                           │ 320–380 px   │
└──────────┴────────────────────────────────────┴──────────────┘
```

- Sidebar：一级导航与工作区状态。
- Content Canvas：列表、看板或报告编辑区。
- Inspector：仅在查看 SQL、任务、模型详情时出现，可隐藏。
- 小于 980 px 时隐藏 Inspector；小于 760 px 时 Sidebar 变为抽屉。

## 4. 视觉系统

### 4.1 字体

```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
  "PingFang SC", "Helvetica Neue", Arial, sans-serif;
```

| 层级 | 字号/行高 | 字重 | 用途 |
|---|---:|---:|---|
| Large title | 32/38 | 700 | 页面名称 |
| Title 2 | 22/28 | 650 | 主要区块 |
| Headline | 15/20 | 600 | 卡片标题、列表主信息 |
| Body | 14/21 | 400 | 正文和说明 |
| Callout | 13/18 | 500 | 次级信息、工具栏 |
| Caption | 11/15 | 500 | 时间、编号、辅助信息 |
| Monospace | 12/18 | 400 | SQL、编号、指标 |

正文不小于 13 px；关键业务正文默认 14 px。支持浏览器缩放至 200% 时不遮挡核心操作。

### 4.2 颜色令牌

颜色使用语义命名，以便未来支持深色模式。

| Token | Light | 用途 |
|---|---|---|
| `--bg-canvas` | `#F5F5F7` | 应用背景 |
| `--bg-surface` | `rgba(255,255,255,.82)` | 卡片与内容面板 |
| `--bg-sidebar` | `rgba(246,246,248,.78)` | 侧栏材料 |
| `--label-primary` | `#1D1D1F` | 主文本 |
| `--label-secondary` | `#6E6E73` | 次文本 |
| `--separator` | `rgba(60,60,67,.14)` | 细分隔线 |
| `--accent` | `#007AFF` | 主要动作与选择 |
| `--success` | `#248A3D` | 成功、已完成 |
| `--warning` | `#B25000` | 待确认、需注意 |
| `--danger` | `#D70015` | 删除、失败、高风险 |
| `--purple` | `#8944AB` | AI 建议与自动生成 |

要求：

- 文字与背景满足 WCAG AA 对比度目标。
- 风险状态同时使用图标、文案和颜色。
- Accent 只用于当前选择和主操作，不用于装饰。

### 4.3 材料与层级

- Sidebar 和 Toolbar 使用轻度半透明材料：`backdrop-filter: blur(24px) saturate(140%)`。
- 内容卡片保持更高不透明度，保证长文本和表格可读性。
- 圆角遵循容器嵌套关系：窗口 22 px、主卡片 16 px、控件 10 px、标签 7 px。
- 阴影只表示浮层：普通卡片不使用明显阴影；Popover、Sheet 使用柔和阴影。
- 不模拟夸张玻璃高光。材料用于区分导航层和内容层，而不是装饰。

### 4.4 间距

采用 4 pt 基础网格：`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40`。

- 页面左右边距：32 px；小窗口 20 px；移动端 16 px。
- 主区块间距：24 px。
- 卡片内边距：20 px。
- 列表行最小高度：56 px；重要列表 64 px。
- 可点击控件目标区域不小于 40×40 px，触控场景建议 44×44 px。

## 5. 核心组件

### 5.1 Sidebar

- 默认宽度 240 px，可折叠到 72 px。
- 当前项使用浅色填充、Accent 图标和中等字重，不使用强烈深色整栏。
- 分组标题使用 11 px 次级文本。
- 数量仅显示需要用户处理的事项，如“3 个待确认”，避免显示无意义总数。
- 底部显示本地数据库状态与最近备份时间。

### 5.2 Toolbar

- 左侧：Sidebar 切换、后退/前进、当前页面标题。
- 中间或右侧：搜索。
- 右侧：不超过三个动作组，突出一个主要动作。
- 图标按钮必须有 Tooltip 和 `aria-label`。
- 随窗口收窄，次要动作进入 More 菜单。

### 5.3 卡片与指标

- 指标卡不重复使用边框套边框。
- 数字是视觉主角，标签置于下方，趋势或状态置于右上角。
- 同一行最多四个主要指标；窄屏自动变为两列。
- 指标必须能点击进入明细，否则不做按钮外观。

### 5.4 列表与表格

- 文本内容左对齐，数字右对齐，状态保持短而稳定。
- 行选择持续高亮；悬停只提供轻微背景反馈。
- 多选、排序、筛选在列表上方工具栏统一出现。
- 复杂表格保留表头，避免每行过多按钮；行级次要动作进入 More。
- 空状态包含原因、下一步动作，不只显示“暂无数据”。

### 5.5 搜索

- 全局搜索使用独立搜索入口并支持 `⌘K / Ctrl K`。
- 输入前显示最近项目和常用查询；输入后显示建议和分类结果。
- 结果按“任务、请求、SQL、模型、记录”分组，可使用 scope chips 缩小范围。
- 高亮匹配文本，但不改变结果原文。

### 5.6 按钮

- Primary：每个视图通常只有一个，如“新建记录”“保存报告”。
- Secondary：普通操作，如“重新生成”“导出”。
- Destructive：红色文字或红色按钮，仅用于删除/恢复覆盖等操作。
- 图标与文案必须表达相同动作，不使用含义不明确的装饰图标。

### 5.7 Sheet、Popover 与 Inspector

- 快速创建使用 Sheet，不遮蔽用户判断所需的上下文。
- SQL、模型、项目详情优先使用右侧 Inspector，保持列表选择关系。
- 确认框只用于不可逆或覆盖性动作。
- AI 建议显示为独立建议区，必须提供“应用建议”，不能自动覆盖人工内容。

## 6. 页面规范

### 6.1 今日

页面顺序：

1. Large title：“今天，先完成最重要的事”。
2. 风险摘要：逾期、受阻、高优先事项。
3. 今日任务列表：时间、标题、关联对象、状态。
4. 工作概览：数据请求、模型待复核、项目进度。

默认只展示与今天行动有关的信息，完整统计进入对应页面。

### 6.2 周计划

- 宽屏使用五列工作日看板；窄屏切换为按日期分组的列表。
- 拖动任务时显示明确目标位置和撤销提示。
- 周复盘与计划分开：计划是执行视图，复盘是周末总结视图。

### 6.3 SQL 资产

- 采用“资产列表 + Inspector”结构。
- 列表突出名称、用途、涉及表、验证状态、更新时间。
- Inspector 分为概览、SQL、版本、关系四个 Tab。
- SQL 使用等宽字体、行号和复制按钮；风险提示不覆盖代码。

### 6.4 监测模型

- 顶部只保留运行健康度、待复核数、失败次数三个指标。
- 模型列表使用状态点和最近运行信息。
- 详情展示规则版本、依赖、运行历史、维护步骤。

### 6.5 报告助手

- 报告编辑区采用单列文档画布，指标作为文档上方摘要。
- AI 生成状态使用紫色语义，不与保存成功的绿色混用。
- “重新生成”不得直接覆盖已保存版本，需生成草稿或提示差异。
- 导出和复制属于次要动作，保存是唯一 Primary。

## 7. 动效与反馈

- 页面切换：120–180 ms 淡入，不做大幅位移。
- Inspector：200 ms 从右侧进入。
- Hover：100 ms；按下态立即反馈。
- 保存成功使用非阻塞 Toast，并在内容附近更新“已保存”状态。
- 加载超过 300 ms 显示骨架；超过 8 秒提供重试与错误原因。
- 尊重 `prefers-reduced-motion`，关闭非必要动画。

## 8. 可访问性与键盘

- 所有操作可以仅使用键盘完成。
- Tab 顺序与视觉阅读顺序一致。
- 当前导航使用 `aria-current="page"`。
- 图标按钮提供可读名称；状态变化通过 `aria-live` 通知。
- Focus ring 使用 Accent 外描边，不移除浏览器焦点。
- 支持深色模式、高对比度、减少动态效果和 200% 页面缩放。
- 不能只靠红/绿区分失败与成功，必须同时显示图标和文字。

## 9. 响应式规则

| 宽度 | 布局 |
|---:|---|
| `≥ 1280` | Sidebar + Content + 可选 Inspector |
| `980–1279` | Sidebar + Content，Inspector 覆盖显示 |
| `760–979` | 可折叠 Sidebar + 单列 Content |
| `< 760` | Sidebar 抽屉，Toolbar 精简，列表替代复杂表格 |

布局变化保持页面名称、主要动作和当前选择稳定，避免在尺寸变化时突然改变用户路径。

## 10. 验收清单

- [ ] 当前页面在 Sidebar 中持续高亮。
- [ ] 每个页面只有一个视觉主操作。
- [ ] 所有图标按钮有 Tooltip 与无障碍名称。
- [ ] 风险、成功、AI 建议采用不同语义颜色和文字。
- [ ] 列表行在 Hover、Focus、Selected 三种状态下清楚可辨。
- [ ] 1280、1024、768、390 px 宽度均无关键内容遮挡。
- [ ] 键盘可以完成导航、搜索、打开详情和保存。
- [ ] 200% 缩放可用；Reduce Motion 生效。
- [ ] 删除、恢复和覆盖操作经过明确确认。
- [ ] 自动生成内容未经人工确认不会覆盖已保存内容。

## 11. 从当前版本迁移

1. 先统一设计令牌、字体、颜色与间距，不改业务逻辑。
2. 将深色固定侧栏替换为浅色材料 Sidebar，并重构 Toolbar。
3. 将 SQL、模型、项目详情统一为 Inspector 模式。
4. 重构今日与列表页面，移除重复统计和静态示例数字。
5. 增加暗色模式、键盘导航与响应式验收。
6. 最后逐页替换生产界面，保留旧版作为可回滚入口。
