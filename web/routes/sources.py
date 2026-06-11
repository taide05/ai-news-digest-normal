from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from web.globals import get_db
from db.models import get_all_sources, add_source, remove_source, toggle_source, update_source_filter, update_source_keywords, get_pending_candidates
from web.templates import templates

router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    db = get_db()
    sources = get_all_sources(db) if db else []
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})


async def _parse_request_data(request: Request):
    """Parse request body as JSON or form-encoded, returning a dict or raising ValueError."""
    try:
        return await request.json()
    except Exception:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            return {key: form[key] for key in form}
        raise ValueError("Invalid request body")


@router.post("/api/sources")
async def api_add_source(request: Request):
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})
    try:
        data = await _parse_request_data(request)
        sid = str(data.get("id", "")).strip()
        name = str(data.get("name", "")).strip()
        stype = str(data.get("type", "")).strip()
        config = str(data.get("config", "")).strip()
        filter_keywords = str(data.get("filter_keywords", "[]")).strip()
        hide_kw = str(data.get("hide_keywords", "[]")).strip()
        highlight_kw = str(data.get("highlight_keywords", "[]")).strip()
        require_kw = str(data.get("require_keywords", "[]")).strip()
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid request body"}, status_code=400)

    if not sid or not name or not stype:
        return JSONResponse({"status": "error", "message": "id, name, type are required"}, status_code=400)
    if not all(c.isalnum() or c in "-_" for c in sid):
        return JSONResponse({"status": "error", "message": "ID must be alphanumeric"}, status_code=400)

    import json

    def _validate_kw_array(val: str, field_name: str) -> str | None:
        if not val or val == "[]":
            return None
        try:
            parsed = json.loads(val)
            if not isinstance(parsed, list):
                return f"{field_name} must be a JSON array"
        except (json.JSONDecodeError, TypeError):
            return f"{field_name} must be a valid JSON array"
        return None

    try:
        json.loads(config)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"status": "error", "message": "Config must be valid JSON"}, status_code=400)

    for val, name in [(filter_keywords, "filter_keywords"), (hide_kw, "hide_keywords"),
                       (highlight_kw, "highlight_keywords"), (require_kw, "require_keywords")]:
        err = _validate_kw_array(val, name)
        if err:
            return JSONResponse({"status": "error", "message": err}, status_code=400)

    ok = add_source(db, sid, name, stype, config, filter_keywords,
                    hide_keywords=hide_kw, highlight_keywords=highlight_kw,
                    require_keywords=require_kw)
    if ok:
        return JSONResponse({"status": "ok"}, headers={"HX-Refresh": "true"})
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
        data = await _parse_request_data(request)
    except Exception:
        data = {}
    # htmx checkbox: when unchecked, 'enabled' is absent from form data
    if "enabled" not in data:
        content_type = request.headers.get("content-type", "")
        is_form = "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type
        if is_form:
            data["enabled"] = False
    # Normalize enabled value (string from form data → bool)
    if "enabled" in data and isinstance(data["enabled"], str):
        data["enabled"] = data["enabled"].lower() in ("true", "on", "1")
    import json
    kw_updated = False
    hide_kw = str(data.get("hide_keywords", "")).strip()
    highlight_kw = str(data.get("highlight_keywords", "")).strip()
    require_kw = str(data.get("require_keywords", "")).strip()
    if hide_kw or highlight_kw or require_kw:
        for val, name in [(hide_kw, "hide_keywords"), (highlight_kw, "highlight_keywords"),
                           (require_kw, "require_keywords")]:
            if val and val != "[]":
                try:
                    parsed_kw = json.loads(val)
                    if not isinstance(parsed_kw, list):
                        return JSONResponse({"status": "error", "message": f"{name} must be a JSON array"}, status_code=400)
                except (json.JSONDecodeError, TypeError):
                    return JSONResponse({"status": "error", "message": f"{name} must be a valid JSON array"}, status_code=400)
        update_source_keywords(db, sid, hide_kw or "[]", highlight_kw or "[]", require_kw or "[]")
        kw_updated = True

    if "filter_keywords" in data:
        try:
            parsed_kw = json.loads(data["filter_keywords"])
            if not isinstance(parsed_kw, list):
                return JSONResponse({"status": "error", "message": "filter_keywords must be a JSON array"}, status_code=400)
        except (json.JSONDecodeError, TypeError):
            return JSONResponse({"status": "error", "message": "filter_keywords must be a valid JSON array"}, status_code=400)
        update_source_filter(db, sid, data["filter_keywords"])
        kw_updated = True
    if "enabled" in data or ("filter_keywords" not in data and not kw_updated):
        toggle_source(db, sid, data.get("enabled", True))
    return JSONResponse({"status": "ok"})


@router.get("/sources/candidates", response_class=HTMLResponse)
async def source_candidates_page(request: Request):
    db = get_db()
    candidates = get_pending_candidates(db) if db else []
    return templates.TemplateResponse(request, "source_candidates.html", {
        "candidates": candidates,
    })
