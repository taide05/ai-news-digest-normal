from slowapi import Limiter
from fastapi import Request


def _rate_limit_key(request: Request) -> str:
    """Use X-Forwarded-For header when behind a reverse proxy, else client IP."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_rate_limit_key)
