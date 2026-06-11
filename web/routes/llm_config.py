from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from web.globals import get_db
from db.models import get_setting, set_setting
from web.templates import templates

router = APIRouter()


@router.get("/admin/llm", response_class=HTMLResponse)
async def llm_config_page(request: Request):
    db = get_db()
    config = {
        "provider": get_setting(db, "llm.provider", "deepseek"),
        "model": get_setting(db, "llm.model", "deepseek-chat"),
        "api_key": get_setting(db, "llm.api_key", ""),
        "base_url": get_setting(db, "llm.base_url", "https://api.deepseek.com"),
    }
    return templates.TemplateResponse(request, "llm_config.html", {"config": config})


@router.post("/api/llm-config")
async def api_llm_config_save(request: Request):
    db = get_db()
    if not db:
        return JSONResponse({"status": "error", "message": "DB not available"})

    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = {key: form[key] for key in form}
    except Exception:
        return JSONResponse({"status": "error", "message": "Invalid request body"}, status_code=400)

    provider = str(data.get("provider", "deepseek")).strip()
    if provider not in ("deepseek", "ollama", "openrouter", "openai_compatible"):
        provider = "deepseek"

    model = str(data.get("model", "deepseek-chat")).strip()
    api_key = str(data.get("api_key", "")).strip()
    base_url = str(data.get("base_url", "https://api.deepseek.com")).strip()

    set_setting(db, "llm.provider", provider, commit=False)
    set_setting(db, "llm.model", model, commit=False)
    set_setting(db, "llm.api_key", api_key, commit=False)
    set_setting(db, "llm.base_url", base_url, commit=True)

    return HTMLResponse(
        '<span class="status-success">已保存。重启应用后生效。</span>'
    )
