# AI 资讯管家 v0.2 Design

**Date:** 2026-06-09
**Status:** Approved
**Theme:** 稳定性 + 可维护性

## Scope

6 tasks, focused on fixing audit gaps and adding low-effort high-value features.

### Task 1: Test Coverage — Critical Path
- **DB models:** `normalize_url`, `make_article_id`, `search_articles`, `get_or_create_concept`, `cache_analysis`, `get_cached_analysis`, `save_weekly_review`, `cleanup_old_data`
- **Collectors:** Arxiv (mocked XML), HackerNews (mocked API), GitHub Trending (mocked HTML)
- **Push:** `send_wecom_digest` (format, truncation, error handling)
- **API routes:** analyze SSE, translate SSE, concept-lookup, generate-review
- **Target:** 15 → 45+ tests, >50% module coverage

### Task 2: db/models.py Refactor
- Split into: `db/url_utils.py`, `db/models.py` (CRUD), `db/queries.py` (higher-level), `db/digest.py`, `db/maintenance.py`
- Move raw SQL from `main.py` and `web/routes/api.py` into new DB functions
- Re-export from `db/__init__.py`

### Task 3: Source Management Web UI
- New page `/sources` — list, enable/disable, add, remove sources
- New API endpoints: `GET /api/sources`, `POST /api/sources`, `DELETE /api/sources/{id}`, `PATCH /api/sources/{id}`
- Sources stored in DB (already have `sources` table)
- No restart required — collectors read from DB registry

### Task 4: Reddit → RSSHub Migration
- Replace `https://www.reddit.com/r/MachineLearning/.rss` with RSSHub instance
- Default: `https://rsshub.app/reddit/r/MachineLearning`
- Configurable via `config.yaml` or source management UI

### Task 5: Weekly Review Auto-Push
- Check on startup: if Monday and no review pushed this week, generate + push
- Add `weekly_review_sent` flag to `weekly_reviews` table
- Reuse existing `build_review_prompt` + `send_wecom_digest` (add a `send_wecom_review` variant)

### Task 6: Markdown Export
- Export button on reader page → download article as .md
- Export button on review page → download review as .md
- API endpoints: `GET /api/export/article/{id}`, `GET /api/export/review`
- Simple template: title, metadata, content/analysis in markdown

## Architecture

```
v0.2 additions:
db/          +url_utils.py, +queries.py, +digest.py, +maintenance.py
web/routes/  +sources.py
web/templates/ +sources.html
tests/       +test_url_utils.py, +test_queries.py, +test_push.py, +test_api.py
```

No new dependencies. All within existing stack (FastAPI + SQLite + Jinja2 + htmx).
