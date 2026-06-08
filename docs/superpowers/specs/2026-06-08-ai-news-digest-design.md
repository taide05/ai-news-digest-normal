# AI 资讯管家 — 设计文档

日期: 2026-06-08
状态: 已批准（终审修正）
版本: v0.1

## 产品定义

一个本地运行的个人 AI 资讯工具。用户双击桌面快捷方式，系统从精选源采集最新 AI 资讯，去重聚类后推送到企业微信，用户通过本地 Web 面板阅读内容并获取 AI 深度解读。

核心价值：**不是资讯推送器，是 AI 学习导师** — 帮用户把表层信息转化为可理解的深度知识。

## v0.1 范围

**做什么：**
- 5 个硬编码信息源采集
- URL 去重 + TF-IDF 标题聚类
- 企微每日推送（话题摘要）
- 本地 Web 面板：首页（今日聚类列表）+ 阅读页（全文 + "这意味着什么"）
- 文章内手动查概念（记录到词典）
- 手动触发周报
- 全文搜索已读文章

**不做什么（defer 到后续版本）：**
- 新源自动发现
- 源管理 Web UI（配置文件硬编码）
- 书签 / 笔记
- "反方怎么说"、"与你关注的关系"、"接下来该看什么"分析面板
- 兴趣建模 + 智能探索率
- 概念自动提取

## 用户交互路径

```
双击桌面快捷方式（.bat）
  │
  ├── 1. 启动本地服务器（若未运行）
  ├── 2. 采集 5 源 → 去重 → TF-IDF 聚类
  ├── 3. 推送到企微 → 自动打开浏览器到首页
  │
  ▼
Web 面板（浏览器 localhost:8765）
  │
  ├── 首页：今日聚类列表 + 上周报入口
  │   ├── 每个聚类：AI 生成的标签 + 文章数
  │   ├── 每条文章：标题 + 来源 + 语言标记
  │   └── [生成周报] 按钮
  │
  ├── 阅读页 /reader/{id}
  │   ├── 文章全文（惰性抓取 + 缓存）
  │   ├── 💡 核心观点（打开页面时自动生成）
  │   ├── ▶ 这意味着什么？（用户点击后 SSE 流式输出）
  │   ├── 文中选中文字 → "查这个概念"
  │   ├── 反馈按钮：👍 感兴趣 / 👎 不感兴趣
  │   └── 🌐 打开原网页
  │
  ├── 搜索 /search — FTS5 全文搜索
  ├── 概念词典 /concepts — 用户查过的概念列表
  └── 周报 /review — 查看/生成周报
```

## 关键设计原则

- **AI 按需调用**：全文提取和 AI 分析仅对用户点开的内容进行
- **惰性全文抓取**：采集时只拿标题+摘要+URL；全文仅当用户点开阅读页时抓取并缓存
- **分析缓存**：同一篇文章同类分析不重复调 API
- **探索多样性**：每天随机选 ~15% 文章来自当日非热点聚类，避免信息茧房

## 技术栈

| 层 | 选择 | 理由 |
|---|------|------|
| 语言 | Python 3.12+ | 数据处理 + LLM 调用生态 |
| Web 后端 | FastAPI + Uvicorn | 轻量、支持 SSE 流式 |
| Web 前端 | Jinja2 + HTMX + hx-sse | 无构建、离线可用 |
| 数据库 | SQLite + FTS5 | 零配置、全文搜索 |
| LLM | DeepSeek API | 国内直连、中文好、便宜 |
| 推送 | 企业微信 Webhook | 注册即用 |

**硬约束：**
- 服务器**只绑定 127.0.0.1**，不对局域网开放
- 所有静态资源本地存放，无需 CDN
- 不依赖 Node.js / npm

## 数据模型

### 表结构

```sql
-- 信息源（首次运行时自动初始化）
CREATE TABLE sources (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,             -- 'rss' | 'api'
    config      TEXT NOT NULL,             -- JSON: {url, endpoint, ...}
    enabled     INTEGER DEFAULT 1,
    fail_count  INTEGER DEFAULT 0,
    last_fetch  TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 文章（使用显式 INTEGER PK 以保证 FTS5 外部内容表稳定）
CREATE TABLE articles (
    _rowid_     INTEGER PRIMARY KEY AUTOINCREMENT,  -- FTS5 content_rowid 锚定
    id          TEXT UNIQUE NOT NULL,       -- SHA256(source_id || ':' || normalized_url)
    source_id   TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT,
    content     TEXT,                      -- RSS/API 自带的全文（原始）
    full_text   TEXT,                      -- 惰性提取的正文（readability）
    author      TEXT,
    published_at TEXT,
    fetched_at  TEXT DEFAULT (datetime('now')),
    language    TEXT,                      -- 'zh' | 'en'
    UNIQUE(source_id, url)
);

-- 文章聚类（每日，简单结构）
CREATE TABLE clusters (
    id          TEXT PRIMARY KEY,          -- SHA256(date || ':' || cluster_seq)
    label       TEXT,                      -- AI 生成的简短标签
    digest_date TEXT NOT NULL,             -- '2026-06-08' — 聚类所属日期
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE cluster_articles (
    cluster_id  TEXT REFERENCES clusters(id) ON DELETE CASCADE,
    article_id  TEXT REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, article_id)
);

-- 每日推送记录
CREATE TABLE daily_digests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,
    webhook_sent INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE digest_articles (
    digest_id   INTEGER REFERENCES daily_digests(id) ON DELETE CASCADE,
    article_id  TEXT REFERENCES articles(id) ON DELETE CASCADE,
    PRIMARY KEY (digest_id, article_id)
);

-- 用户阅读记录
CREATE TABLE read_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    opened_at   TEXT DEFAULT (datetime('now')),
    feedback    TEXT                       -- 'interested' | 'not_interested' | null
);

-- 概念词典（用户手动查词时记录）
CREATE TABLE concepts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    term        TEXT NOT NULL UNIQUE,
    definition  TEXT,                      -- AI 生成的简短定义
    query_count INTEGER DEFAULT 1,
    first_seen  TEXT DEFAULT (datetime('now')),
    last_seen   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE article_concepts (
    article_id  TEXT REFERENCES articles(id) ON DELETE CASCADE,
    concept_id  INTEGER REFERENCES concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, concept_id)
);

-- AI 分析缓存
CREATE TABLE analysis_cache (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id    TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL,           -- 'core_insight' | 'what_it_means' | 'translation'
    content       TEXT NOT NULL,
    model         TEXT DEFAULT 'deepseek-chat',
    tokens_used   INTEGER,
    created_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(article_id, analysis_type)
);

-- 周报记录
CREATE TABLE weekly_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start  TEXT NOT NULL,             -- '2026-06-01' 周一日期
    week_end    TEXT NOT NULL,             -- '2026-06-07' 周日日期
    content     TEXT NOT NULL,
    article_ids TEXT NOT NULL,             -- JSON 数组
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(week_start)
);
```

### 索引

```sql
CREATE INDEX idx_articles_source ON articles(source_id);
CREATE INDEX idx_articles_published ON articles(published_at);
CREATE INDEX idx_articles_url ON articles(url);
CREATE INDEX idx_reads_article ON read_records(article_id);
CREATE INDEX idx_concepts_term ON concepts(term);
CREATE INDEX idx_analysis_article ON analysis_cache(article_id);
CREATE INDEX idx_cluster_articles_article ON cluster_articles(article_id);
CREATE INDEX idx_digest_articles_article ON digest_articles(article_id);
CREATE INDEX idx_clusters_date ON clusters(digest_date);

-- FTS5 全文搜索（VACUUM 后 rowid 可能变化，锚定 _rowid_ 列）
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title, full_text, content='articles', content_rowid='_rowid_'
);
```

### FTS5 同步触发器

articles 表需要 INSERT/UPDATE/DELETE 触发器自动同步 FTS5 索引。UPDATE 触发器检测 `full_text` 变化：写入或更新时同步内容，被保留策略清空（设为 NULL）时从 FTS5 移除对应行，避免搜到空正文。

## 模块结构

```
ai-news-digest/
├── main.py              # 入口：一键执行的触发点
├── config.py            # 配置加载（.env + config.yaml）
├── push.py              # 企微 Webhook 推送
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── collectors/
│   ├── __init__.py
│   ├── base.py          # 采集器基类
│   ├── registry.py      # 采集器注册表
│   ├── arxiv.py
│   ├── hackernews.py
│   ├── rss_reader.py    # 通用 RSS（机器之心等）
│   ├── github_trending.py
│   └── reddit_ml.py
│
├── pipeline/
│   ├── __init__.py
│   ├── dedup.py         # URL + 标题去重
│   ├── cluster.py       # TF-IDF 向量聚类
│   └── extractor.py     # 全文惰性提取
│
├── ai/
│   ├── __init__.py
│   ├── client.py        # DeepSeek API 封装（重试 + 熔断）
│   ├── analysis.py      # "核心观点" + "这意味着什么" prompt
│   └── review.py        # 周报生成 prompt
│
├── web/
│   ├── __init__.py
│   ├── app.py           # FastAPI 应用
│   ├── routes/
│   │   ├── home.py
│   │   ├── reader.py
│   │   ├── search.py
│   │   ├── concepts.py
│   │   └── review.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── reader.html
│   │   ├── search.html
│   │   ├── concepts.html
│   │   └── review.html
│   └── static/
│       ├── htmx.min.js
│       ├── htmx-sse.js      # HTMX SSE 扩展
│       └── style.css
│
├── db/
│   ├── __init__.py
│   ├── schema.py        # DDL + 初始数据 seed
│   └── models.py        # 数据访问函数
│
└── tests/
    ├── conftest.py
    ├── test_dedup.py
    ├── test_cluster.py
    ├── test_db.py
    ├── test_prompts.py
    ├── test_collectors.py
    └── test_integration.py
```

### 依赖规则

```
collectors → db
pipeline   → db, ai
ai         → db
push       → db
web        → db, ai
main       → config, collectors, pipeline, push, web
config     → 无依赖
```

## 采集层设计

### 采集器接口

```python
@dataclass
class Article:
    source_id: str
    url: str
    title: str
    summary: str          # RSS/API 自带的简介
    author: str | None
    published_at: str | None
    language: str         # 'zh' | 'en'
    content: str | None   # RSS/API 自带的全文，可能为空

class BaseCollector(ABC):
    name: str
    type: str             # 'rss' | 'api'
    rate_limit: float     # 请求间隔（秒）

    @abstractmethod
    async def fetch(self, since: datetime) -> list[Article]:
        """拉取自 since 以来的新文章"""
```

### 采集流程

```
1. main.py 读取 sources 表获取启用源
2. asyncio.gather 并行拉取（各自 15s 超时）
3. 单个源失败不影响其他源
4. 汇总 → URL 标准化（去追踪参数）→ SHA256(source_id || ':' || url) 生成 ID
5. INSERT OR IGNORE 写入 articles 表
6. 返回新文章列表
```

### 初版 5 源

| ID | 源 | 类型 | 方式 | 语言 |
|----|-----|------|------|------|
| arxiv-cs-ai | arXiv cs.AI/cs.CL/cs.LG | API | 官方 API | en |
| hackernews | Hacker News (AI 关键字过滤) | API | 官方 API | en |
| jiqizhixin | 机器之心 | RSS | feedparser | zh |
| github-trending | GitHub Trending | web | 爬取 trending 页面 / RSSHub | en |
| reddit-ml | Reddit r/MachineLearning | RSS | feedparser (`.rss` 后缀) | en |

### 健壮性

- 每个源独立 try/except，失败不阻塞其他源
- 3 次重试 + 指数退避（1s, 2s, 4s）
- 10 秒单个源超时
- 同一源连续失败 7 天 → 首页显示该源状态标红
- HTTP 请求统一 User-Agent
- 响应编码自动检测（chardet）

## 加工流水线

### 去重 (pipeline/dedup.py)

```
1. URL 标准化：去除 query string 追踪参数（utm_*, ref=, source=等）
2. articles 表 (source_id, url) UNIQUE 约束自动拒绝重复
3. 标题相似度 > 0.85 的也视为重复（Jaccard 或 cosine on char n-grams）
```

### 聚类 (pipeline/cluster.py)

仅用 TF-IDF，不做 LLM 精修：

```
1. 将当天新文章 + 标题+摘要拼接为文档
2. TF-IDF 向量化（scikit-learn TfidfVectorizer）
3. 余弦相似度矩阵
4. 单链接聚类（阈值 0.6）
5. 为每个聚类生成标签：取聚类内 TF-IDF 最高频的 3-5 个词作为临时标签
6. LLM 仅为聚类打标签（批量请求，~200 tokens 出所有标签）
```

### 全文提取 (pipeline/extractor.py)

触发：用户第一次访问 /reader/{id} 时

```
1. 检查 articles.full_text 是否已填充 → 已填充直接返回
2. articles.content 非空 → 取 content
3. 否则 HTTP GET 原文 URL
4. readability-lxml 提取正文
5. 写入 articles.full_text（持久缓存）
6. 失败处理：
   - HTTP 404/403 → full_text = "[原文无法访问]"
   - 超时（15s） → full_text = "[原文加载超时]"
   - 提取内容 < 200 字 → full_text = "[正文提取失败，请查看原网页]"
```

### 探索多样性

不追踪用户兴趣。简单实现：每天聚类后，从包含 ≤2 篇文章的小聚类中随机选取 ~15% 的文章，标记为「探索」。首页单篇展示时带 `[探索]` 标签。

## AI 分析设计

### DeepSeek API 封装 (ai/client.py)

- 使用 openai 兼容 SDK，base_url 指向 DeepSeek
- 3 次重试（tenacity，指数退避 1s/2s/4s）
- 连续 5 次失败 → 熔断（10 分钟期内拒绝新请求）
- 熔断期间返回缓存结果或友好错误信息
- 每次调用记录 tokens_used

### v0.1 分析类型

| 分析类型 | 触发时机 | 输入 | 预估 token |
|---------|---------|------|-----------|
| 核心观点 | 打开阅读页时自动 | 全文 | ~500 |
| 这意味着什么 | 用户点击按钮 | 全文 + 概念词典 | ~800 |
| 全文翻译 | 用户点击「翻译全文」 | 全文（仅英文文章） | ~1000 |

### "全文翻译" prompt

```
将以下英文文章翻译为中文。保留技术术语的准确性，保持原文结构和风格。
文章：[全文]
```

### "核心观点" prompt

```
用 2-3 句话概括下面这篇文章的核心内容。直接说重点，不要铺垫。

文章：[全文]
```

### "这意味着什么" prompt

```
你是一位 AI 领域的资深分析师。用户正在学习 AI，读了一篇文章后想理解它到底意味着什么。

用户已了解的概念：[概念词典中的term列表]

文章内容：
[全文]

请从以下维度分析：
1. 这件事在 AI 领域有多重要？（噪音 ←→ 里程碑）
2. 可信度如何？（有数据支撑还是 PR 宣传？）
3. 为什么会发生？（技术/商业/政策驱动力）
4. 长期看意味着什么？（半年后回头看）

用通俗中文回答，避免术语堆砌。若原文为英文，用中文输出分析。
```

### 周报生成 (ai/review.py)

- 触发：用户在首页或 /review 页点击"生成周报"
- "周"的定义：自然周（周一至周日），若用户在周中触发则覆盖到前一天
- 输入：本周已读文章（标题+核心观点）、新增概念、👍/👎 分布
- 缓存到 weekly_reviews 表，同一周不重复生成

### 概念查询

- 触发：用户在阅读页选中文字 → 右键/按钮 → "查这个概念"
- 发送选中文字到 DeepSeek → 生成简短定义（~100 tokens）
- 写入 concepts 表（已存在则 query_count +1）
- 返回定义弹窗展示

## Web 面板设计

### 技术方案

- FastAPI + Jinja2（SSR）
- HTMX 处理页面切换
- hx-sse 扩展处理流式 AI 输出
- 两个 JS 文件本地存放（共 ~20KB）
- 最小宽度 1024px

### 路由

```
/                    首页
/reader/{id}         阅读页
/search              搜索
/concepts            概念词典
/review              周报
/api/analyze/{id}    GET SSE: "这意味着什么"分析
/api/translate/{id}  GET SSE: 全文翻译（英文→中文）
/api/concept-lookup  POST: 查概念
/api/feedback/{id}   POST: 提交 👍/👎
/api/generate-review POST: 生成周报
/api/collect         POST: 触发采集流水线（内部调用）
/api/health          GET: 健康检查
```

### 首页

```
┌─────────────────────────────────────────┐
│  AI 资讯管家          2026年6月8日        │
│                                          │
│  今日采集 47 篇，去重后 18 篇，分为 6 个话题   │
│                                          │
│  ● OpenAI & GPT-5         [3 篇相关]      │
│    OpenAI 发布 GPT-5 正式版，推理能力...    │
│    ├ 机器之心 · 4h前           [EN]       │
│    ├ OpenAI Blog · 5h前       [EN]       │
│    └ HN 讨论 · 3h前           [EN]       │
│                                          │
│  ● MoE 效率突破            [2 篇相关]      │
│    ...                                   │
│                                          │
│  ● [探索] 量子+ML 新方向     [1 篇]        │
│    ...                                   │
│                                          │
│  ─────────────────────────────────────  │
│  [🔍 搜索]  [📖 概念词典]  [📊 周报]      │
└─────────────────────────────────────────┘
```

### 空状态（首次运行前）

```
┌─────────────────────────────────────────┐
│  AI 资讯管家                             │
│                                          │
│  👋 欢迎！                                │
│                                          │
│  还没有资讯数据。                          │
│  请双击桌面上的「AI资讯」快捷方式来         │
│  采集第一期资讯。                          │
│                                          │
│  或在这里配置：                            │
│  [设置 DeepSeek API Key]                 │
│  [设置企微 Webhook URL]                  │
└─────────────────────────────────────────┘
```

### 阅读页

```
┌─────────────────────────────────────────┐
│  ← 返回首页           [👍 感兴趣] [👎 不感兴趣] │
│                                          │
│  OpenAI 发布 GPT-5 正式版                 │
│  来源：OpenAI Blog · 2026-06-08 · EN     │
│  作者：Sam Altman                         │
│  ─────────────────────────────────────  │
│  [全文...]                               │
│  ─────────────────────────────────────  │
│                                          │
│  [🌐 打开原网页]  [🌐 翻译全文]             │
│  选中文字 → [查这个概念]                    │
│                                          │
│  💡 核心观点                              │
│  GPT-5 在推理基准上首次...                 │
│                                          │
│  [▶ 这意味着什么？]                        │
└─────────────────────────────────────────┘
```

### AI 分析加载状态

```
点击"这意味着什么？"或"翻译全文"
  │
  ├── 立即显示骨架屏（灰色脉冲条）
  ├── 发送 GET /api/analyze/{id}?type=what_it_means  (SSE)
  │   或 GET /api/translate/{id} (SSE)
  ├── 服务器检查 analysis_cache → 有缓存直接返回
  ├── 无缓存 → 检查 ai/client 熔断状态
  │   ├── 熔断中 → 返回 "AI 服务暂时不可用，请稍后再试"
  │   └── 正常 → 调用 DeepSeek，SSE 流式回传
  │       ├── 每收到一段 → 前端追加渲染
  │       └── 全部完成 → 写入 analysis_cache（以 analysis_type='what_it_means' 或 'translation'）
  └── 失败（重试耗尽）→ "分析生成失败，请稍后重试"
```

### 搜索

- SQLite FTS5，搜索范围：articles.title + articles.full_text
- 服务端查询，返回摘要片段（用 `snippet()` 函数高亮匹配词）
- 按相关度排序，支持日期过滤

### 概念词典

- 列表页：按 query_count 降序，显示 term + definition + 查了多少次
- 点击 term 进入搜索该词出现过的所有文章

## 推送设计

### 企业微信通知格式

```markdown
🤖 AI 资讯已就绪 | 2026-06-08

今日采集 47 篇，精选 18 篇，6 个话题：

📌 OpenAI 发布 GPT-5 正式版 (3篇)
📌 MoE 训练效率新突破 (2篇)
...

💻 打开电脑上的 Web 面板查看详情
```

- 单次推送 ≤3KB（企微限制）
- 只推话题标签，不推链接
- 企微是提醒入口，不是阅读入口
- 同一天不重复推送（daily_digests.webhook_sent 检查）

## 首次运行

### 启动顺序

```
用户双击 ai-news.bat
  │
  ├── 1. 激活虚拟环境
  ├── 2. 检查 .env 文件存在 → 不存在则弹窗提示，服务器仍启动
  ├── 3. python main.py（异步执行以下步骤）
  │     ├── db/schema.py: CREATE TABLE IF NOT EXISTS（建表）
  │     ├── 检查 sources 表是否为空 → 空则 INSERT 5 条默认源
  │     ├── asyncio.create_task 启动 FastAPI (127.0.0.1:8765)
  │     ├── 执行采集→去重→聚类→推送流水线（与服务器并行）
  │     ├── 流水线完成后，写入临时文件标记"今日数据就绪"
  │     └── webbrowser.open("http://127.0.0.1:8765")
  └── 4. 保持运行（uvicorn serve 在后台线程）
```

关键实现细节：
- `uvicorn.Server` 在独立线程启动，不阻塞主流程
- 采集在服务器启动后执行，新数据写入后 Web 面板即时可见
- 浏览器在采集完成后打开，此时首页已有新鲜数据

### .env 缺失时的行为

- `python main.py` 启动时检测 .env 缺失
- FastAPI 正常启动（显示空状态页）
- 首页提示用户配置 API Key
- 采集和 AI 分析不会运行
- 控制台打印：`[WARN] .env 未找到，请复制 .env.example 为 .env 并填入 API Key`

### 服务器已运行时再次双击

- 请求 `http://127.0.0.1:8765/health` 检查
- 返回预期响应（含 `x-server: ai-news-digest` 头）→ 自己的服务器在运行
  - 直接 `webbrowser.open("http://127.0.0.1:8765")`
  - 通过 `/api/collect` 端点触发一次采集流水线
- 响应不匹配或连接拒绝 → 端口被其他程序占用或服务器未启动
  - 不启动新进程，提示用户检查

### 端口被占用（启动时）

- 启动时检测 8765 被占用
- 请求 `/health` 检查是否是自己 → 是则复用，不是则尝试 8766
- 最多尝试 3 个端口，全占用则报错退出

## Windows 快捷方式

### ai-news.bat

```batch
@echo off
cd /d D:\Projects\ai-news-digest
call .venv\Scripts\activate.bat
python main.py
```

### 桌面快捷方式创建

首次部署时手动执行 `setup.bat`，创建桌面快捷方式指向 `ai-news.bat`。

## 数据维护

### 自动清理策略

每次执行采集时进行清理：

| 表 | 保留策略 |
|---|---------|
| articles.full_text | 保留 90 天，超期后置 NULL（保留标题+摘要+分析缓存） |
| analysis_cache | 保留 180 天，超期后删除 |
| read_records | 保留 365 天 |
| daily_digests | 永久保留（只有日期+文章关联，数据量极小） |

### 数据库维护

- 启动时执行 `PRAGMA journal_mode=WAL`（避免多进程访问时的 SQLITE_BUSY）
- 每周执行一次 `PRAGMA optimize`
- 数据清理完成后执行 `VACUUM`（仅在文件缩小 >10% 时）

## 安全

| 措施 | 说明 |
|------|------|
| HTML 转义 | 所有外部内容 Jinja2 默认 `{{ }}` 转义 |
| 服务器绑定 | 强制 `host="127.0.0.1"`，启动时 `assert host == "127.0.0.1"` |
| 密钥管理 | `.env` + `.gitignore`，`.env.example` 模板 |
| 外部链接 | `rel="noopener noreferrer"` |
| SQL 注入 | 全部参数化查询 |

## 进程内流水线触发

### /api/collect（内部端点）

当用户在服务器已运行时再次双击快捷方式，主进程向已有服务器发送 POST `/api/collect`，触发一次采集流水线。流水线异步执行，返回 `{"status": "started"}`。前端通过轮询 `/api/collect/status` 或 SSE 获知完成。

### /api/health

```json
{"status": "ok", "server": "ai-news-digest"}
```

响应头含 `x-server: ai-news-digest`，用于区分自己的服务器和其他程序。

## 配置方案

### config.yaml

```yaml
pipeline:
  exploration_rate: 0.15      # 探索内容占比
  cluster_threshold: 0.6      # 聚类相似度阈值
  max_daily_articles: 20      # 每日推送上限

web:
  host: "127.0.0.1"
  port: 8765

data:
  full_text_retention_days: 90
  analysis_cache_retention_days: 180
```

### .env（不提交 git）

```
DEEPSEEK_API_KEY=sk-xxxxxxxx
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxx
```

## 错误处理汇总

| 场景 | 行为 |
|------|------|
| 采集源超时/失败 | 该源跳过，首页显示该源状态 |
| 全文提取失败 | 显示"[原文无法访问]"占位文字，提供"打开原网页"按钮 |
| DeepSeek 单次失败 | 自动重试 3 次 |
| DeepSeek 连续 5 次失败 | 熔断 10 分钟，返回"AI 服务暂时不可用" |
| 熔断期间请求分析 | 检查 analysis_cache → 有就返回旧的，没有就返回提示 |
| .env 缺失 | 服务器正常启动，显示配置引导页 |
| 端口被占用 | 自动尝试 +1 端口 |
| 当日已推送 | daily_digests 检查 → 跳过推送，只更新 Web 面板数据 |
| 当日运行两次 | 第二次不走推送，但重新采集（新文章追加到已有聚类或新建聚类） |
| 数据库损坏 | 启动时执行 `PRAGMA integrity_check`，失败则提示用户重建 |

## 依赖

```
fastapi
uvicorn[standard]
jinja2
feedparser
httpx
readability-lxml
chardet
scikit-learn
openai
python-dotenv
pyyaml
tenacity
```

## 测试策略

### 自动化

- Pipeline 逻辑（去重、聚类） — pytest + 固定数据
- DB 操作 — pytest + 内存 SQLite
- Prompt 模板格式 — pytest（不调 API）
- 采集器错误处理 — pytest + httpx mock

### 不测

- RSS 解析（feedparser）
- 前端渲染
- 企微实际发送
- AI 输出质量（人肉验证）

### 手动验收

1. 首次运行：空 DB → 运行 → 首页有数据
2. 企微推送：运行后收到通知
3. 缺 API Key：.env 不存在 → 显示引导页
4. 重复运行：两次 → 不重复推送
5. 数据持久化：重启 → 数据在

## 后续迭代（v0.2+）

- 新源自动发现
- 源管理 Web UI
- 书签 + 笔记
- "反方怎么说"、"与你关注的关系"、"接下来该看什么"
- 智能兴趣建模 + 个性化探索率
- 概念自动提取
- 导出 Markdown 学习笔记
- 切换到 Claude API（用户配好代理后）
