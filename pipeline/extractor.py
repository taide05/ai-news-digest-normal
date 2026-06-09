import logging
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from readability import Document

logger = logging.getLogger(__name__)

# Reserved/private IP blocks to reject
_BLOCKED_IP_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.IPv4Network("0.0.0.0/8"),       # current network
    ipaddress.IPv4Network("10.0.0.0/8"),       # private
    ipaddress.IPv4Network("100.64.0.0/10"),    # CGNAT
    ipaddress.IPv4Network("127.0.0.0/8"),      # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),   # link-local
    ipaddress.IPv4Network("172.16.0.0/12"),    # private
    ipaddress.IPv4Network("192.0.0.0/29"),     # DS-Lite
    ipaddress.IPv4Network("192.0.2.0/24"),     # TEST-NET-1
    ipaddress.IPv4Network("192.88.99.0/24"),   # 6to4 relay
    ipaddress.IPv4Network("192.168.0.0/16"),   # private
    ipaddress.IPv4Network("198.18.0.0/15"),    # benchmark
    ipaddress.IPv4Network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.IPv4Network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.IPv4Network("224.0.0.0/4"),      # multicast
    ipaddress.IPv4Network("240.0.0.0/4"),      # reserved
    ipaddress.IPv6Network("::1/128"),          # loopback
    ipaddress.IPv6Network("::/128"),           # unspecified
    ipaddress.IPv6Network("fc00::/7"),         # unique local
    ipaddress.IPv6Network("fe80::/10"),        # link-local
    ipaddress.IPv6Network("ff00::/8"),         # multicast
]


def _is_safe_url(url: str) -> bool:
    """Return False for URLs targeting internal/private networks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # hostname, not IP — resolve it
        try:
            resolved = socket.getaddrinfo(hostname, None, 0, socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        for info in resolved:
            addr = ipaddress.ip_address(info[4][0])
            if any(addr in net for net in _BLOCKED_IP_RANGES):
                return False
        return True
    return not any(addr in net for net in _BLOCKED_IP_RANGES)


_MAX_REDIRECTS = 5

_COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def _fetch_with_safe_redirects(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Manually follow redirects with URL validation on every hop."""
    target = url
    for _ in range(_MAX_REDIRECTS):
        if not _is_safe_url(target):
            logger.warning(f"Blocked unsafe redirect target: {target}")
            raise httpx.InvalidURL(f"Blocked unsafe URL: {target}")
        resp = await client.get(target, headers=_COMMON_HEADERS)
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        location = resp.headers.get("Location")
        if not location:
            return resp
        from urllib.parse import urljoin
        target = urljoin(target, location)
    raise httpx.TooManyRedirects(f"Too many redirects from {url}")


async def extract_full_text(url: str, timeout: int = 15) -> str:
    if not _is_safe_url(url):
        logger.warning(f"Blocked unsafe URL: {url}")
        return "[原文无法访问]"

    try:
        async with httpx.AsyncClient(timeout=float(timeout)) as client:
            resp = await _fetch_with_safe_redirects(client, url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 403, 410):
            logger.warning(f"URL returned {e.response.status_code}: {url}")
            return "[原文无法访问]"
        raise
    except (httpx.TimeoutException, httpx.TooManyRedirects):
        logger.warning(f"Timeout fetching: {url}")
        return "[原文加载超时]"
    except httpx.HTTPError as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
        return "[原文无法访问]"

    try:
        doc = Document(html)
        text = doc.summary()
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = ' '.join(text.split())

        if len(text) < 200:
            return "[正文提取失败，请查看原网页]"
        return text
    except Exception as e:
        logger.warning(f"Readability extraction failed for {url}: {e}")
        return "[正文提取失败，请查看原网页]"
