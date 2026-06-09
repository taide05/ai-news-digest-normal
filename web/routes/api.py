import json
import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from web.app import limiter
from web.globals import get_db, get_ai, get_config
from db.models import (
    get_article, set_full_text, get_cached_analysis, cache_analysis,
    set_feedback, get_or_create_concept, link_article_concept,
    get_concepts_list, get_pending_candidates, verify_candidate, reject_candidate,
)
from ai.analysis import (
    build_core_insight_prompt, build_what_it_means_prompt,
    build_translation_prompt, build_concept_lookup_prompt,
)
from pipeline.extractor import extract_full_text

logger = logging.getLogger("api")
router = APIRouter()


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
        return JSONResponse({"status": "error", "message": "DB unavailable"})
    verify_candidate(db, candidate_id)
    return JSONResponse({"status": "ok"})


@router.post("/api/source-candidates/{candidate_id}/reject")
@limiter.limit("10/minute")
async def reject_source_candidate(candidate_id: int, request: Request = None):
    db = get_db()
    if db is None:
        return JSONResponse({"status": "error", "message": "DB unavailable"})
    reject_candidate(db, candidate_id)
    return JSONResponse({"status": "ok"})


# ── SSE helper ──────────────────────────────────────────────────────

async def _sse_stream(ai, system_prompt: str, user_prompt: str, max_tokens: int,
                      db, article_id: str, analysis_type: str):
    full_response = ""
    for chunk in ai.chat_stream(system_prompt, user_prompt, max_tokens=max_tokens):
        full_response += chunk
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    try:
        cache_analysis(db, article_id, analysis_type, full_response)
    except Exception as e:
        logger.warning("Failed to cache analysis for article %s type %s: %s", article_id, analysis_type, e)
    yield "data: [DONE]\n\n"


def _get_user_topics(db) -> list[str]:
    """Extract user interest topics from read_records for personalization."""
    rows = db.execute(
        "SELECT DISTINCT topics FROM read_records WHERE topics != '' AND feedback = 'interested'"
    ).fetchall()
    topics = []
    for (t,) in rows:
        for topic in t.split(","):
            topic = topic.strip()
            if topic and topic not in topics:
                topics.append(topic)
    return topics[:10]


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
    if not full_text or full_text.startswith("["):
        full_text = await extract_full_text(article["url"])
        set_full_text(db, article_id, full_text)

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
    if not full_text or full_text.startswith("["):
        full_text = await extract_full_text(article["url"])
        set_full_text(db, article_id, full_text)

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


@router.post("/api/feedback/{article_id}")
@limiter.limit("30/minute")
async def feedback(article_id: str, feedback: str = Query(...), request: Request = None):
    db = get_db()
    if db is None:
        return JSONResponse({"status": "error"})
    set_feedback(db, article_id, feedback)

    # Auto-extract topics from article on positive feedback
    if feedback == "interested":
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
                        db.commit()
        except Exception:
            pass  # best-effort topic extraction

    return JSONResponse({"status": "ok"})


@router.post("/api/generate-review")
@limiter.limit("5/minute")
async def generate_review(request: Request = None):
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return JSONResponse({"status": "error", "message": "AI 服务未配置"})

    import orchestrator as orch
    cfg = get_config()
    result = orch.generate_weekly_review(db, ai, cfg)
    if result is None:
        return JSONResponse({"status": "error", "message": "没有足够的阅读数据生成周报"})
    if result.get("status") == "exists":
        return JSONResponse({"status": "ok", "message": "本周周报已存在", "review": result["review"]})
    return JSONResponse({"status": "ok", "content": result["content"]})


@router.post("/api/collect")
@limiter.limit("30/minute")
async def trigger_collect(request: Request = None):
    return JSONResponse({"status": "unavailable", "message": "Collection is triggered automatically on startup; manual collection via API is not supported yet."})
