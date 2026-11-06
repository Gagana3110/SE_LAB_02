"""Rate limiting (DFS-SR-006) and security headers, applied to every request."""

import math
import threading
import time
from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import security
from app.auth.deps import SESSION_COOKIE
from app.config import settings

WINDOW_SECONDS = 60
LOGIN_PATH = "/api/auth/login"
UNLIMITED_PATHS = {"/health", "/api/health"}
# Swagger UI loads its scripts from a CDN, so the strict API policy would break it.
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"


class SlidingWindowLimiter:
    """Allows at most `limit` hits per key in any `window`-second period. Kept in memory, so the
    limit applies per API process; that is enough for the single process this app runs."""

    def __init__(self, window: float = WINDOW_SECONDS, clock=time.monotonic):
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> float:
        """Records a hit and returns 0 when allowed, or the seconds to wait when over the limit."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= limit:
                return hits[0] + self.window - now
            hits.append(now)
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def prune(self) -> None:
        """Drops keys with no recent hits, so memory does not grow with every visitor."""
        now = self.clock()
        with self._lock:
            for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                del self._hits[key]


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    # Only nginx sets X-Real-IP; trust it only when the API is reachable through nginx alone.
    if settings.trust_proxy_headers and request.headers.get("x-real-ip"):
        return request.headers["x-real-ip"]
    return request.client.host if request.client else "unknown"


def _rate_key(request: Request) -> tuple[str, int] | None:
    path = request.url.path
    if path in UNLIMITED_PATHS or not path.startswith("/api/"):
        return None
    if path == LOGIN_PATH and request.method == "POST":
        return f"login:{client_ip(request)}", settings.login_rate_per_minute
    token = request.cookies.get(SESSION_COOKIE)
    user_id = security.read_token(token) if token else None
    who = f"user:{user_id}" if user_id is not None else f"ip:{client_ip(request)}"
    return f"api:{who}", settings.api_rate_per_minute


def _too_many(request: Request, wait: float) -> JSONResponse:
    body = {
        "error": {"code": 429, "message": "Too many requests. Please wait and try again."},
        "requestId": getattr(request.state, "request_id", None),
    }
    return JSONResponse(status_code=429, content=body,
                        headers={"Retry-After": str(max(1, math.ceil(wait)))})


def _add_headers(request: Request, response) -> None:
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not request.url.path.startswith(DOCS_PATHS):
        response.headers.setdefault("Content-Security-Policy", API_CSP)
    if settings.cookie_secure:  # only meaningful when the site is served over HTTPS
        response.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")


def register_hardening(app: FastAPI) -> None:
    @app.middleware("http")
    async def rate_limit_and_headers(request: Request, call_next):
        rule = _rate_key(request)
        wait = limiter.hit(*rule) if rule else 0.0
        response = _too_many(request, wait) if wait else await call_next(request)
        _add_headers(request, response)
        if rule and len(limiter._hits) > 10_000:
            limiter.prune()
        return response
