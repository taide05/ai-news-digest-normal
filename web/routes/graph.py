from datetime import date as _date
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import (get_graph_data, get_graph_snapshot, get_snapshot_dates,
                       get_graph_data_from_nodes)
from web.templates import templates


router = APIRouter()


def _build_nodes_and_edges(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Convert raw DB rows into deduplicated node/edge lists."""
    nodes = []
    edges = []
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
    return nodes, edges


@router.get("/graph", response_class=HTMLResponse)
async def graph(request: Request, period: str = Query("today"),
                compare: str = Query("")):
    db = get_db()
    nodes = []
    edges = []
    dates = []
    compare_nodes = []
    compare_edges = []

    if db:
        today_str = _date.today().isoformat()

        if period == "today":
            # Prefer concept_nodes for today, fallback to live JOIN
            rows = get_graph_data_from_nodes(db, today_str)
            if not rows:
                rows = get_graph_data(db, period)
        else:
            rows = get_graph_data(db, period)

        nodes, edges = _build_nodes_and_edges(rows)
        dates = get_snapshot_dates(db)

        if compare:
            snap = get_graph_snapshot(db, compare, period)
            if snap:
                compare_nodes = snap.get("nodes", [])
                compare_edges = snap.get("edges", [])

    return templates.TemplateResponse(request, "graph.html", {
        "nodes": nodes, "edges": edges, "period": period,
        "node_count": len(nodes), "edge_count": len(edges),
        "dates": dates, "compare": compare,
        "compare_nodes": compare_nodes, "compare_edges": compare_edges,
    })
