import re
from fastapi import APIRouter
from fastapi.responses import Response
from web.globals import get_db
from db.models import get_article, get_cached_analysis
from db.queries import get_weekly_review
from utils import get_week_bounds

router = APIRouter()

_SAFE_FILENAME_RE = re.compile(r'[\x00-\x1f\x7f"*:<>?|\\/]+')


def _safe_filename(name: str, max_len: int = 40) -> str:
    return _SAFE_FILENAME_RE.sub('_', name)[:max_len].rstrip('. ')


@router.get("/api/export/article/{article_id}")
async def export_article(article_id: str):
    db = get_db()
    if not db:
        return Response("DB not available", status_code=500)

    article = get_article(db, article_id)
    if not article:
        return Response("Article not found", status_code=404)

    insight = get_cached_analysis(db, article_id, "core_insight") or ""
    what_it_means = get_cached_analysis(db, article_id, "what_it_means") or ""

    md = f"# {article['title']}\n\n"
    md += f"**来源:** {article['source_id']} | **日期:** {(article.get('published_at') or '')[:10]}\n\n"
    md += f"{article['url']}\n\n---\n\n## 核心观点\n\n{insight}\n\n"
    md += f"---\n\n## 这意味着什么\n\n{what_it_means}\n\n---\n\n## 摘要\n\n{article.get('summary', '')}\n"

    filename = _safe_filename(article['title']) + '.md'
    return Response(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/api/export/review")
async def export_review():
    db = get_db()
    if not db:
        return Response("DB not available", status_code=500)

    week_start, week_end = get_week_bounds()
    review = get_weekly_review(db, week_start)
    if not review:
        return Response("No review for this week", status_code=404)

    md = f"# AI 资讯周报 | {week_start} ~ {week_end}\n\n{review['content']}\n"
    filename = f"ai-weekly-{week_start}.md"
    return Response(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
