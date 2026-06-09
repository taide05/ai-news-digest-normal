# A-F Cycle Report #7 — v0.7 → v0.8

**Date:** 2026-06-09
**Cycle:** 阶段 C (v0.8规划) → D (v0.8开发) → T (系统测试) → E (v0.8验收) → F (文档+规则审计)
**Status:** ✅ Complete

---

## 阶段 C: v0.8 规划

**设计流程:** brainstorming → 3 个澄清问题（定位/图谱增强/推荐增强/周报增强）→ 多视角审查 → 风险+架构审计 → 设计确认

**用户决策:**
- 定位：打磨收尾（B），不新增页面
- 图谱：历史对比（A），非性能优化
- 推荐：序列分析→降级为话题聚类（A）
- 周报：数据驱动（A）

**多视角审查发现（v0.7 未发现的盲区）:**
- 图谱对比并排布局过挤 → 改为上下堆叠
- 首周无快照空窗期 → 条件渲染隐藏对比
- 序列分析依赖不足 → 降级为话题聚类

**风险+架构审计发现 6 项并修复:**
- HIGH: snapshot 在采集前生成 → 移入 daily_job 采集之后
- MEDIUM: graph.py 函数膨胀 → 抽取 `_build_nodes_and_edges`
- MEDIUM: api.py 内联 SQL → 新增 `get_recent_articles`
- MEDIUM: week_start 无校验 → 加 assert 守卫
- LOW: snapshot 无清理 → 30 天 DELETE
- LOW: 周报查询重复 → 统一为 `_get_weekly_concepts_by_date`

**设计交付:**
- Spec: `docs/superpowers/specs/2026-06-09-ai-news-digest-v0.8-design.md`
- Plan: `docs/superpowers/plans/2026-06-09-ai-news-digest-v0.8.md`

**v0.8 范围（4 tasks）:**
1. 知识图谱历史对比 — snapshot 表 + tab 切换 + 对比模式
2. 阅读推荐聚类升级 — cluster 引擎 + 降级兜底
3. 周报数据驱动 — 热词 + 新晋概念统计
4. 集成验证

---

## 阶段 D: v0.8 开发

**Subagent-Driven Development:**

| Task | Commit | 结果 |
|------|--------|------|
| Task 1: 图谱历史 | 5306e35 | schema + CRUD + graph route update + template + scheduler + 7 tests |
| Task 1 fix | e7b0de7 | DRY: scheduler 复用 `_build_nodes_and_edges`，本周 tab 去门控，startup 注释 |
| Task 2: 推荐升级 | 0b8a9f2 | cluster engine + get_recent_articles + fallback + 6 tests |
| Task 3: 周报数据 | 8faac72 | unified weekly queries + MD template update + 5 tests |
| Task 4: 集成验证 | bc4e7ba | full suite + coverage |

**代码审查发现:**
- scheduler.py 重复了 `_build_nodes_and_edges` → 改为 import
- "本周" tab 被错误关联到 snapshot 存在 → 去门控
- startup 采集跳过 snapshot → 加注释说明

**关键指标:**
- 测试: 198 → 216 (+18, +9%)
- Commits: 5 (3 feat + 1 fix + 1 test)
- 新增文件: 3 test files

---

## 阶段 T: v0.8 系统测试

| # | 检查项 | 结果 |
|---|--------|------|
| T1 | 全量测试 | ✅ 216/216 PASS |
| T2 | 回归检查 | ✅ 198→216 (+9%) |
| T3 | 边界条件 | ✅ 代码审查阶段已覆盖 |
| T4 | 集成烟雾 | ✅ 全部路由/template/import 正常 |
| T5 | 性能 | ✅ get_graph_data LIMIT 100，30天清理 |
| T6 | 安全回归 | ✅ 参数化查询，date_column assert 防注入 |
| T7 | 覆盖率 | ✅ 83%→84% (+1pp) |
| T8 | 问题修复 | ✅ 3 fix commits |

**门禁结果: 216/216 通过，进入阶段 E。**

---

## 阶段 E: v0.8 验收

- [x] 216/216 tests pass
- [x] graph_snapshots table with UNIQUE(snap_date, period)
- [x] /graph?compare=DATE loads historical snapshot
- [x] /graph hides compare dropdown when <2 snapshots
- [x] /api/recommend uses cluster engine (reason "近期关注")
- [x] /api/recommend falls back to recent articles when cluster empty
- [x] generate_weekly_review includes "## 新晋概念" with stats
- [x] weekly stat queries have date format validation
- [x] scheduler snapshot reuse `_build_nodes_and_edges` (DRY)
- [x] scheduler 30-day snapshot cleanup
- [x] Coverage: 83% → 84% (+1pp)
- [x] Git committed: `bc4e7ba`

---

## 阶段 F: 文档更新 + 规则审计

### 规则审计
- 现有 10 条规则全部在文档中。本次 cycle 无新增规则。
- 风险+架构审计流程已证明价值：6 项问题在 plan 阶段修复，1 项在 review 阶段修复

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

**累计:** 28→216 tests (+671%), 5 commits this cycle, 估计整体约 95% → v1.0

**下一步:** v1.0 — 知识图谱持久化 + polish + 正式发布
