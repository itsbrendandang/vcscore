"""Minimal stdlib HTTP fetch with a sane User-Agent and certifi CA bundle
(macOS system Python can't verify TLS via urllib otherwise). No third-party deps."""
from __future__ import annotations

import gzip
import ssl
import urllib.error
import urllib.request
import zlib

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover
    _SSL_CTX = ssl.create_default_context()

UA = "vcscore/0.1 (internal diligence tool)"


def fetch_text(url: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Return (ok, text). ok is False on any network/HTTP error."""
    if not url or not url.startswith(("http://", "https://")):
        return False, ""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            raw = r.read()
            enc = r.headers.get("Content-Encoding", "")
            if enc == "gzip":
                raw = gzip.decompress(raw)
            elif enc == "deflate":
                raw = zlib.decompress(raw)
            return True, raw.decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError):
        return False, ""
