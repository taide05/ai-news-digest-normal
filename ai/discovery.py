"""AI-powered source quality evaluation."""
import logging

logger = logging.getLogger("discovery")


async def evaluate_source_candidates(ai_client, urls: list[str]) -> list[dict]:
    """Evaluate candidate source URLs for quality and relevance."""
    if not urls or not ai_client:
        return []

    candidates = []
    for url in urls[:10]:
        try:
            sys_p = "你是一个信息源评估助手。评估一个URL是否适合作为AI资讯的长期信息来源。只返回JSON。"
            usr_p = (
                f"URL: {url}\n\n"
                f"判断这个来源是否：1.持续产出AI/技术内容 2.内容质量高 3.适合定期抓取\n\n"
                f'返回JSON：{{"title": "来源名称", "description": "一句话描述", "score": 0.0-1.0, "is_source": true/false}}'
            )
            result, _ = ai_client.chat(sys_p, usr_p, max_tokens=150)
            parsed = _parse_evaluation(result, url)
            if parsed and parsed.get("is_source", False):
                candidates.append(parsed)
        except Exception as e:
            logger.warning(f"Source evaluation failed for {url}: {e}")

    return candidates


def _parse_evaluation(result: str, url: str) -> dict | None:
    """Parse AI evaluation JSON response."""
    import json
    try:
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(result[start:end])
            data["url"] = url
            if "score" not in data:
                data["score"] = 0.5
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None
