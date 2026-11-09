"""HTTP fetching with a browser TLS fingerprint (curl_cffi), polite delays and block detection."""
from __future__ import annotations

import random
import time

try:  # curl_cffi mimics Chrome's TLS fingerprint -> blocked far less often
    from curl_cffi import requests as _req

    _HAS_CFFI = True
except ImportError:  # fallback, e.g. for local runs without curl_cffi
    import requests as _req  # type: ignore

    _HAS_CFFI = False

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_BLOCK_MARKERS = (
    "captcha",
    "access denied",
    "zugriff verweigert",
    "are you a robot",
    "bist du ein mensch",
    "unusual traffic",
    "request blocked",
)


class BlockedError(Exception):
    """The portal blocked the request (403/429/captcha)."""


class Fetcher:
    def __init__(self, delay: tuple[float, float] = (3, 7), timeout: int = 30):
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0
        if _HAS_CFFI:
            self.session = _req.Session(impersonate="chrome")
            self.headers = {"Accept-Language": "de-DE,de;q=0.9,en;q=0.6"}
        else:
            self.session = _req.Session()
            self.headers = {
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.6",
            }

    def _wait(self) -> None:
        if self._last:
            pause = random.uniform(*self.delay)
            remaining = pause - (time.time() - self._last)
            if remaining > 0:
                time.sleep(remaining)
        self._last = time.time()

    def fetch(self, url: str) -> tuple[int, str, str]:
        """Like get(), but returns (status, final_url, html) for 4xx instead of raising.
        Still raises BlockedError for 403/429/captcha so a block is never mistaken for 'gone'."""
        self._wait()
        r = self.session.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
        if r.status_code in (403, 429):
            raise BlockedError(f"HTTP {r.status_code} for {url}")
        if r.status_code >= 500:
            raise RuntimeError(f"HTTP {r.status_code} for {url}")
        html = r.text
        if r.status_code == 200 and len(html) < 20000 and any(m in html[:5000].lower() for m in _BLOCK_MARKERS):
            raise BlockedError(f"Captcha/block page for {url}")
        return r.status_code, str(r.url), html

    def get(self, url: str, retries: int = 1) -> str:
        last_exc: Exception | None = None
        for _ in range(retries + 1):
            self._wait()
            try:
                r = self.session.get(url, headers=self.headers, timeout=self.timeout)
            except Exception as exc:  # network error
                last_exc = exc
                continue
            if r.status_code in (403, 429):
                raise BlockedError(f"HTTP {r.status_code} for {url}")
            if r.status_code >= 500:
                last_exc = RuntimeError(f"HTTP {r.status_code} for {url}")
                continue
            r.raise_for_status()
            html = r.text
            head = html[:5000].lower()
            if len(html) < 20000 and any(m in head for m in _BLOCK_MARKERS):
                raise BlockedError(f"Captcha/block page for {url}")
            return html
        raise last_exc or RuntimeError(f"Request failed: {url}")
