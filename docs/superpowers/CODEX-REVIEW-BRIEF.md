# Codex 审阅 Brief — AI 资讯管家 v1.0

**项目:** AI 资讯管家 (ai-news-digest)
**版本:** v1.0
**状态:** 233 tests passing, 9 个版本交付完成
**日期:** 2026-06-10

---

## 一、项目概述

一个本地运行的个人 AI 资讯学习工具。不是资讯推送器，是 **AI 学习导师** —— 帮用户把表层信息转化为可理解的深度知识。

**核心链路:**
```
5源采集(RSS/arXiv/HN/GitHub/Reddit) → URL去重 → TF-IDF聚类
  → Web面板(暗色主题+htmx) → 用户点开某条 → AI深度解读(DeepSeek)
  → 知识图谱(概念提取+生命周期+关联)
  → 企微Webhook + Telegram 推送
```

**技术栈:** Python 3.13 / FastAPI / SQLite + FTS5 / Jinja2 / htmx / 暗色主题 / 零 JS 框架
**环境:** Windows 10, 本地 127.0.0.1, 手动触发, 单用户
**测试:** 233 tests, 82% 覆盖率, pytest
**Commits:** ~50+, 格式 `type: description` (feat/fix/docs)

---

## 二、审阅目标

按优先级排序，每个发现标注 文件:行号 + 严重程度 + 修复建议。

### P0 — Bug & 安全（必须找出来）

- **逻辑错误:** 边界条件、并发问题、DB 锁、资源泄漏、状态不一致
- **安全:** SQL 注入（验证全参数化查询）、XSS（用户输入渲染）、密钥泄露（API Key 在代码/日志中）、路径遍历、SSRF
- **数据完整性:** 去重是否可靠、聚类结果是否正确、概念节点写入/读取一致性

### P1 — 架构 & 性能

- **模块边界:** 循环依赖、抽象泄漏、职责重叠
- **性能:** N+1 查询、重复计算、大循环中的低效操作、未关闭的文件/连接、多余 DB commit
- **可维护性:** 哪些地方未来改一行会炸一片

### P2 — 代码质量

- **死代码:** 未使用的函数、类、import、变量
- **错误处理:** 遗漏的 try/except、静默吞异常
- **重复逻辑:** 同样的代码出现两次以上
- **命名:** 误导性的变量名、不一致的命名风格

### P3 — 体验 & 优化建议

- **UI:** 死链接、错误文案、空态处理、加载态
- **简化:** 过度设计的部分、可以用更简单方式实现的逻辑
- **测试:** 假通过的测试、过度 mock 导致测试无效、遗漏的边界用例

---

## 三、参考材料（必读）

按阅读顺序：

1. **`docs/superpowers/PROJECT-OVERVIEW.md`** — 项目总览，含完整 A-F 开发循环、11 条开发铁律、Bug Hunting 四 Hunter 机制、版本历史、风险约束
2. **`docs/superpowers/specs/2026-06-10-ai-news-digest-v1.0-design.md`** — v1.0 设计 spec
3. **`docs/superpowers/plans/2026-06-10-ai-news-digest-v1.0.md`** — v1.0 实现 plan（8 tasks → 8+ commits）
4. **`docs/superpowers/reports/2026-06-10-cycle-8-report.md`** — v1.0 周期报告，含 A→F 全流程记录
5. **`docs/superpowers/reports/`** — 历史 7 个 cycle reports，了解项目演进

---

## 四、审阅方法

### 第一步：跑起来

```bash
cd D:\Projects\ai-news-digest
.venv\Scripts\python.exe -m pytest tests/ -v    # 确认 233 pass
# 双击 ai-news.bat 看真实运行效果
```

### 第二步：从关键路径读起

```
main.py          → 编排入口，采集+聚类+推送+Web 启动
pipeline/        → 采集器、去重、聚类、管道编排
web/             → FastAPI routes + Jinja2 templates
ai/              → DeepSeek client、分析 prompt、概念提取、生命周期
db/              → SQLite schema、CRUD、FTS5 搜索
```

### 第三步：对照规则验证

PROJECT-OVERVIEW.md 中的 11 条铁律（R1-R11），逐条检查代码是否真的遵守了。特别注意：
- **R3:** htmx endpoint 是否都返回 HTMLResponse（不是 JSON）
- **R4:** 函数被重命名/删除后是否 grep 了所有调用方
- **R7:** task 间审查是否真的执行了
- **R10:** Phase T (T1-T8 门禁) 是否每次完整执行

### 第四步：四 Hunter 扫描

按 PROJECT-OVERVIEW.md 中定义的 Bug Hunting 四 Hunter 执行：

| Hunter | 扫描内容 |
|--------|---------|
| **边界猎人** | 空输入、超长输入、并发竞态、超时、DB 锁、零文章/单文章场景 |
| **体验猎人** | UI 死链接、错误文案、加载态缺失、空态处理、暗色主题一致性 |
| **安全猎人** | SQL 注入（所有 SQL 字符串拼接）、XSS（模板中 `| safe` 使用）、密钥硬编码、路径遍历 |
| **正确性猎人** | 逻辑矛盾、数据不一致、错误处理遗漏、状态机转换是否合法 |

---

## 五、关键上下文

- **用户是学习者**，不是工程师。界面和信息架构要降低认知负担
- **AI 按需调用** — 采集时只拿标题+摘要，AI 分析只在用户点开时触发（省 token）
- **核心价值** — "这意味着什么？" 是用户最看重的功能
- **LLM 是 DeepSeek** — 不是 Claude，prompt 设计和重试策略针对性优化
- **特殊约束** — Windows 10, CWD 可能变成 System32（子代理无写权限）, 无固定 IP
- **单用户** — 无认证、无多租户、服务器绑定 127.0.0.1
- **离线优先** — 所有静态资源本地存放，不依赖 CDN/Node.js

---

## 六、输出格式

```
## 审阅报告

### P0 — Bug & 安全 (N 条)
- [文件:行号] 问题描述 → 修复建议

### P1 — 架构 & 性能 (N 条)
- [文件:行号] 问题描述 → 修复建议

### P2 — 代码质量 (N 条)
- [文件:行号] 问题描述 → 修复建议

### P3 — 体验 & 优化 (N 条)
- [文件:行号] 问题描述 → 修复建议

### 总体评价
（一段话总结项目整体质量、最大风险、最值得改进的方向）
```

---

## 七、Codex 交接验证清单

v1.0 开发过程中声称遵守了以下 8 条规范。请验证每条是否真实执行：

| # | 规则 | 验证方式 |
|---|------|---------|
| 1 | 零 ad-hoc 修改 | 检查所有 commit 是否有对应的 spec/plan/task |
| 2 | Cycle Report 先于验收 | 报告中的测试数/commit 数与 `git log` + `pytest` 一致 |
| 3 | 测试只增不减 | 28→233, 确认无测试被删除 |
| 4 | 安全归零 | 全参数化 SQL，无 XSS/注入/泄露 |
| 5 | Commit 消息规范 | feat/fix/docs 格式一致 |
| 6 | PROJECT-OVERVIEW 同步 | 文档版本号与实际代码一致 |
| 7 | Spec→Plan→Code 可追溯 | 每个 spec requirement → plan task → commit |
| 8 | 文档语言统一 | 中文文档 + 英文 commit |
