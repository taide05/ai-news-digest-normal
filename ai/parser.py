import json
import re
import logging

logger = logging.getLogger(__name__)

# ── CJK detection ──────────────────────────────────────────────────────────
_CJK_BLOCK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]{4,}")

# ── Partial-field regexes for truncated JSON recovery ──────────────────────
_PARTIAL_STR_FIELD_RE = re.compile(
    r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL
)
_PARTIAL_ARRAY_FIELD_RE = re.compile(
    r'"(\w+)"\s*:\s*\[(.*?)\]', re.DOTALL
)
_PARTIAL_NUM_FIELD_RE = re.compile(
    r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)'
)

# Fields worth recovering from truncated analysis responses
_RECOVERABLE_STR_FIELDS = {
    "core_insight", "what_it_means", "translation", "definition",
    "summary", "tldr", "reason", "term",
}
_RECOVERABLE_ARR_FIELDS = {"concepts", "key_takeaways", "topics"}
_RECOVERABLE_NUM_FIELDS = {"novelty", "confidence", "relevance"}


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

    # Layer 4: Partial-field extraction from truncated JSON
    result = _extract_partial_fields(raw)
    if result is not None:
        result["_partial"] = True
        return result

    # Layer 5: CJK refusal-text stripping + retry from Layer 1
    stripped = _strip_non_latin_tail(raw)
    if stripped != raw and len(stripped) > 20:
        return parse_json_response(stripped)

    logger.warning(f"parse_json_response: all 5 layers failed for {len(raw)} chars")
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


def _extract_partial_fields(raw: str) -> dict | None:
    """Extract complete fields from truncated JSON using regex.

    When max_tokens cuts off the response mid-JSON, some fields may still
    be intact.  This recovers them without needing balanced braces.
    """
    result = {}
    found_any = False

    for m in _PARTIAL_STR_FIELD_RE.finditer(raw):
        key = m.group(1)
        if key in _RECOVERABLE_STR_FIELDS:
            val = m.group(2)
            if len(val) > 3:
                result[key] = val
                found_any = True

    for m in _PARTIAL_ARRAY_FIELD_RE.finditer(raw):
        key = m.group(1)
        if key in _RECOVERABLE_ARR_FIELDS:
            inner = m.group(2).strip()
            if inner:
                items = [it.strip().strip('"').strip("'") for it in inner.split(",")]
                items = [it for it in items if it]
                if items:
                    result[key] = items
                    found_any = True

    for m in _PARTIAL_NUM_FIELD_RE.finditer(raw):
        key = m.group(1)
        if key in _RECOVERABLE_NUM_FIELDS:
            try:
                result[key] = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
                found_any = True
            except (ValueError, OverflowError):
                pass

    return result if found_any else None


def _strip_non_latin_tail(raw: str) -> str:
    """Truncate at the point where CJK refusal text takes over.

    When a cheap multilingual model switches mid-response to Chinese refusal
    text, this finds the earliest run where >30% of the remaining characters
    are CJK and truncates there.
    """
    if len(raw) < 100:
        return raw

    best = len(raw)
    for m in _CJK_BLOCK_RE.finditer(raw):
        start = m.start()
        # Check ratio of CJK chars in the tail from this point
        tail = raw[start:]
        cjk_count = len(_CJK_BLOCK_RE.findall(tail))
        cjk_chars = sum(len(x) for x in _CJK_BLOCK_RE.findall(tail))
        total_chars = len(tail)
        # Include spaces/punctuation as non-CJK; flag if >30% CJK
        if total_chars > 0 and cjk_chars / total_chars > 0.3:
            best = min(best, start)

    return raw[:best].rstrip().rstrip(",") if best < len(raw) else raw
