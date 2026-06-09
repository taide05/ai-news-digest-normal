# AI 资讯管家 v0.3 Design

**Date:** 2026-06-09
**Status:** Approved
**Theme:** 多渠道推送 + 稳定性

## Scope — 3 tasks

### Task 1: Telegram Bot 推送
- 新增 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 到 `.env`
- 新增 `push_telegram.py`：`send_telegram_digest()` 和 `send_telegram_review()`
- Telegram API: `POST https://api.telegram.org/bot{token}/sendMessage`，支持 MarkdownV2 格式
- 消息格式：中文标签 + [title](url) 链接（同企微格式）
- 在 `main.py` 中同时调用企微和 Telegram（不互斥）
- 如果 Telegram 未配置则跳过

### Task 2: GitHub Trending 正则 → BeautifulSoup
- 安装 `beautifulsoup4` + `lxml`
- 重写 `collectors/github_trending.py` 的解析逻辑
- 用 BS4 提取：repo name, description, language, stars
- 保留现有 API（`fetch(since)` 返回 `list[Article]`）
- 加测试：mock GitHub HTML，验证解析结果

### Task 3: API 限流
- 安装 `slowapi`
- 对 AI 端点加限流：`/api/analyze/*`, `/api/translate/*`, `/api/concept-lookup`, `/api/generate-review`
- 默认：每个 IP 每分钟 10 次
- 返回 429 + 友好提示

## Architecture
```
v0.3 additions:
push_telegram.py     — Telegram Bot API
.env                + TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
config.py           + telegram_token, telegram_chat_id
collectors/github_trending.py  — rewrite with BS4
web/app.py          + slowapi middleware
tests/test_telegram.py, tests/test_github_bs4.py
```

New dependencies: `beautifulsoup4`, `lxml`, `slowapi`
