from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import get_graph_data
from web.templates import templates

router = APIRouter()


@router.get("/graph", response_class=HTMLResponse)
async def graph(request: Request, period: str = Query("today")):
    db = get_db()
    nodes = []
    edges = []
    if db:
        rows = get_graph_data(db, period)
        seen_articles = set()
        seen_concepts = set()
        for r in rows:
            aid = r["article_id"]
            concept = r["concept"]
            if aid not in seen_articles:
                nodes.append({
                    "id": aid, "label": r["title"][:20],
                    "type": "article", "source_id": r["source_id"]
                })
                seen_articles.add(aid)
            if concept not in seen_concepts:
                nodes.append({
                    "id": concept, "label": concept,
                    "type": "concept", "query_count": r["query_count"]
                })
                seen_concepts.add(concept)
            edges.append({"from": aid, "to": concept})

    return templates.TemplateResponse(request, "graph.html", {
        "nodes": nodes, "edges": edges, "period": period,
        "node_count": len(nodes), "edge_count": len(edges),
    })
