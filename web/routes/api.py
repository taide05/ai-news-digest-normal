import json
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from web.app import get_db, get_ai, get_config
from db.models import (
    get_article, set_full_text, get_cached_analysis, cache_analysis,
    record_read, set_feedback, get_or_create_concept, link_article_concept,
    get_concepts_list, get_weekly_review, save_weekly_review,
)
from ai.analysis import (
    build_core_insight_prompt, build_what_it_means_prompt,
    build_translation_prompt, build_concept_lookup_prompt, build_review_prompt,
)
from ai.review import get_week_bounds
from pipeline.extractor import extract_full_text

router = APIRouter()


async def _sse_stream(ai, system_prompt: str, user_prompt: str, max_tokens: int,
                      db, article_id: str, analysis_type: str):
    full_response = ""
    for chunk in ai.chat_stream(system_prompt, user_prompt, max_tokens=max_tokens):
        full_response += chunk
        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    try:
        cache_analysis(db, article_id, analysis_type, full_response)
    except Exception:
        pass
    yield "data: [DONE]\n\n"


@router.get("/api/analyze/{article_id}")
async def analyze(article_id: str, type: str = Query(...)):
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
    elif type == "what_it_means":
        concepts = [c["term"] for c in get_concepts_list(db)]
        system, user = build_what_it_means_prompt(full_text, concepts)
    else:
        return StreamingResponse(iter(["未知分析类型"]), media_type="text/event-stream")

    return StreamingResponse(
        _sse_stream(ai, system, user, 1024, db, article_id, type),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/translate/{article_id}")
async def translate(article_id: str):
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
async def feedback(article_id: str, feedback: str = Query(...)):
    db = get_db()
    if db is None:
        return JSONResponse({"status": "error"})
    set_feedback(db, article_id, feedback)
    return JSONResponse({"status": "ok"})


@router.post("/api/generate-review")
async def generate_review():
    db = get_db()
    ai = get_ai()
    if db is None or ai is None:
        return JSONResponse({"status": "error", "message": "AI 服务未配置"})

    week_start, week_end = get_week_bounds()
    existing = get_weekly_review(db, week_start)
    if existing:
        return JSONResponse({"status": "ok", "message": "本周周报已存在", "review": existing})

    from datetime import datetime, timedelta
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    rows = db.execute(
        "SELECT a.title, ac.content as insight FROM read_records r "
        "JOIN articles a ON r.article_id = a.id "
        "LEFT JOIN analysis_cache ac ON a.id = ac.article_id AND ac.analysis_type = 'core_insight' "
        "WHERE r.opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()
    articles = [{"title": r[0], "insight": r[1] or ""} for r in rows]
    concepts = [c["term"] for c in get_concepts_list(db)]

    interested = [r[0] for r in db.execute(
        "SELECT DISTINCT a.title FROM read_records r JOIN articles a ON r.article_id = a.id "
        "WHERE r.feedback = 'interested' AND r.opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()]

    not_interested = [r[0] for r in db.execute(
        "SELECT DISTINCT a.title FROM read_records r JOIN articles a ON r.article_id = a.id "
        "WHERE r.feedback = 'not_interested' AND r.opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()]

    system, user = build_review_prompt(articles, concepts, interested, not_interested)
    content, tokens = ai.chat(system, user, max_tokens=2048)

    article_ids = [r[0] for r in db.execute(
        "SELECT article_id FROM read_records WHERE opened_at >= ?",
        (start_dt.strftime("%Y-%m-%d"),)
    ).fetchall()]

    save_weekly_review(db, week_start, week_end, content, article_ids)
    return JSONResponse({"status": "ok", "content": content})


@router.post("/api/collect")
async def trigger_collect():
    import os
    with open(".collect_trigger", "w") as f:
        f.write("1")
    return JSONResponse({"status": "started", "message": "采集已触发"})
