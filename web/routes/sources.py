from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from web.globals import get_db
from db.models import get_all_sources, add_source, remove_source, toggle_source, update_source_filter, get_pending_candidates
from web.templates import templates

router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    db = get_db()
    sources = get_all_sources(db) if db else []
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})


@router.post("/api/sources")
async def api_add_source(request: Request):
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})
    try:
        data = await request.json()
        sid = str(data.get("id", "")).strip()
        name = str(data.get("name", "")).strip()
        stype = str(data.get("type", "")).strip()
        config = str(data.get("config", "")).strip()
        filter_keywords = str(data.get("filter_keywords", "[]")).strip()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid request body"}, status_code=400)

    if not sid or not name or not stype:
        return JSONResponse({"status": "error", "message": "id, name, type are required"}, status_code=400)
    if not all(c.isalnum() or c in "-_" for c in sid):
        return JSONResponse({"status": "error", "message": "ID must be alphanumeric"}, status_code=400)

    import json
    try:
        json.loads(config)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"status": "error", "message": "Config must be valid JSON"}, status_code=400)

    try:
        parsed_kw = json.loads(filter_keywords)
        if not isinstance(parsed_kw, list):
            return JSONResponse({"status": "error", "message": "filter_keywords must be a JSON array"}, status_code=400)
    except (json.JSONDecodeError, TypeError):
        return JSONResponse({"status": "error", "message": "filter_keywords must be a valid JSON array"}, status_code=400)

    ok = add_source(db, sid, name, stype, config, filter_keywords)
    if ok:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "error", "message": "Source ID already exists"})


@router.delete("/api/sources/{sid}")
async def api_remove_source(sid: str):
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})
    remove_source(db, sid)
    return JSONResponse({"status": "ok"})


@router.patch("/api/sources/{sid}")
async def api_toggle_source(sid: str, request: Request):
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})
    try:
        data = await request.json()
    except Exception:
        data = {}
    import json
    if "filter_keywords" in data:
        try:
            parsed_kw = json.loads(data["filter_keywords"])
            if not isinstance(parsed_kw, list):
                return JSONResponse({"status": "error", "message": "filter_keywords must be a JSON array"}, status_code=400)
        except (json.JSONDecodeError, TypeError):
            return JSONResponse({"status": "error", "message": "filter_keywords must be a valid JSON array"}, status_code=400)
        update_source_filter(db, sid, data["filter_keywords"])
    if "enabled" in data or "filter_keywords" not in data:
        toggle_source(db, sid, data.get("enabled", True))
    return JSONResponse({"status": "ok"})


@router.get("/sources/candidates", response_class=HTMLResponse)
async def source_candidates_page(request: Request):
    db = get_db()
    candidates = get_pending_candidates(db) if db else []
    return templates.TemplateResponse(request, "source_candidates.html", {
        "candidates": candidates,
    })
