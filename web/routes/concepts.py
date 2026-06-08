from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from web.app import get_db
from db.models import get_concepts_list

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/concepts", response_class=HTMLResponse)
async def concepts_list(request: Request):
    concepts = get_concepts_list(get_db()) if get_db() else []
    return templates.TemplateResponse("concepts.html", {"request": request, "concepts": concepts})
