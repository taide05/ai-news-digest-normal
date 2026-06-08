from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import search_articles

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query(default="")):
    results = []
    if q and get_db():
        results = search_articles(get_db(), q)
    return templates.TemplateResponse("search.html", {"request": request, "query": q, "results": results})
