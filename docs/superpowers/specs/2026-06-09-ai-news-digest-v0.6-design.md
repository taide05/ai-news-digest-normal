# AI 资讯管家 v0.6 Design

**Date:** 2026-06-09
**Status:** Approved
**Theme:** 深度分析 — 从"知道发生了什么"到"理解这意味着什么"
**Reviews:** 1 轮 3 视角审查（美学/系统/逻辑），A 并入 B、C 推迟、D 轻量化

## Scope — 5-6 Tasks

### Task 1: analysis_cache schema 扩展 + API dispatch 重构

- 新增 `cross_analysis_cache` 表：`id, cluster_id TEXT, analysis_type TEXT, content TEXT, article_ids TEXT, model TEXT, tokens_used INTEGER, created_at TEXT, UNIQUE(cluster_id, analysis_type)`
- `web/routes/api.py` 的 `analyze` 端点 if/elif 链重构为 dispatch map：`_ANALYZERS = {"core_insight": ..., "what_it_means": ..., "counter_argument": ..., "cross_comparison": ...}`
- 向后兼容：现有 `analysis_cache` 表和 `get_cached_analysis`/`cache_analysis` 不改动

### Task 2: "这意味着什么" 5 维升级（含反方观点）

- 重写 `build_what_it_means_prompt` 为 5 维结构：
  1. **技术意义** — 对技术栈、工程实践的影响
  2. **商业影响** — 谁会受益/受损？市场格局变化？
  3. **行业趋势** — 孤立事件还是趋势信号？与已知事件的串联
  4. **反方观点** — 谁会反对？局限性在哪？批评者的合理担忧？（从独立模块 A 并入）
  5. **与你相关** — 关联用户 read_records.topics 和 concepts
- 函数签名扩展：`build_what_it_means_prompt(full_text, concepts, user_topics: list[str], read_titles: list[str])`
- SSE 流式输出分段标记：`data: {"section": "tech_significance", "chunk": "..."}`
- 调用方 `api.py` 在 analyze 端点组装 user_topics 和 read_titles 上下文

### Task 3: 横向对比分析（轻量版）

- 新建 `ai/analysis.py:build_cross_comparison_prompt(cluster_articles: list[dict])`
  - 输入：同 cluster 的文章列表（标题 + source_id + core_insight 缓存内容）
  - 输出：观点异同 / 事实一致性 / 信息来源可信度 / 推荐阅读顺序
- 新增 API 端点：`POST /api/cross-compare/{cluster_id}`
  - 检查 `cross_analysis_cache` 缓存
  - 同一 cluster 需 ≥3 篇文章才触发
  - 仅使用 core_insight（自动加载的缓存）+ 标题 + 来源，不依赖 what_it_means 预计算
- 新增 `db/models.py` 函数：`cache_cross_analysis()`, `get_cached_cross_analysis()`
- reader.html 底部新增：同 cluster 文章 ≥3 篇时显示"对比阅读"按钮

### Task 4: 阅读页 UI — 折叠式分析 + 信息过载控制

- 升级 `reader.html`：
  - "核心观点"：保持自动加载
  - "这意味着什么"：默认折叠，5 个维度标签页/accordion 切换
  - "对比阅读"：仅在 cluster ≥3 篇时显示按钮
  - SSE 连接数控制：最多 2 个并发（core_insight 自动 + 用户当前展开的分析），旧连接在用户切换时关闭
- 首页 `home.html` 文章列表加 cluster 文章数 badge：`[+2篇同类]`
- 所有分析区块延迟加载：用户点击才触发 SSE，不自动加载

### Task 5: 测试 + 集成验证

- `tests/test_analysis_v06.py`：5 维 prompt 格式验证、cross_comparison prompt 输入验证
- `tests/test_api_v06.py`：新端点 200/缓存命中/cluster 不足 3 篇拒绝
- `tests/test_web_v06.py`：UI 元素存在性（折叠/展开/对比按钮条件显示）
- 全量回归：166+ tests pass

## Architecture

```
ai/analysis.py          — +build_cross_comparison_prompt
                          — 重写 build_what_it_means_prompt (5-dimension)
                          — 删除 build_counter_argument_prompt（并入 B）

web/routes/api.py       — 重构 analyze 端点: if/elif → dispatch map
                          — 新增 POST /api/cross-compare/{cluster_id}
                          — analyze 端点组装 user_topics/read_titles 上下文

db/schema.py            — 新增 cross_analysis_cache 表
db/models.py            — 新增 cache_cross_analysis(), get_cached_cross_analysis()

web/templates/reader.html  — 5 维折叠式分析 + 对比阅读按钮
web/templates/home.html    — cluster 文章数 badge
```

## Key Decisions

- **A 并入 B**：反方观点从独立端点变为 B 的第 4 维。消除偶发复杂度，省 50% API 调用
- **C 推迟到 v0.7**：趋势追踪需要 >=2 周数据积累 + 属于"学习轨迹"而非"文章理解"
- **D 不依赖 B**：横向对比只吃 core_insight + 标题 + 来源，不等待 what_it_means 完成
- **默认折叠**：所有分析区块按需加载。日信息单元从 ~100 降到 ~40，回到认知预算内
- **SSE ≤2 并发**：用户切换分析区块时关闭旧 SSE 连接
- **D ≥3 篇触发**：同一 cluster 不足 3 篇文章时不显示对比按钮

## Deferred to v0.7

- **C: 学习趋势追踪** — /trends 页面，概念热度变化，个人学习轨迹
- 周报增强 — 趋势数据融入周报
- 知识图谱雏形 — 概念间关系可视化
