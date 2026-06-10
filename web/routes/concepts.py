from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import get_concepts_list, get_concept_node_history, get_concept_nodes_by_date
from web.templates import templates
from datetime import date

router = APIRouter()


@router.get("/concepts", response_class=HTMLResponse)
async def concepts_list(request: Request):
    concepts = get_concepts_list(get_db()) if get_db() else []
    return templates.TemplateResponse(request, "concepts.html", {"concepts": concepts})


@router.get("/concepts/{label:path}", response_class=HTMLResponse)
async def concept_detail(request: Request, label: str):
    db = get_db()
    if not db:
        return templates.TemplateResponse(request, "concept_detail.html", {
            "concept_label": label, "lifecycle_state": "new",
            "lifecycle_state_display": "新概念", "first_seen": "-",
            "last_seen": "-", "total_articles": 0,
            "history": [], "chart_points": "", "related_articles": []
        })

    history = get_concept_node_history(db, label, days=90)
    today_nodes = get_concept_nodes_by_date(db, date.today().isoformat())
    current = next((n for n in today_nodes if n["label"] == label), None)

    lifecycle_state = current["lifecycle_state"] if current else "new"
    state_display = {
        "new": "新概念", "rising": "上升中", "stable": "稳定",
        "declining": "下降中"
    }.get(lifecycle_state, lifecycle_state)

    # Build SVG chart points
    chart_points = ""
    if history and len(history) > 1:
        max_w = max(h["weight"] for h in history) or 1
        width = 800
        height = 200
        step = width / (len(history) - 1)
        points = []
        for i, h in enumerate(history):
            x = int(i * step)
            y = int(height - (h["weight"] / max_w) * (height - 20) - 10)
            points.append(f"{x},{y}")
        chart_points = " ".join(points)

    # Related articles
    related_articles = []
    if db:
        rows = db.execute(
            "SELECT DISTINCT a.id, a.title, a.source_id, a.published_at "
            "FROM articles a "
            "JOIN article_concepts ac ON a.id = ac.article_id "
            "JOIN concepts c ON ac.concept_id = c.id "
            "WHERE c.term = ? "
            "ORDER BY a.published_at DESC LIMIT 20",
            (label,)
        ).fetchall()
        related_articles = [
            {"id": r[0], "title": r[1], "source_id": r[2], "published_at": r[3]}
            for r in rows
        ]

    return templates.TemplateResponse(request, "concept_detail.html", {
        "concept_label": label,
        "lifecycle_state": lifecycle_state,
        "lifecycle_state_display": state_display,
        "first_seen": history[0]["snap_date"] if history else "-",
        "last_seen": history[-1]["snap_date"] if history else "-",
        "total_articles": sum(h["article_count"] for h in history),
        "history": history,
        "chart_points": chart_points,
        "related_articles": related_articles,
    })
