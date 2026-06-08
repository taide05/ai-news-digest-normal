from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import get_clusters_for_date

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = get_db()
    if db is None:
        return templates.TemplateResponse("home.html", {"request": request, "clusters": [], "today": "", "empty": True})

    today = datetime.now().strftime("%Y-%m-%d")
    clusters = get_clusters_for_date(db, today)

    return templates.TemplateResponse("home.html", {
        "request": request,
        "clusters": clusters,
        "today": today,
        "empty": len(clusters) == 0,
    })
