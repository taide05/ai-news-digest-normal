from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.globals import get_db
from db.models import search_articles
from web.filters import highlight

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["highlight"] = highlight


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query(default="")):
    results = []
    if q and get_db():
        results = search_articles(get_db(), q)
    return templates.TemplateResponse(request, "search.html", {"query": q, "results": results})
