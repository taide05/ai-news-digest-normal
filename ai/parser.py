import json
import re
import logging

logger = logging.getLogger(__name__)


def parse_json_response(raw: str) -> dict:
    if not raw or not raw.strip():
        return {"_partial": True, "_error": "empty response"}

    raw = raw.strip()

    # Layer 1: Direct JSON parse
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass

    # Layer 2: Extract from ```json code fences
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Layer 3: Brace matching + partial field recovery
    result = _brace_match_recover(raw)
    if result is not None:
        result["_partial"] = True
        return result

    logger.warning(f"parse_json_response: all 3 layers failed for {len(raw)} chars")
    return {"_partial": True, "_error": "parse_failed", "_raw": raw[:500]}


def _brace_match_recover(raw: str) -> dict | None:
    start = raw.find('{')
    if start == -1:
        return None
    depth = 0
    end = -1
    for i in range(start, len(raw)):
        if raw[i] == '{':
            depth += 1
        elif raw[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return _regex_field_recovery(raw)
    candidate = raw[start:end]
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return _regex_field_recovery(raw)


def _regex_field_recovery(raw: str) -> dict | None:
    pattern = r'"(\w+)"\s*:\s*"([^"]*)"'
    matches = re.findall(pattern, raw)
    if not matches:
        return None
    result = {}
    for key, value in matches:
        result[key] = value
    return result
