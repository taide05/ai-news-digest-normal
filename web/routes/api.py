import asyncio
import html
import json
import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from web.limiter import limiter
from web.globals import get_db, get_ai, get_config
from db.models import (
    get_article, set_full_text, get_cached_analysis, cache_analysis,
    set_feedback, get_or_create_concept, link_article_concept,
    get_concepts_list, get_pending_candidates, verify_candidate, reject_candidate,
    cache_cross_analysis, get_cached_cross_analysis,
    get_recommendations_interest, get_recommendations_cluster, get_recent_articles,
)
from ai.analysis import (
    build_core_insight_prompt, build_what_it_means_prompt,
    build_translation_prompt, build_concept_lookup_prompt,
    build_cross_comparison_prompt, build_concept_extraction_prompt,
    _EXTRACTION_ERRORS,
)
from pipeline.extractor import extract_full_text

logger = logging.getLogger("api")
router = APIRouter()

# Per-cluster lock to prevent duplicate LLM calls (TOCTOU guard)
_cluster_locks: dict[str, asyncio.Lock] = {}

# Cache for user topics (invalidated on "interested" feedback)
_user_topics_cache: list[str] | None = None

_EXTRACTION_ERROR_SET = set(_EXTRACTION_ERRORS)


# ── source candidate APIs ───────────────────────────────────────────

@router.get("/api/source-candidates")
async def list_source_candidates(request: Request = None):
    db = get_db()
    if db is None:
        return JSONResponse({"candidates": []})
    candidates = get_pending_candidates(db)
    return JSONResponse({"candidates": candidates})


@router.post("/api/source-candidates/{candidate_id}/verify")
@limiter.limit("10/minute")
async def verify_source_candidate(candidate_id: int, request: Request = None):
    db = get_db()
    if db is None:
        return HTMLResponse('<tr><td colspan="4" style="color:red;padding:10px;">数据库不可用</td></tr>')
    verify_candidate(db, candidate_id)
    return HTMLResponse('<tr><td colspan="4" style="color:#4caf50;padding:10px;">已确认，已加入信息源列表</td></tr>')


@router.post("/api/source-candidates/{candidate_id}/reject")
@limiter.limit("10/minute")
async def reject_source_candidate(candidate_id: int, request: Request = None):
    db = get_db()
    if db is None:
        return HTMLResponse('<tr><td colspan="4" style="color:red;padding:10px;">数据库不可用</td></tr>')
    reject_candidate(db, candidate_id)
    return HTMLResponse('<tr><td colspan="4" style="color:#888;padding:10px;">已拒绝</td></tr>')


# ── SSE helper ──────────────────────────────────────────────────────

def _safe_sse_chunk(chunk: str) -> str:
    """Encode chunk as SSE-safe JSON, replacing malformed UTF-8 surrogates."""
    sanitized = chunk.encode("utf-8", errors="replace").decode("utf-8")
    return json.dumps({"chunk": sanitized})


async def _sse_stream(ai, system_prompt: str, user_prompt: str, max_tokens: int,
                      db, article_id: str, analysis_type: str):
    full_response = ""
    for chunk in ai.chat_stream(system_prompt, user_prompt, max_tokens=max_tokens):
        full_response += chunk
        yield f"data: {_safe_sse_chunk(chunk)}\n\n"
    try:
        cache_analysis(db, article_id, analysis_type, full_response)
    except Exception as e:
        logger.warning("Failed to cache analysis for article %s type %s: %s", article_id, analysis_type, e)
    yield "data: [DONE]\n\n"


def _get_user_topics(db) -> list[str]:
    """Extract user interest topics from read_records for personalization."""
    global _user_topics_cache
    if _user_topics_cache is not None:
        return _user_topics_cache
    rows = db.execute(
        "SELECT DISTINCT topics FROM read_records WHERE topics != '' AND feedback = 'interested'"
    ).fetchall()
    topics = []
    for (t,) in rows:
        for topic in t.split(","):
            topic = topic.strip()
            if topic and topic not in topics:
                topics.append(topic)
    _user_topics_cache = topics[:10]
    return _user_topics_cache


def _get_recent_read_titles(db, limit: int = 10) -> list[str]:
    """Get titles of recently read articles for context."""
    rows = db.execute(
        "SELECT a.title FROM read_records r JOIN articles a ON r.article_id = a.id "
        "ORDER BY r.opened_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [r[0] for r in rows]


# ── analyze / translate / concept-lookup / feedback / review ────────

@router.get("/api/analyze/{article_id}")
@limiter.limit("10/minute")
async def analyze(article_id: str, type: str = Query(...), request: Request = None):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return StreamingResponse(iter(["AI 服务未配置"]), media_type="text/event-stream")

    article = get_article(db, article_id)
    if article is None:
        return StreamingResponse(iter(["文章不存在"]), media_type="text/event-stream")

    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text in _EXTRACTION_ERROR_SET:
        extracted = await extract_full_text(article["url"])
        if extracted not in _EXTRACTION_ERROR_SET:
            full_text = extracted
            try:
                set_full_text(db, article_id, full_text)
            except Exception as e:
                logger.warning("Failed to save full_text for article %s: %s", article_id, e)
        elif not full_text:
            full_text = extracted

    if full_text in _EXTRACTION_ERROR_SET:
        return StreamingResponse(iter([full_text]), media_type="text/event-stream")

    cached = get_cached_analysis(db, article_id, type)
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps({'chunk': cached})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    if type == "core_insight":
        system, user = build_core_insight_prompt(full_text)
        max_tokens = 1024
    elif type == "what_it_means":
        concepts = [c["term"] for c in get_concepts_list(db)]
        user_topics = _get_user_topics(db)
        read_titles = _get_recent_read_titles(db)
        system, user = build_what_it_means_prompt(full_text, concepts, user_topics, read_titles)
        max_tokens = 2048
    else:
        return StreamingResponse(iter(["未知分析类型"]), media_type="text/event-stream")

    return StreamingResponse(
        _sse_stream(ai, system, user, max_tokens, db, article_id, type),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/translate/{article_id}")
@limiter.limit("10/minute")
async def translate(article_id: str, request: Request = None):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return StreamingResponse(iter(["AI 服务未配置"]), media_type="text/event-stream")

    article = get_article(db, article_id)
    if article is None:
        return StreamingResponse(iter(["文章不存在"]), media_type="text/event-stream")

    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text in _EXTRACTION_ERROR_SET:
        extracted = await extract_full_text(article["url"])
        if extracted not in _EXTRACTION_ERROR_SET:
            full_text = extracted
            try:
                set_full_text(db, article_id, full_text)
            except Exception as e:
                logger.warning("Failed to save full_text for article %s: %s", article_id, e)
        elif not full_text:
            full_text = extracted

    if full_text in _EXTRACTION_ERROR_SET:
        return StreamingResponse(iter([full_text]), media_type="text/event-stream")

    cached = get_cached_analysis(db, article_id, "translation")
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps({'chunk': cached})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    system, user = build_translation_prompt(full_text)
    return StreamingResponse(
        _sse_stream(ai, system, user, 2048, db, article_id, "translation"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/concept-lookup")
@limiter.limit("10/minute")
async def concept_lookup(request: Request):
    db = get_db()
    ai = get_ai()
    data = await request.json()
    term = data.get("term", "").strip()
    article_id = data.get("article_id", "")

    if not term or db is None or ai is None:
        return JSONResponse({"term": term, "definition": ""})

    system, user = build_concept_lookup_prompt(term)
    definition, _ = ai.chat(system, user, max_tokens=200)

    cid = get_or_create_concept(db, term, definition)
    if article_id:
        link_article_concept(db, article_id, cid)

    return JSONResponse({"term": term, "definition": definition})


@router.get("/api/auto-extract-concepts/{article_id}")
@limiter.limit("10/minute")
async def auto_extract_concepts(article_id: str, request: Request = None):
    db = get_db()
    if db is None:
        return HTMLResponse("")

    cached = get_cached_analysis(db, article_id, "concepts")
    if cached:
        terms = json.loads(cached)
        if terms:
            badges = "".join(
                f'<span style="background:#1a237e;color:#fff;padding:2px 8px;border-radius:3px;margin:2px;font-size:0.85em;display:inline-block;">{html.escape(t)}</span>'
                for t in terms
            )
            return HTMLResponse(f'<span style="color:#888;">本文概念：</span>{badges}')
        return HTMLResponse("")

    article = get_article(db, article_id)
    if article is None:
        return HTMLResponse("")

    full_text = article.get("full_text") or article.get("content") or ""
    if not full_text or full_text in _EXTRACTION_ERROR_SET:
        return HTMLResponse("")

    ai = get_ai()
    if ai is None:
        return HTMLResponse("")

    system, user = build_concept_extraction_prompt(full_text)
    try:
        raw, tokens = ai.chat(system, user, max_tokens=100)
    except Exception as e:
        logger.warning("Concept extraction failed for article %s: %s", article_id, e)
        return HTMLResponse("")

    raw = raw.strip().strip('"').strip("'")
    if raw == "无" or not raw:
        cache_analysis(db, article_id, "concepts", "[]", tokens_used=tokens)
        return HTMLResponse("")

    terms = [t.strip().strip('\'"') for t in raw.split(",") if t.strip()]
    new_terms = []
    for term in terms:
        cid = get_or_create_concept(db, term, commit=False)
        link_article_concept(db, article_id, cid, commit=False)
        new_terms.append(term)
    db.commit()

    concepts_json = json.dumps(new_terms)
    cache_analysis(db, article_id, "concepts", concepts_json, tokens_used=tokens)

    badges = "".join(
        f'<span style="background:#1a237e;color:#fff;padding:2px 8px;border-radius:3px;margin:2px;font-size:0.85em;display:inline-block;">{html.escape(t)}</span>'
        for t in new_terms
    )
    return HTMLResponse(f'<span style="color:#888;">本文概念：</span>{badges}')


@router.get("/api/recommend/{article_id}")
@limiter.limit("10/minute")
async def recommend(article_id: str, request: Request = None):
    db = get_db()
    if db is None:
        return HTMLResponse("")

    interest = get_recommendations_interest(db, article_id, limit=2)
    cluster = get_recommendations_cluster(db, limit=2)

    seen = set()
    merged = []
    for r in interest + cluster:
        if r["id"] not in seen and r["id"] != article_id:
            seen.add(r["id"])
            merged.append(r)
        if len(merged) >= 4:
            break

    # Fallback: if not enough recommendations, fill with recent articles
    if len(merged) < 2:
        recents = get_recent_articles(db, article_id, exclude_read=True,
                                       limit=4 - len(merged))
        for r in recents:
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append({"id": r["id"], "title": r["title"],
                               "source_id": r["source_id"], "reason": "热门文章"})

    if not merged:
        return HTMLResponse("")

    cards = ""
    for r in merged:
        cards += (
            f'<div style="padding:8px 12px;margin:4px 0;background:var(--surface);border-radius:4px;'
            f'border-left:3px solid #2196f3;">'
            f'<a href="/reader/{r["id"]}" style="font-weight:500;">{html.escape(r["title"])}</a>'
            f'<span style="color:#888;font-size:0.8em;margin-left:8px;">{html.escape(r["source_id"])}</span>'
            f'<div style="color:#9c27b0;font-size:0.8em;margin-top:2px;">{html.escape(r["reason"])}</div>'
            f'</div>'
        )
    return HTMLResponse(
        f'<div style="margin:24px 0;">'
        f'<h4 style="margin-bottom:8px;">推荐阅读</h4>{cards}</div>'
    )


@router.post("/api/feedback/{article_id}")
@limiter.limit("30/minute")
async def feedback(article_id: str, feedback: str = Query(...), request: Request = None):
    global _user_topics_cache
    db = get_db()
    if db is None:
        return HTMLResponse('<span style="color:red;">错误</span>')
    set_feedback(db, article_id, feedback, commit=False)

    if feedback == "interested":
        _user_topics_cache = None
        try:
            article = get_article(db, article_id)
            if article:
                ai = get_ai()
                if ai:
                    title = article.get("title", "")
                    if title:
                        sys_p = "用一个逗号分隔的关键词列表（不超过5个）描述这篇文章的主题领域。只输出关键词。"
                        usr_p = f"标题：{title}"
                        topics, _ = ai.chat(sys_p, usr_p, max_tokens=30)
                        topics = topics.strip().strip('"').strip("'")
                        db.execute(
                            "UPDATE read_records SET topics = ? WHERE article_id = ? "
                            "AND id = (SELECT MAX(id) FROM read_records WHERE article_id = ?)",
                            (topics, article_id, article_id)
                        )
        except Exception:
            pass
    db.commit()

    label = "已标记感兴趣" if feedback == "interested" else "已标记不感兴趣"
    color = "#4caf50" if feedback == "interested" else "#f44336"
    return HTMLResponse(f'<span style="color:{color};font-weight:500;">{label}</span>')


@router.post("/api/generate-review")
@limiter.limit("5/minute")
async def generate_review(request: Request = None):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return HTMLResponse('<div class="error">AI 服务未配置</div>')

    import orchestrator as orch
    cfg = get_config()
    result = orch.generate_weekly_review(db, ai, cfg)
    if result is None:
        return HTMLResponse('<div class="error">没有足够的阅读数据生成周报</div>')
    if result.get("status") == "exists":
        html = result["review"].replace('\n', '<br>')
        return HTMLResponse(f'<div class="review-result">{html}</div>')
    html = result["content"].replace('\n', '<br>')
    return HTMLResponse(f'<div class="review-result">{html}</div>')


@router.post("/api/cross-compare/{cluster_id}")
@limiter.limit("5/minute")
async def cross_compare(cluster_id: str, request: Request = None):
    if not cluster_id or len(cluster_id) > 128:
        return HTMLResponse('<div class="error">无效的 cluster_id</div>')

    db = get_db()
    if db is None:
        return HTMLResponse('<div class="error">数据库未配置</div>')

    cached = get_cached_cross_analysis(db, cluster_id, "cross_comparison")
    if cached:
        return HTMLResponse(f'<div class="cross-compare-result">{cached.replace(chr(10), "<br>")}</div>')

    lock = _cluster_locks.setdefault(cluster_id, asyncio.Lock())
    async with lock:
        cached = get_cached_cross_analysis(db, cluster_id, "cross_comparison")
        if cached:
            return HTMLResponse(f'<div class="cross-compare-result">{cached.replace(chr(10), "<br>")}</div>')

        try:
            arts = db.execute(
                "SELECT a.id, a.title, a.source_id, a.url, "
                "COALESCE(ac.content, '') as insight "
                "FROM cluster_articles ca "
                "JOIN articles a ON ca.article_id = a.id "
                "LEFT JOIN analysis_cache ac ON a.id = ac.article_id AND ac.analysis_type = 'core_insight' "
                "WHERE ca.cluster_id = ?",
                (cluster_id,)
            ).fetchall()
        except Exception as e:
            logger.warning("DB read error in cross_compare for cluster %s: %s", cluster_id, e)
            return HTMLResponse('<div class="error">数据查询失败</div>')

        if len(arts) == 0:
            return HTMLResponse('<div class="error">话题不存在</div>')
        if len(arts) < 3:
            return HTMLResponse(f'<div class="error">本话题仅有 {len(arts)} 篇文章，至少需要 3 篇</div>')

        ai = get_ai()
        if ai is None:
            return HTMLResponse('<div class="error">AI 服务未配置</div>')

        cluster_articles = [
            {"title": r[1], "source_id": r[2], "url": r[3], "insight": r[4]}
            for r in arts
        ]

        system, user = build_cross_comparison_prompt(cluster_articles)
        try:
            content, tokens = ai.chat(system, user, max_tokens=1024)
        except Exception as e:
            logger.warning("AI chat error in cross_compare for cluster %s: %s", cluster_id, e)
            return HTMLResponse('<div class="error">AI 分析失败，请稍后重试</div>')

        article_ids = [r[0] for r in arts]
        try:
            cache_cross_analysis(db, cluster_id, "cross_comparison",
                                 content[:10000], article_ids, tokens_used=tokens)
        except Exception as e:
            logger.warning("Failed to cache cross_analysis for cluster %s: %s", cluster_id, e)

        return HTMLResponse(f'<div class="cross-compare-result">{content.replace(chr(10), "<br>")}</div>')


@router.post("/api/collect")
@limiter.limit("30/minute")
async def trigger_collect(request: Request = None):
    return JSONResponse({"status": "unavailable", "message": "Collection is triggered automatically on startup; manual collection via API is not supported yet."})
