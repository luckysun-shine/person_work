# 产品事实

- 产品暂名为审计监察数据分析师个人工作台，第一阶段为单用户、自托管的桌面端网页应用。
- 核心对象包括项目、任务、数据请求、SQL 记录、监测模型、存储过程、工作记录和导航项。
- 本轮只探索 UI 方向，不实现生产后端，也不在页面中连接或执行真实数据库 SQL。
- 代表页面为首页工作台、SQL 查询库、SQL 详情、监测模型详情。
- 主视口为 1440 x 900，同时检查 375 x 812 的窄屏降级。
- 界面数据均为虚构示例，不放入真实审计数据、数据库地址、人员信息或凭据。
- Huashu Design 当前安装版本为 3.0.0，负责方向探索、高保真 HTML 原型和设计验证，不作为生产组件库。
- IBM Carbon 的数据表规范强调搜索、筛选、排序、批量操作和可扩展行，适合作为密集业务列表的现实参考。
- Supabase Dashboard 的 SQL Editor 将保存查询、代码编辑器和数据库对象放在同一工作壳中，适合作为 SQL 资产页面的现实参考。

参考来源

- https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines
- https://supabase.com/database
- https://github.com/alchaincyf/huashu-design

