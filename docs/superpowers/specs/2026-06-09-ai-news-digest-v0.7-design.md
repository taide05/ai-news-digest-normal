# AI 资讯管家 v0.7 设计规格

**Date:** 2026-06-09
**Status:** Draft
**上一版本:** v0.6 (182 tests, 82% coverage)

---

## 一、范围

v0.7 定位：**数据基础建设**。为 v0.8 趋势追踪和 v1.0 知识图谱做数据准备。

### 包含

1. **概念自动提取** — 打开文章时 AI 自动提取新概念术语
2. **资讯关联图** — `/graph` 页面，当日/本周文章的概念关联网络
3. **双引擎阅读推荐** — 兴趣 + 知识空白两路推荐
4. **Markdown 周刊自动推送** — 每周定时生成 .md 并推送企微/Telegram

### 不包含

- 学习趋势追踪 → v0.8
- 周报增强（整合趋势数据）→ v0.8
- 知识图谱历史存档 → v1.0

---

## 二、依赖链

```
概念自动提取 ──→ 资讯关联图 ──→ 双引擎推荐
                                        │
Markdown 周刊自动推送（独立并行） ←──────┘
```

概念提取是其他模块的数据前提。周刊是独立模块。

---

## 三、模块设计

### 3.1 概念自动提取

**触发:** 用户打开文章阅读页时，core_insight SSE 流完成后自动触发。

**流程:**
1. `reader.html` 中 core_insight 加载完成后，htmx 自动触发 `/api/auto-extract-concepts/{article_id}`
2. endpoint 检查该文章是否已提取过 → 有缓存直接返回
3. AI 扫描 full_text，提取 ≤5 个新概念术语
4. 与现有 concepts 表比对去重
5. 返回新概念列表，前端在文章旁展示"本文新概念：X, Y, Z"
6. 写入 article_concepts 关联

**Prompt 设计:**
```
从以下文章中提取最多 5 个 AI/技术领域的关键概念术语。
只输出逗号分隔的术语列表，不要解释。如果文章不包含值得提取的概念，输出"无"。
```

**数据流:**
```
reader.html (htmx trigger after core_insight)
  → GET /api/auto-extract-concepts/{article_id}
    → check cache (analysis_cache WHERE analysis_type='concepts')
    → ai.chat(extract_prompt, full_text)
    → match against concepts table (exact + fuzzy)
    → insert new concepts + link_article_concept
    → cache result
    → return JSON {concepts: [...], new: true/false}
```

**缓存:** 复用 analysis_cache，analysis_type='concepts'。每篇文章只提取一次。

---

### 3.2 资讯关联图

**页面:** `/graph`，从底部导航进入。

**核心逻辑:**
1. 查询当前日/周的文章及其关联概念
2. 构建图：节点 = 文章 + 概念，边 = article_concepts 关联
3. 前端用简单的力导向布局渲染

**数据查询:**
```sql
-- 当日文章及其概念
SELECT a.id, a.title, c.term
FROM articles a
JOIN article_concepts ac ON a.id = ac.article_id
JOIN concepts c ON ac.concept_id = c.id
WHERE a.fetched_at >= date('now')
ORDER BY c.query_count DESC
```

**前端实现:**
- 纯 HTML + 内联 SVG，不引入 D3.js（保持离线可用）
- 节点大小 = 概念 query_count（热度），文章节点固定大小
- 点击概念节点 → 跳转搜索该概念的文章
- 点击文章节点 → 跳转阅读页

**布局算法:**
简化的力导向：概念推斥 + 文章-概念吸引，迭代 50 轮即可收敛。节点数控制在 ~50 以内（当日数据）。

**时间切换:**
页面顶部两个标签：「今天」/「本周」。默认今天。

---

### 3.3 双引擎阅读推荐

**位置:** 阅读页底部，feedback 区块之后。

**推荐接口:** `GET /api/recommend/{article_id}`

**引擎 A — 兴趣驱动:**
1. 从 read_records.topics 取用户标记"感兴趣"的话题
2. 从当前文章的概念找到关联文章
3. 交集优先 → 按概念匹配数降序
4. 排除已读文章

**引擎 B — 知识空白驱动:**
1. 取所有概念中 query_count 最高的 N 个（热门概念）
2. 排除用户已读文章涉及的概念
3. 找到讨论这些"未接触概念"的文章
4. 按文章新鲜度 + 概念热度排序

**合并策略:**
- 引擎 A 取 top 2，引擎 B 取 top 2
- 去重合并，最多展示 4 篇
- 每篇显示：标题 + 来源 + 为什么推荐（"因为你关注 Agent" / "探索 RLHF 领域"）

**数据流:**
```
reader.html (htmx trigger on load, after full page render)
  → GET /api/recommend/{article_id}
    → engine_a: interest match query
    → engine_b: knowledge gap query
    → merge + dedup, cap at 4
    → return HTML fragment with recommendations
```

---

### 3.4 Markdown 周刊自动推送

**触发:** 复用 v0.5 的 APScheduler，每周一次（如周一早上 8:00）。

**流程:**
1. scheduler 触发 `generate_weekly_review()` (已有)
2. 新增：将 review content 渲染为 Markdown 模板
3. 通过 PushChannel (已有) 推送到企微/Telegram
4. 支持 `/api/export/review/latest` 手动下载 .md 文件

**Markdown 模板:**
```markdown
# AI 资讯周刊 — {week_start} ~ {week_end}

## 本周概览
{review_content}

## 本周热词
{top_concepts}

## 推荐阅读
{recommendations}

---
由 AI 资讯管家自动生成 | {date}
```

**推送策略:**
- 通过 PushChannel 发送 Markdown 文本（企微支持 markdown 消息类型）
- Telegram 用 MarkdownV2 parse_mode
- 同时保存到 weekly_reviews 表（已有，content 字段存 MD 原文）

---

## 四、文件变更清单

| 文件 | 操作 | 对应模块 |
|------|------|---------|
| `ai/analysis.py` | 新增 `build_concept_extraction_prompt` | 3.1 |
| `web/routes/api.py` | 新增 `/api/auto-extract-concepts/{id}`, `/api/recommend/{id}` | 3.1, 3.3 |
| `web/routes/graph.py` | **新建** — `/graph` 页面路由 | 3.2 |
| `web/templates/graph.html` | **新建** — 关联图页面模板 | 3.2 |
| `web/templates/reader.html` | 新增概念提取触发 + 推荐区块 | 3.1, 3.3 |
| `web/templates/home.html` | 底部导航加 `/graph` 入口 | 3.2 |
| `db/models.py` | 新增 `get_graph_data`, `get_recommendations_interest`, `get_recommendations_gap` | 3.2, 3.3 |
| `orchestrator.py` | review 生成改为输出 MD 格式，集成推送 | 3.4 |
| `push/channels.py` | 新增 `send_markdown` 方法（如需要） | 3.4 |
| `scheduler.py` | 新增周报定时推送任务 | 3.4 |
| `tests/test_concept_extract.py` | **新建** | 3.1 |
| `tests/test_graph.py` | **新建** | 3.2 |
| `tests/test_recommend.py` | **新建** | 3.3 |
| `tests/test_md_weekly.py` | **新建** | 3.4 |

---

## 五、测试策略

| 模块 | 测试重点 |
|------|---------|
| 概念提取 | prompt 格式、空文章返回"无"、已提取过返回缓存、重复概念去重 |
| 关联图 | 空数据页面不崩溃、概念-文章边数量正确、时间切换 |
| 推荐 | 无阅读记录时回退到热门推荐、兴趣/空白两路不重复、排除已读 |
| 周刊 | MD 模板渲染、推送 channel 调用、手动下载端点 |

目标: 182 → 200+ tests, 覆盖率 ≥ 82%

---

## 六、风险

| 风险 | 缓解 |
|------|------|
| 概念提取增加页面加载时间 | 异步触发，不阻塞阅读；缓存机制避免重复 |
| 关联图当数据量大时性能差 | 只查当天数据，节点数天然有限 |
| 推荐质量依赖概念提取质量 | 双引擎兜底：兴趣不行还有知识空白 |
| 周刊 MD 格式在企微/Telegram 兼容性 | 企微 markdown 类型，Telegram MarkdownV2 |
