# A-F Cycle Report #8 — v0.8 → v1.0

**Date:** 2026-06-10
**Cycle:** 阶段 A (v0.8验收) → C (v1.0规划) → D (v1.0开发) → T (系统测试) → E (v1.0验收) → F (文档归档)
**Status:** ✅ Complete

---

## 阶段 A: v0.8 验收

- [x] 216/216 tests pass
- [x] 覆盖率 84%
- [x] Git 状态干净
- [x] 应用启动验证：84 篇文章成功采集，首页正常渲染，微信推送成功

**验收结论：v0.8 功能完整，进入 v1.0 规划。**

---

## 阶段 C: v1.0 规划

**设计流程:** brainstorming → 三视角审查（aesthetic/systems/logic） → 设计修正 → 用户确认

**三视角审查关键发现（6 项修正）：**

| # | 发现 | 来源 | 修正 |
|---|------|------|------|
| 1 | 双写不一致 — JSON + 结构化表并存无单一真相源 | 全部三个视角 | 翻转写入方向：结构化表为唯一真相源，JSON 从表中派生 |
| 2 | 生命周期状态机无量化定义 | 逻辑、系统 | 加入迟滞窗口（3/5/7天）和 20% 波动阈值 |
| 3 | concept_edges 和 monthly trend section 未赚回复杂度 | 审美 | 推迟至 v1.1 |
| 4 | Bug Hunting 与现有 B+T 阶段职责重叠 | 审美 | 融入 B+T 而非另立 B2/D2 |
| 5 | 概念表无剪枝策略 | 系统 | 加 90 天低权重剪枝 |
| 6 | Bug Hunting 缺少学习回路 | 系统 | 每个 cycle 出"建议强化规则"，连续两次自动升级为铁律 |

**v1.0 范围（8 tasks）：**

1. Layer A: 档案永久化 — 移除 30 天 DELETE
2. Layer B: Schema + concept_nodes 模型 — 新表 + CRUD + 回填 + 剪枝
3. Layer B: Scheduler 写入翻转 — concept_nodes 为唯一真相源
4. Layer B: Graph 路由查询切换 — concept_nodes 替代 live JOIN
5. Layer C: 生命周期状态机 — hysteresis + 3/5/7 day windows
6. Layer C: 概念轨迹页 — /concepts/<label> + SVG 趋势图
7. Bug Hunting + Codex 交接文档
8. 集成验证

**推迟至 v1.1：** concept_edges, weekly snapshot, 月度趋势板块, 概念实体解析

---

## 阶段 D: v1.0 开发

**Subagent-Driven Development:**

| Task | Commit | 结果 |
|------|--------|------|
| Task 1: Layer A | 9ece1d2 | 8 行删除，永久保留 |
| Task 2: Schema+Models | 4f0ae9f + cf1cc41 | concept_nodes 表 + 6 functions + 6 tests |
| Task 3: Scheduler 翻转 | 5d34102 | _save_graph_snapshot 抽取，startup 也写 concept_nodes |
| Task 4: Graph 路由切换 | 85afa7d | 4-table JOIN，fallback 路径 |
| Task 5: 生命周期引擎 | ea5ffa9 + e0008b0 | ai/lifecycle.py + 8 tests |
| Task 6: 概念轨迹页 | b9f45cb | template + route + CSS + 3 tests |
| Task 7: Bug Hunting 文档 | 1ba262d | PROJECT-OVERVIEW 全面更新 + Codex 验证 |

**代码审查发现（跨 task）：**
- Task 2: 冗余 import json + 测试断言 or→and 修复
- Task 3: article nodes 从 JSON 中移除（预期行为，Task 4 切换查询路径）
- Task 5: 未使用 deque import 移除
- 每个 task 均通过 spec compliance + code quality 双阶段审查

**关键指标：**
- 测试: 216 → 233 (+17, +8%)
- Commits: 8 (5 feat + 2 fix + 1 docs)
- 新增文件: ai/lifecycle.py, concept_detail.html, 3 test files
- 新增函数: 12 (save_concept_nodes, get_concept_nodes_by_date, get_concept_node_history, get_distinct_concept_labels, backfill_concept_nodes_from_snapshots, prune_stale_concepts, get_graph_data_from_nodes, compute_lifecycle_state, update_all_lifecycle_states, _consecutive_increasing, _consecutive_decreasing, _low_fluctuation)

---

## 阶段 T: v1.0 系统测试

| # | 检查项 | 结果 |
|---|--------|------|
| T1 | 全量测试 | 233/233 PASS |
| T2 | 回归检查 | 216→233 (+17, +8%) |
| T3 | 边界条件 | lifecycle 空历史/单位数/零值覆盖 |
| T4 | 集成烟雾 | 概念轨迹页路由正常，graph fallback 正常 |
| T5 | 性能 | concept_nodes 90天剪枝，LIMIT 100 查询 |
| T6 | 安全回归 | 全参数化 SQL 查询，get_graph_data_from_nodes 参数化 |
| T7 | 覆盖率 | 82%（新代码路径测试覆盖待补） |
| T8 | 问题修复 | 2 fix commits |

**门禁结果: 233/233 通过，进入阶段 E。**

---

## 阶段 E: v1.0 验收

- [x] 233/233 tests pass
- [x] graph_snapshots 无 30 天自动删除
- [x] concept_nodes 表存在且被 scheduler 写入
- [x] graph 路由从 concept_nodes 查询（含 fallback）
- [x] JSON 快照从 concept_nodes 派生（单一真相源）
- [x] 概念生命周期状态机含迟滞窗口（3/5/7天）
- [x] `/concepts/<label>` 页面正常渲染
- [x] 90 天低权重概念自动剪枝
- [x] Bug Hunting 四 Hunter 机制文档化
- [x] 8 条 Codex 规则全部验证通过
- [x] Git committed: `1ba262d`

---

## 阶段 F: 文档更新 + 规则审计

### 文档交付
- Spec: `docs/superpowers/specs/2026-06-10-ai-news-digest-v1.0-design.md`
- Plan: `docs/superpowers/plans/2026-06-10-ai-news-digest-v1.0.md`
- Cycle Report: `docs/superpowers/reports/2026-06-10-cycle-8-report.md`
- PROJECT-OVERVIEW.md 同步更新 (v1.0)

### 规则审计
- 新增 R11: Bug Hunting 学习回路
- 现有 10 条规则全部保留
- 三视角审查流程已证明价值：6 项设计问题在规划阶段修正

---

## 项目整体进度

| 版本 | 测试 | Commits | 覆盖率 | 关键交付 |
|------|------|---------|--------|---------|
| v0.1 | 28 | 3 | — | MVP |
| v0.2 | 54 | 5 | — | 测试+DB+源管理+周报+导出 |
| v0.3 | 60 | 6 | — | Telegram+GitHub BS4+API限流 |
| v0.4 | 108 | 7 | 71% | 批量commit+模板单例+智能探索 |
| v0.5 | 166 | 11 | 82% | 管道编排+PushChannel+定时+排序+源发现+反馈 |
| v0.6 | 182 | 6 | 82% | 5维分析+横向对比+折叠UI+过载控制 |
| v0.7 | 198 | 8 | 83% | 概念提取+关联图+双引擎推荐+MD周刊 |
| v0.8 | 216 | 5 | 84% | 图谱历史+推荐聚类+周报数据驱动 |
| **v1.0** | **233** | **5 feat + 2 fix + 1 docs** | **82%** | **知识图谱三层升级 + 概念轨迹页 + Bug Hunting + Codex交接** |

**累计:** 28→233 tests (+732%), 9 个版本全部交付。v1.0 正式发布。

**下一步:** Codex 审阅 → v1.1（concept_edges, weekly snapshots, 月度趋势, 实体解析）
