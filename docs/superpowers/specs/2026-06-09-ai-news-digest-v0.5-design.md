# AI 资讯管家 v0.5 Design

**Date:** 2026-06-09
**Status:** Approved
**Theme:** 自动化 + 智能排序 + 源发现
**Reviews:** 2 轮 6 次专业视角审查（美学/系统/逻辑），11+5 项修复已纳入

## Scope — 8 Tasks

### Task 1: db/schema.py 扩展
- `read_records` 加 `topics` TEXT 字段（source 列为 'user'/'ai'），不新建 user_interests 表
- `source_candidates` 新表：url TEXT UNIQUE, verified BOOLEAN DEFAULT FALSE, discovered_at, confirmed_at, relevance_score
- Config 嵌套化：SchedulerConfig(cron, enabled), RankingConfig(interest_weight, freshness_decay, exploration_floor), DiscoveryConfig(max_candidates)
- 候选积压上限：source_candidates 最多保留 50 条未审核记录

### Task 2: orchestrator.py — 管道 7 阶段拆分
- 从 main.py 拆出独立可调用管道函数，scheduler 和 main.py 都导入
- 7 个阶段：collect_all → dedup_articles → rank_articles → cluster_articles → annotate_articles → discover_sources → push_to_channels
- 阶段 5 `annotate_articles` 仅做 cluster label + 探索标记，不做深层分析（深层分析保持按需 /api/analyze）
- 周报生成逻辑从 `web/routes/api.py` 抽取到 orchestrator：`generate_weekly_review(db, ai)`
- source_miner 对缺失 full_text 的文章优雅跳过（当前 full_text 仅按需填充）

### Task 3: push/ 重构 — PushChannel 抽象
- `push/base.py`：AsyncPushChannel 抽象基类，定义 `send_digest(digest)` 和 `send_review(review)` 方法
- `push/wecom.py`：WeComChannel(PushChannel)，从 push.py 迁移
- `push/telegram.py`：TelegramChannel(PushChannel)，从 push_telegram.py 迁移
- orchestrator 遍历通道列表发送，不再硬编码函数名
- 管道按序发送（非并行），避免多通道同时调用触发限流

### Task 4: scheduler.py — 定时调度引擎
- APScheduler + SQLiteJobStore（持久化 job 状态）
- 注册 Job：每日 9:00 采集+推送
- `run_on_startup`：启动时立即执行一次采集（解决"启动后无内容"问题）
- 周报触发：事件驱动——采集完成后触发，非固定 9:30（避免采集超时吃掉间隔）
- ai-news.bat 改为启动 Web 服务 + 后台调度器

### Task 5: pipeline/ranking.py — 双阶段智能排序
- **位置**：pipeline/ranking.py（非 ai/ 下，ranking 是统计算法不需要 LLM）
- **阶段 1 — 冷启动**：feedback < 15 时，时间降序 + 来源信誉权重 + 智能探索率
- **阶段 2 — 兴趣驱动**：feedback ≥ 15 后渐进混合，权重 = min(1, feedback/25)，在 15-25 区间平滑过渡（非硬切换，避免"冷启动悬崖"）
- **探索配额**：≥20% 来自用户未接触的概念，加绝对下限 min 2 篇（解决百分比陷阱：5篇/天时 20%=1 篇不够）
- **插入点**：dedup 之后、cluster 之前。Ranking 只打分不过滤——所有文章进 cluster，score 影响 digest 选取
- **隐性信号**：阅读时长、是否点开翻译、是否收藏，作为冷启动辅助信号

### Task 6: source_miner.py + ai/discovery.py — 新源自动发现
- `pipeline/source_miner.py`：从文章 full_text 提取域名/URL，去重已有源，生成候选列表。缺失 full_text 的跳过。
- `ai/discovery.py`：AI 评估候选源质量（内容领域匹配、更新频率预估、权威度），生成 relevance_score
- 候选进入 `source_candidates` 表（verified=False），需人工确认后进入 sources 表
- 候选源审核页：Web 面板 /sources/candidates，展示候选列表，一键确认/拒绝

### Task 7: Web 面板扩展
- 阅读页加 👍/👎 按钮，写入 read_records.feedback
- 首页文章列表显示优先级标记（ranking score 可视化）
- 源候选审核页：/sources/candidates，展示 source_candidates 列表
- API 端点：POST /api/feedback, GET /api/source-candidates, POST /api/source-candidates/{id}/verify, POST /api/source-candidates/{id}/reject

### Task 8: 防护机制（横向关注，覆盖所有 task）
- **SQLite 写重试**：WAL + busy_timeout=5000 + 最多 3 次写重试，装饰器 `@db_write_retry`
- **探索配额下限**：绝对 min 2 篇，与 20% 取较大值
- **LLM token 追踪**：ai/client.py 加每日 token 计数器，日志输出 "今日 AI 调用消耗 X tokens"
- **冷启动渐进过渡**：weight = min(1, feedback/25)，避免硬切换
- **source_candidates UNIQUE(url)**：防止重复发现同一源

## Architecture

```
orchestrator.py          ← 7 composable pipeline stages (唯一入口)
scheduler.py             ← imports orchestrator
main.py                  ← imports orchestrator + scheduler, wires them

pipeline/
  dedup.py               ← stage 2
  ranking.py             ← stage 3 (双阶段打分)
  cluster.py             ← stage 4
  extractor.py           ← full_text utility
  source_miner.py        ← stage 6a (URL提取+去重)

ai/
  client.py              ← LLM client + token tracking
  analysis.py            ← prompt builders
  review.py              ← week review prompts
  discovery.py           ← stage 6b (AI源质量评估)

push/
  base.py                ← PushChannel ABC
  wecom.py               ← WeComChannel
  telegram.py            ← TelegramChannel

db/
  schema.py              ← +read_records.topics, +source_candidates
  models.py              ← CRUD

web/routes/
  api.py                 ← feedback, source review, week review (→ orchestrator)
  sources.py             ← source candidate review page
```

## Pipeline Flow

```
① collect_all(db, sources) → articles
② dedup_articles(db, articles) → unique_articles
③ rank_articles(db, unique_articles) → scored_articles  [新: pipeline/ranking.py]
④ cluster_articles(db, scored_articles) → clusters
⑤ annotate_articles(db, ai, clusters) → annotated         [仅label+explore, 非深层]
⑥ discover_sources(db, ai, annotated) → candidates        [新: source_miner+discovery]
⑦ push_to_channels(db, channels, digest) → results        [重构: PushChannel迭代]
```

## Safeguards

| 防护 | 机制 | 对抗风险 |
|------|------|---------|
| 冷启动渐进 | weight=min(1,feedback/25)，15-25平滑过渡 | 冷启动悬崖 |
| 探索下限 | max(20%, 2篇) | 百分比陷阱 |
| 源验证门禁 | source_candidates.verified=False, UNIQUE(url), 50条上限 | LLM幻觉源 |
| SQLite写重试 | WAL + busy_timeout + @db_write_retry(3) | 三路并发写 |
| 周一事件驱动 | 采集完成后触发周报，非固定9:30 | 采集超时 |
| Token追踪 | ai/client.py 每日计数器+日志 | 成本盲飞 |
| 推送串行 | 按序迭代通道列表，非并行 | 多通道堆叠限流 |

## Key Decisions

- **ranking 在 pipeline/ 而非 ai/**：ranking 是统计算法（时间衰减+权重计算），不需要 LLM
- **ranking 只打分不过滤**：所有文章进 cluster，score 影响 digest 精选——避免小众话题被丢弃
- **annotate 非 analyze**：阶段 5 仅做 cluster label + 探索标记（轻量 LLM）。深层分析保持按需触发
- **read_records.topics 而非独立表**：从 feedback 聚合派生，source 列区分 'user'/'ai'，避免双表 truth 问题
- **事件驱动周报**：比固定 9:30 更稳健，采集多久等多久
- **探索配额选"概念差集"**：从 v0.4 的随机 15% 升级为定向选取用户未接触概念
