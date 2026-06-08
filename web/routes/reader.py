from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import get_article, record_read

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/reader/{article_id}", response_class=HTMLResponse)
async def reader(request: Request, article_id: str):
    db = get_db()
    article = get_article(db, article_id) if db else None
    if article is None:
        return HTMLResponse("Article not found", status_code=404)

    record_read(db, article_id)
    return templates.TemplateResponse("reader.html", {"request": request, "article": article})
