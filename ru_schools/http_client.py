# -*- coding: utf-8 -*-
"""HTTP-клиент с вежливым троттлингом и экспоненциальными повторами.

Все источники в этом проекте — публичные государственные сервисы, поэтому
клиент намеренно медленный: ограничение частоты запросов и честный User-Agent.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

_RETRY_CODES = (403, 405, 429, 500, 502, 503, 504)

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# В песочнице исходящий HTTPS идёт через прокси с собственным CA.
_CA_BUNDLE = "/root/.ccr/ca-bundle.crt"


class RateLimiter:
    """Не более одного запроса раз в `interval` секунд на весь процесс."""

    def __init__(self, interval: float):
        self.interval = interval
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                delay = self._next_at - now
            else:
                delay = 0.0
            self._next_at = max(now, self._next_at) + self.interval
        if delay > 0:
            time.sleep(delay)


class HttpClient:
    def __init__(
        self,
        rate: float = 1.0,
        timeout: int = 60,
        retries: int = 5,
        user_agent: str = DEFAULT_UA,
        verify: Optional[str] = None,
    ):
        """rate — запросов в секунду (на процесс)."""
        self.limiter = RateLimiter(1.0 / rate if rate > 0 else 0.0)
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        # Прокси песочницы принимает только CONNECT (HTTPS); переменная
        # HTTP_PROXY заставила бы requests слать обычный HTTP-запрос → 405.
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if https_proxy:
            self.session.trust_env = False
            self.session.proxies = {"https": https_proxy}
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        )
        if verify is None and os.path.exists(_CA_BUNDLE):
            verify = _CA_BUNDLE
        self.verify = verify if verify else True

    def request(self, method: str, url: str, **kw) -> requests.Response:
        last_exc = None
        for attempt in range(self.retries):
            self.limiter.wait()
            try:
                resp = self.session.request(
                    method, url, timeout=self.timeout, verify=self.verify, **kw
                )
            except requests.RequestException as exc:  # сеть/таймаут
                last_exc = exc
                self._backoff(attempt, f"{type(exc).__name__} {url}")
                continue

            if resp.status_code in _RETRY_CODES:
                last_exc = RuntimeError(f"HTTP {resp.status_code} {url}")
                # 403/405/429 у ЕГРЮЛ означают троттлинг, а не ошибку запроса,
                # поэтому ждём дольше обычного.
                slow = resp.status_code in (403, 405, 429)
                self._backoff(attempt, f"HTTP {resp.status_code} {url}", slow=slow)
                continue
            return resp

        raise RuntimeError(f"не удалось выполнить запрос {url}: {last_exc}")

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self.request("POST", url, **kw)

    @staticmethod
    def _backoff(attempt: int, why: str, slow: bool = False) -> None:
        base = 5 * (attempt + 1) if slow else 2 ** attempt
        delay = min(base, 60) + random.uniform(0, 1.5)
        log.debug("повтор через %.1f с (%s)", delay, why)
        time.sleep(delay)
