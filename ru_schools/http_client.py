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
    """Адаптивный троттлинг: один запрос раз в `interval` секунд на процесс.

    ЕГРЮЛ отвечает 405 при превышении лимита, поэтому интервал растёт при
    отказах. Расти ему есть куда, но недалеко: слишком осторожный лимитер
    сам становится узким местом и способен застопорить сбор на часы, уже
    после того как сервис давно отвечает нормально. Поэтому потолок низкий,
    а возврат к базовой скорости — быстрый.
    """

    def __init__(self, interval: float, max_interval: float = 20.0):
        self.base = interval
        self.interval = interval
        self.max_interval = max(max_interval, interval)
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._ok_streak = 0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.interval
        if delay > 0:
            time.sleep(delay)

    def penalize(self, factor: float = 2.0) -> None:
        with self._lock:
            self.interval = min(max(self.interval * factor, 2.0), self.max_interval)
            self._ok_streak = 0
            return self.interval

    def relax(self, every: int = 5, factor: float = 0.5) -> None:
        with self._lock:
            if self.interval <= self.base:
                return
            self._ok_streak += 1
            if self._ok_streak >= every:
                self._ok_streak = 0
                self.interval = max(self.base, self.interval * factor)


class HttpClient:
    def __init__(
        self,
        rate: float = 1.0,
        timeout: int = 60,
        retries: int = 5,
        user_agent: str = DEFAULT_UA,
        verify: Optional[str] = None,
        proxy: Optional[str] = None,
        limiter: Optional[RateLimiter] = None,
    ):
        """rate — запросов в секунду (на клиента).

        `proxy` — адрес вида http://логин:пароль@хост:порт. Задан — весь
        трафик клиента идёт через него, минуя настройки окружения.

        `limiter` позволяет нескольким клиентам делить один лимит частоты:
        сессии у них при этом разные, и сброс одной не задевает остальные.
        """
        self.limiter = limiter or RateLimiter(1.0 / rate if rate > 0 else 0.0)
        self._lock = threading.Lock()
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.proxy = proxy
        if proxy:
            self.session.trust_env = False
            self.session.proxies = {"http": proxy, "https": proxy}
        else:
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
        # Вызывается, когда сервис начал троттлить и сессия сброшена.
        self.on_throttle = None
        self._resetting = False

    def reset_session(self) -> None:
        """Начинает общение с источником заново после отказа по частоте.

        Сбрасываются и cookie, и пул соединений: свежая сессия с новым
        TCP-соединением получает ответ там, где переиспользованное
        соединение продолжает получать 405, даже когда пауза выдержана.
        """
        with self._lock:
            if self._resetting:
                return
            self._resetting = True
        try:
            self.session.cookies.clear()
            self.session.close()
            if self.on_throttle:
                self.on_throttle()
        finally:
            with self._lock:
                self._resetting = False

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
                if slow:
                    interval = self.limiter.penalize()
                    self.reset_session()
                    # Раньше это писалось в DEBUG, и сбор незаметно уползал
                    # в многоминутные паузы — теперь торможение видно в логе.
                    log.info(
                        "источник ограничил частоту (HTTP %s), интервал между "
                        "запросами теперь %.1f с",
                        resp.status_code, interval,
                    )
                self._backoff(attempt, f"HTTP {resp.status_code} {url}", slow=slow)
                continue
            self.limiter.relax()
            return resp

        raise RuntimeError(f"не удалось выполнить запрос {url}: {last_exc}")

    def get(self, url: str, **kw) -> requests.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        return self.request("POST", url, **kw)

    @staticmethod
    def _backoff(attempt: int, why: str, slow: bool = False) -> None:
        # Пауза после отказа по частоте должна быть заметной, но не такой,
        # чтобы один запрос съедал четверть часа.
        base = 20 * (attempt + 1) if slow else 2 ** attempt
        delay = min(base, 90) + random.uniform(0, 5)
        log.debug("повтор через %.1f с (%s)", delay, why)
        time.sleep(delay)
