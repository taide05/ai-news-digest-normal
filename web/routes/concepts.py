from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import get_concepts_list
from web.templates import templates

router = APIRouter()


@router.get("/concepts", response_class=HTMLResponse)
async def concepts_list(request: Request):
    concepts = get_concepts_list(get_db()) if get_db() else []
    return templates.TemplateResponse(request, "concepts.html", {"concepts": concepts})
