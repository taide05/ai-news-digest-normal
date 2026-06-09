from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from web.globals import get_db
from db.models import get_all_sources, add_source, remove_source, toggle_source

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    db = get_db()
    sources = get_all_sources(db) if db else []
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})


@router.post("/api/sources")
async def api_add_source(request: Request):
    data = await request.json()
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})
    ok = add_source(db, data["id"], data["name"], data["type"], data["config"])
    if ok:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "error", "message": "Source ID already exists"})


@router.delete("/api/sources/{sid}")
async def api_remove_source(sid: str):
    db = get_db()
    if db:
        remove_source(db, sid)
    return JSONResponse({"status": "ok"})


@router.patch("/api/sources/{sid}")
async def api_toggle_source(sid: str, request: Request):
    data = await request.json()
    db = get_db()
    if db:
        toggle_source(db, sid, data.get("enabled", True))
    return JSONResponse({"status": "ok"})
