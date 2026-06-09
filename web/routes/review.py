from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.globals import get_db
from utils import get_week_bounds
from db.models import get_weekly_review
from web.filters import nl2br

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["nl2br"] = nl2br


@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    db = get_db()
    week_start, week_end = get_week_bounds()
    review_data = get_weekly_review(db, week_start) if db else None
    return templates.TemplateResponse(request, "review.html", {
        "review": review_data,
        "week_start": week_start,
        "week_end": week_end,
    })
