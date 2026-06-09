# AI 资讯管家 v0.8 设计规格

**Date:** 2026-06-09
**Status:** Draft
**上一版本:** v0.7 (198 tests, 83% coverage)

---

## 一、范围

v0.8 定位：**打磨收尾**。不新增页面，在 v0.7 基础上增强 3 个现有模块。为 v1.0 做最后的品质提升。

### 包含

1. **知识图谱历史对比** — `/graph` 页面支持查看历史快照 + 对比模式
2. **阅读推荐序列升级** — 基于近期阅读话题聚类优化推荐
3. **周报数据驱动** — 周报注入统计热词和概念增长数据

### 不包含

- 新页面/新路由
- 学习趋势追踪（独立趋势页）→ 由周报数据驱动替代
- 知识图谱持久化全局历史 → v1.0

---

## 二、依赖

```
graph_snapshot 表（新）
      │
      ▼
知识图谱历史对比
      
read_records 时间序列（已有）
      │
      ▼
阅读推荐序列升级（替换 engine B）

concepts.query_count 增量（已有）
      │
      ▼
周报数据驱动
```

三个模块互相独立，可并行开发。

---

## 三、模块设计

### 3.1 知识图谱历史对比

**目标:** `/graph` 页面支持查看历史快照和对比模式。

**新增表:**
```sql
CREATE TABLE IF NOT EXISTS graph_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snap_date   TEXT NOT NULL,
    period      TEXT NOT NULL,  -- 'today' or 'week'
    data_json   TEXT NOT NULL,  -- JSON: {nodes: [...], edges: [...]}
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(snap_date, period)
);
```

**快照生成:**
- 在 scheduler 的 daily_job 完成后，异步生成当日 snapshot
- 调用 `get_graph_data(db, "today")` 获取当前数据
- 序列化为 JSON 存入 `graph_snapshots`
- 保留最近 30 天快照

**前端改造:**
- 页面顶部改为 tab 切换：「今天 / 上周 / 对比」
- 对比模式：上下堆叠两张 SVG（当前 vs 选中日期）
- 首周无历史快照时，隐藏「对比」和「上周」tab
- 历史 SVG 使用与当前相同的力导向布局（随机种子不同，布局可不同）

**数据查询:**
```python
def get_graph_snapshot(conn, snap_date: str, period: str) -> dict | None:
    row = conn.execute(
        "SELECT data_json FROM graph_snapshots WHERE snap_date = ? AND period = ?",
        (snap_date, period)
    ).fetchone()
    return json.loads(row[0]) if row else None

def get_snapshot_dates(conn, limit: int = 7) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT snap_date FROM graph_snapshots ORDER BY snap_date DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [r[0] for r in rows]
```

**/graph 路由更新:**
- 新增 query param: `?period=today&compare=2026-06-02`
- 有 compare 参数时加载两张图的数据
- 无 compare 且无历史时，tab 只显示「今天」

---

### 3.2 阅读推荐序列升级

**目标:** 引擎 B 从"随机热门概念"升级为"近期阅读话题聚类推荐"。

**新算法（替换 `get_recommendations_gap`）:**
1. 从 `read_records` 取最近 7 天已读文章的 concept_id 列表
2. 按 concept 出现频率降序 → 用户近期关注的话题
3. 找到同样讨论这些高频概念、但用户尚未读过的文章
4. 按概念匹配数降序，取 top 2

**新函数:**
```python
def get_recommendations_cluster(conn, limit: int = 2) -> list[dict]:
    """Recommend articles based on recent reading topic clusters."""
    rows = conn.execute(
        "SELECT a.id, a.title, a.source_id, c.term, COUNT(*) as matches "
        "FROM articles a "
        "JOIN article_concepts ac ON a.id = ac.article_id "
        "JOIN concepts c ON ac.concept_id = c.id "
        "WHERE ac.concept_id IN ("
        "  SELECT ac2.concept_id FROM article_concepts ac2 "
        "  JOIN read_records rr ON ac2.article_id = rr.article_id "
        "  WHERE rr.opened_at >= date('now', '-7 days')"
        "  GROUP BY ac2.concept_id ORDER BY COUNT(*) DESC LIMIT 10"
        ") "
        "AND a.id NOT IN (SELECT article_id FROM read_records) "
        "GROUP BY a.id "
        "ORDER BY matches DESC, a.fetched_at DESC "
        "LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"id": r[0], "title": r[1], "source_id": r[2],
             "reason": f"近期关注「{r[3]}」"} for r in rows]
```

**API 更新:**
- `/api/recommend/{article_id}` 调用 `get_recommendations_cluster` 替代 `get_recommendations_gap`
- 引擎 A（`get_recommendations_interest`）不变
- 合并逻辑不变：A 取 2，B 取 2，去重上限 4

**降级策略:**
- 如果用户最近 7 天无阅读记录 → `get_recommendations_cluster` 返回空
- 此时引擎 A 独立提供推荐（取 top 4）
- 如果 A 也不足 2 篇 → 回退到全局热门文章（按 fetched_at 降序）

---

### 3.3 周报数据驱动

**目标:** 周报 MD 模板注入从数据库提取的统计数据。

**新增统计数据:**
1. **本周热词 TOP5** — 本周内被查询/关联最多的概念
2. **概念增长最快 TOP3** — 本周新增 + query_count 增量最大的概念

**数据查询:**
```python
def get_weekly_hot_concepts(conn, week_start: str) -> list[dict]:
    """Top concepts by query_count increase this week."""
    rows = conn.execute(
        "SELECT term, query_count FROM concepts "
        "WHERE last_seen >= ? "
        "ORDER BY query_count DESC LIMIT 5",
        (week_start,)
    ).fetchall()
    return [{"term": r[0], "count": r[1]} for r in rows]

def get_weekly_growing_concepts(conn, week_start: str) -> list[dict]:
    """Concepts with highest growth this week (newly created or most queried)."""
    rows = conn.execute(
        "SELECT term, query_count FROM concepts "
        "WHERE first_seen >= ? "
        "ORDER BY query_count DESC LIMIT 3",
        (week_start,)
    ).fetchall()
    return [{"term": r[0], "count": r[1]} for r in rows]
```

**MD 模板更新:**
```markdown
## 本周热词
transformer (15次), agent (12次), RLHF (8次), attention (7次), fine-tuning (6次)

## 新晋概念
tool-use (5次), MoE (3次), RAG (2次)

## 本周概览
{AI生成内容}

## 推荐阅读
{推荐列表}
```

**orchestrator 更新:**
- `generate_weekly_review` 调用上述两个查询
- 将结果渲染到 MD 模板的「本周热词」和「新晋概念」部分
- 保持现有「本周概览」和「推荐阅读」部分不变

---

## 四、文件变更清单

| 文件 | 操作 | 对应模块 |
|------|------|---------|
| `db/schema.py` | 新增 `graph_snapshots` 表 | 3.1 |
| `db/models.py` | 新增 `save_graph_snapshot`, `get_graph_snapshot`, `get_snapshot_dates`, `get_recommendations_cluster`, `get_weekly_hot_concepts`, `get_weekly_growing_concepts` | 3.1, 3.2, 3.3 |
| `web/routes/graph.py` | 支持 `?compare=` 参数，加载历史快照 | 3.1 |
| `web/templates/graph.html` | tab 切换（今天/上周/对比），对比模式双 SVG | 3.1 |
| `web/routes/api.py` | 推荐端点切换到 `get_recommendations_cluster`，加降级逻辑 | 3.2 |
| `orchestrator.py` | `generate_weekly_review` 注入统计数据 | 3.3 |
| `scheduler.py` | daily_job 完成后生成 graph snapshot | 3.1 |
| `tests/test_graph_v08.py` | **新建** | 3.1 |
| `tests/test_recommend_v08.py` | **新建** | 3.2 |
| `tests/test_weekly_v08.py` | **新建** | 3.3 |

---

## 五、测试策略

| 模块 | 测试重点 |
|------|---------|
| 图谱历史 | snapshot 写入/读取、空历史时不显示对比 tab、compare 参数加载两张图 |
| 推荐升级 | 聚类查询正确性、空阅读记录降级、引擎 A+B 合并不变 |
| 周报数据 | 热词查询、增长概念查询、MD 模板渲染含数据 |

目标: 198 → 210+ tests, 覆盖率 ≥ 83%

---

## 六、风险

| 风险 | 缓解 |
|------|------|
| 首周无快照，对比功能空窗 | 前端条件渲染，无历史时隐藏对比 tab |
| 用户无阅读记录时推荐降级 | 引擎 A 独立支撑 + 全局热门兜底 |
| concepts 数据不足（v0.7 刚上线） | 热词查询用 `last_seen` 过滤，无数据时显示"暂无数据" |
