# AI 资讯管家 v1.0 设计规格

**Date:** 2026-06-10
**Status:** Draft
**上一版本:** v0.8 (216 tests, 84% coverage)

---

## 一、范围

v1.0 定位：**正式发布**。知识图谱从展示层升级为数据层一等公民，配合 Bug Hunting 机制和 Codex 审阅交接完成最终交付。

### 包含

1. **知识图谱三层升级** — 档案永久化 → 结构化存储 → 生命周期追踪
2. **Bug Hunting 机制** — 四类专项子代理融入现有审计+测试阶段
3. **Codex 审阅交接** — 按 8 条规则完成可追溯性打包

### 不包含（推迟至 v1.1）

- `concept_edges` 结构化边表 → v1.1
- Weekly snapshot 独立保存 → v1.1
- 周报月度概念趋势板块 → v1.1  
- 概念实体解析（标签合并/去重） → v1.1

---

## 二、架构决策

### 2.1 写入方向：结构化表为唯一真相源

```
旧: scheduler → JSON 快照 (+ 结构化表并存)
新: scheduler → concept_nodes (唯一真相源) → JSON 快照从表中生成
```

**理由:** 三视角审查一致指出双写不一致是最严重风险。翻转写入方向彻底消除双真相源问题，JSON 快照降级为从结构化表派生的只读缓存。

### 2.2 三层递进关系

```
Layer A: 档案永久化 ──→ 移除 30 天 DELETE，快照永久保留
     │
     ▼
Layer B: 结构化存储 ──→ concept_nodes 表，替代 JSON 作为查询源
     │
     ▼
Layer C: 生命周期引擎 ──→ 状态追踪 + 概念轨迹页
```

B 依赖 A（需要历史数据支撑生命周期计算），C 依赖 B（需要结构化查询能力）。但 B 的实现不改变 A 的交付——A 独立可验收。

---

## 三、模块设计

### 3.1 Layer A — 档案级持久化

**改动点：**

1. `scheduler.py` `daily_job()`: 移除 30 天 DELETE 逻辑（约 6 行）
2. `scheduler.py` `daily_job()`: 快照保存逻辑不变，继续存 today 快照
3. 不新增 weekly 快照保存（推迟至 v1.1）

**影响:** `graph_snapshots` 表数据永久保留。对比模式可查看任意历史日期。

**不改:** schema、路由、模板。

### 3.2 Layer B — 结构化概念存储

**新表 `concept_nodes`：**

```sql
CREATE TABLE IF NOT EXISTS concept_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_label   TEXT NOT NULL,
    weight          REAL DEFAULT 0.0,
    article_count   INTEGER DEFAULT 0,
    first_seen_date TEXT NOT NULL,
    last_seen_date  TEXT NOT NULL,
    snap_date       TEXT NOT NULL,
    UNIQUE(concept_label, snap_date)
);
CREATE INDEX IF NOT EXISTS idx_concept_nodes_label ON concept_nodes(concept_label);
CREATE INDEX IF NOT EXISTS idx_concept_nodes_snap_date ON concept_nodes(snap_date);
```

**数据流：**

```
daily_job:
  1. 采集完成 → get_graph_data("today") 取 nodes + edges
  2. 写入 concept_nodes（UPSERT by concept_label + snap_date）
  3. 从 concept_nodes 生成 JSON → 写入 graph_snapshots（备份/兼容）
```

**查询切换：**

- `web/routes/graph.py`: `get_graph_data()` 改为从 `concept_nodes` 查询，不再只读 JSON
- `get_graph_snapshot()` JSON 路径保留，作为对比模式的 fallback

**剪枝策略：**

- `last_seen_date < date('now', '-90 days') AND weight < 1.0` → 软删除标记
- 软删除的概念不在 graph 页面展示，但保留原始数据
- 清理在 daily_job 末尾执行，与快照生成同事务

**迁移：**

- schema.py 新增 `concept_nodes` 建表语句
- 首次启动时从现有 `graph_snapshots` JSON 回填历史数据（一次性）

### 3.3 Layer C — 概念生命周期引擎

**生命周期状态机：**

```
new ──→ rising ──→ stable ──→ declining
  ↑                             │
  └───────── 回归 ──────────────┘
```

**状态迁移规则（含迟滞窗口）：**

| 迁移 | 条件 | 迟滞 |
|------|------|------|
| new → rising | 连续 3 天 article_count 增长 | 3 天窗口 |
| rising → stable | 连续 5 天 article_count 波动 < 20% | 5 天窗口 |
| stable → declining | 连续 7 天 article_count 递减 | 7 天窗口 |
| declining → rising | 连续 3 天 article_count 增长 | 3 天窗口（回归） |

**实现：**

- `ai/analysis.py` 新增 `compute_concept_lifecycle(conn, concept_label)` 
- 基于 `concept_nodes` 表中该概念的 `article_count` 历史序列判定状态
- 结果缓存至 `concept_nodes` 表新增 `lifecycle_state` 列

**概念轨迹页 `/concepts/<label>`：**

- 展示单个概念的演化：权重曲线（SVG 折线图）、当前状态、首次出现日期、关联文章列表
- 复用 `_build_nodes_and_edges` 的力导向图，以该概念为中心展示关联子图
- 模板：新增 `web/templates/concept_detail.html`

**不改:** 周报模板（月度趋势板块推迟至 v1.1）

---

## 四、Bug Hunting 机制

### 4.1 融入策略

四个 Hunter 作为 **B 阶段和 T 阶段的固定执行模块**，不另立 B2/D2 阶段号。

| 模块 | 执行时机 | 扫描范围 | 职责 |
|------|---------|---------|------|
| 边界猎人 | B（审计）, T（测试） | B: 全量 / T: 增量 | 空输入、超长输入、并发、超时、DB 锁 |
| 体验猎人 | B, T | B: 全量 / T: 增量 | UI 死链接、错误文案、加载态缺失、空态处理 |
| 安全猎人 | B, T | B: 全量 / T: 增量 | SQL 注入、XSS、密钥泄露、路径遍历 |
| 正确性猎人 | B, T | B: 全量 / T: 增量 | 逻辑矛盾、数据不一致、遗漏的错误处理 |

### 4.2 学习回路

每个 cycle 的猎杀报告末尾增加 **"建议强化规则"** 条目。若连续两个 cycle 的同一 hunter 发现同类问题，该建议自动升级为 PROJECT-OVERVIEW.md 铁律（R11+）。

### 4.3 空结果协议

若某 hunter 零发现，触发验证步骤：
1. 确认 hunter 确实运行了（检查输出日志）
2. 确认扫描了正确的文件集（检查 git diff 范围）
3. 验证通过 → 记录 "clean"，不视为异常

### 4.4 融入现有阶段

**阶段 B 扩展：**
```
B1: 架构+安全+质量+性能审计（现有）
B2: 四 Hunter 全量扫描（新增，作为 B 的子步骤）
B3: 修复 + 规则审计（现有）
```

**阶段 T 扩展：**
```
T1-T2: 全量测试 + 回归（现有）
T3: 边界猎人 增量扫描（替代原 T3 手工边界检查）
T4: 集成烟雾（现有）
T5: 性能检查（现有）
T6: 安全猎人 增量扫描（替代原 T6 手工安全扫描）
T7: 覆盖率（现有）
T8: 修复（现有，增加 hunter 发现的问题）
```

---

## 五、Codex 审阅交接

按 `codex-handover-requirements` 的 8 条规则执行，v1.0 开发过程中逐条验证：

1. 零 ad-hoc — 所有变更通过 spec→plan→task→commit 链路
2. Cycle Report 先于验收 — 数字可被 git log + pytest 验证
3. 测试只增不减 — 216 → 目标 230+
4. 安全归零 — T6 每次 PASS
5. Commit 消息规范 — type: description 格式
6. PROJECT-OVERVIEW 同步 — v1.0 完成后更新
7. Spec→Plan→Code 可追溯 — 每个 requirement 对应 task 对应 commit
8. 文档语言统一 — 中文 spec/plan/report，英文 commit

---

## 六、验收标准

- [ ] graph_snapshots 不再自动删除（30 天限制移除）
- [ ] concept_nodes 表存在且有数据
- [ ] graph 路由从 concept_nodes 查询（非 JSON）
- [ ] JSON 快照从 concept_nodes 派生（单一真相源）
- [ ] 概念生命周期状态正确判定（含迟滞窗口）
- [ ] `/concepts/<label>` 页面正常渲染
- [ ] 90 天低权重概念自动剪枝
- [ ] 四 Hunter 报告产生并归档
- [ ] 测试数 ≥ 230，覆盖率 ≥ 84%
- [ ] 8 条 Codex 规则逐条验证通过

---

## 七、风险与约束

| 风险 | 缓解 |
|------|------|
| concept_nodes 表膨胀 | 90 天剪枝 + article_count 阈值 |
| 历史 JSON 回填失败 | 回填作为独立 migration 步骤，失败不影响新数据写入 |
| 生命周期状态振荡 | 迟滞窗口（3/5/7 天连续满足才迁移） |
| Hunter 误报淹没真实问题 | 空结果协议 + 连续误报触发 hunter 规则重审 |
