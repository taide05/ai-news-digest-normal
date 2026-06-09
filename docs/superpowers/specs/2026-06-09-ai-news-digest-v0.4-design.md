# AI 资讯管家 v0.4 Design

**Date:** 2026-06-09
**Status:** Approved
**Theme:** 性能 + 测试覆盖 + 代码整洁

## Scope — 4 tasks

### Task 1: 批量 Commit（CRITICAL 性能）
- `db/models.py`, `db/digest.py`, `db/maintenance.py` 所有写函数加 `commit=False` 参数
- 调用方负责最终 `conn.commit()`
- `main.py` 的 `run_collection_pipeline` 只在所有写入完成后 commit 一次
- web routes 中的单个写操作保持 `commit=True`（默认行为）

### Task 2: 测试覆盖率 50%→70%（CRITICAL）
- 优先覆盖: `web/routes/sources.py`, `web/routes/export.py`, `collectors/github_trending.py`
- 补: `push_telegram.py` review push 测试, `_escape_mdv2` 全部 18 字符测试
- 补: `web/routes/api.py` 限流 429 测试
- 目标: 60 → 80+ tests

### Task 3: Jinja2Templates 单例（MEDIUM）
- 在 `web/templates.py` 创建单一 `templates` 实例
- 所有路由文件从中 import，不再各自实例化
- 自定义 filters 在单例上注册一次

### Task 4: 智能探索率（MEDIUM）
- 当前: 固定 15% 文章标记 `[探索]`
- 改进: 调用 AI 判断每篇是否需要探索（新概念/新源/与已有知识差距大）
- 在 `ai/analysis.py` 加 `build_exploration_prompt`
- `config.yaml` 保留 `exploration_rate` 作为 fallback 上限

## Architecture
```
v0.4 modifications:
db/models.py     — 所有写函数加 commit param
db/digest.py     — commit param
db/maintenance.py — already has param, just verify
main.py          — 单次 commit
web/templates.py — NEW: 单例 Jinja2Templates
web/routes/*.py  — import from web.templates
ai/analysis.py   — +build_exploration_prompt
tests/           — +test_sources.py, +test_export.py, +test_github_bs4.py
```
