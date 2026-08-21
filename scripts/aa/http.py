"""Robust HTTP fetching, caching, atomic writes, retries (stdlib only).

Central helpers shared by every AA source adaptor so behaviour is consistent:
bounded responses, no-credential-redirect, retries with backoff, respectful
rate limiting, disk caching, and atomic JSON writes.
"""

from __future__ import annotations

import json
import logging
import os
import time
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

log = logging.getLogger("aa.pipeline")

MAX_RESPONSE_BYTES = 60 * 1024 * 1024  # 60 MB hard cap (RSC payload is ~2.5 MB)


class _NoRedirectHandler(HTTPRedirectHandler):
    """Fail closed instead of forwarding credentials across redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class FetchResult:
    """Bounded, header-captured HTTP response."""

    status: int
    body: bytes
    url: str
    headers: dict = field(default_factory=dict)
    retries: int = 0  # number of retries actually performed (0 = first try)


def build_request(url: str, headers: dict | None = None, data=None) -> Request:
    hdrs = {"User-Agent": DEFAULT_UA}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    if data is not None and isinstance(data, str):
        data = data.encode("utf-8")
    return Request(url, headers=hdrs, data=data)


def _read_limited(resp, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    chunks, total = [], 0
    while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise RuntimeError(f"Upstream response exceeded {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_bytes(
    url: str,
    headers: dict | None = None,
    data=None,
    *,
    timeout: int = 90,
    retries: int = 3,
    backoff_base: float = 2.0,
    error_http_codes: frozenset[int] = frozenset({400, 401, 403, 404, 410}),
) -> FetchResult:
    """GET/POST with retries/backoff.

    - Retries on 5xx, 429 (honouring Retry-After / our own delay), and
      transient URLError.
    - Does NOT retry on 4xx auth/not-found codes (caller decides those).
    - Raises ``RuntimeError`` for bounded read overflow.
    Returns a :class:`FetchResult` on success.
    """
    attempt = 0
    while True:
        req = build_request(url, headers=headers, data=data)
        try:
            with build_opener(_NoRedirectHandler).open(req, timeout=timeout) as r:
                hdrs = {k: r.headers.get(k) for k in
                        ("x-aa-tier", "x-ratelimit-limit", "x-ratelimit-remaining",
                         "x-ratelimit-reset", "retry-after", "content-type")
                        if r.headers.get(k) is not None}
                body = _read_limited(r)
                return FetchResult(status=r.status, body=body, url=url,
                                   headers=hdrs, retries=attempt)
        except HTTPError as e:
            status = e.code
            msg = e.read(1024).decode("utf-8", errors="replace")
            if status in error_http_codes or status < 500:
                # Deterministic failure; caller decides fallback/policy.
                log.error("HTTP %s from %s: %s", status, url, msg[:300])
                raise RuntimeError(f"HTTP {status} from {url}") from e
            # 5xx / 429 retriable
            retry_after = None
            raw_ra = e.headers.get("Retry-After")
            try:
                if raw_ra is not None:
                    retry_after = float(raw_ra)
            except (TypeError, ValueError):
                retry_after = None
            delay = retry_after if retry_after is not None else \
                backoff_base ** attempt
            if attempt >= retries:
                raise RuntimeError(f"HTTP {status} from {url} after {attempt} retries")
            log.warning("Retryable HTTP %s from %s (retry %d, sleeping %.1fs)",
                        status, url, attempt + 1, delay)
            time.sleep(min(delay, 60))
            attempt += 1
        except URLError as e:
            if attempt >= retries:
                raise RuntimeError(f"Unreachable {url}: {e.reason}") from e
            delay = min(backoff_base ** attempt, 60)
            log.warning("Transient network error fetching %s (retry %d, sleep %.1fs)",
                        url, attempt + 1, delay)
            time.sleep(delay)
            attempt += 1


def fetch_json(url: str, headers: dict | None = None, **kw) -> tuple[dict, FetchResult]:
    res = fetch_bytes(url, headers=headers, **kw)
    try:
        payload = json.loads(res.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Invalid JSON from {url}") from e
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON payload from {url} is not an object")
    return payload, res


def atomic_write_json(path: Path, obj) -> None:
    """Write ``obj`` to ``path`` atomically (temp file + os.replace + fsync)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            json.dump(obj, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def disk_cache_key(url: str) -> str:
    import hashlib
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]