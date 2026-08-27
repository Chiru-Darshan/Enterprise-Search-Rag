"""URL normalization and scope checks (FR-02: duplicate avoidance)."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urldefrag, urljoin, urlsplit, urlunsplit

TRACKING_PARAMS = re.compile(
    r"^(utm_[a-z_]+|gclid|gclsrc|dclid|fbclid|msclkid|mc_[a-z]+|_hs[a-z]*|igshid|"
    r"ref|ref_src|source|gtm_latency)$",
    re.I,
)
DEFAULT_PORTS = {"http": "80", "https": "443"}


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Return a canonical absolute http(s) URL, or None if not crawlable."""
    if not url:
        return None
    url = url.strip()
    if url.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    host = parts.hostname or ""
    port = parts.port
    netloc = host
    if port and str(port) != DEFAULT_PORTS.get(parts.scheme):
        netloc = f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if path.endswith(("/index.html", "/index.htm", "/index.php")):
        path = path.rsplit("/", 1)[0] + "/"

    query = "&".join(
        f"{k}={v}"
        for k, v in sorted(parse_qsl(parts.query, keep_blank_values=True))
        if not TRACKING_PARAMS.match(k)
    )
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def registrable_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def in_allowed_domains(url: str, allowed: list[str]) -> bool:
    host = registrable_host(url)
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed)


def path_extension(url: str) -> str:
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    slash = path.rfind("/")
    return path[dot:] if dot > slash else ""
