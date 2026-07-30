# -*- coding: utf-8 -*-
"""Пул каналов: несколько прокси — несколько независимых потоков сбора.

ФНС считает частоту запросов по IP, поэтому единственный способ ускорить
сбор, не долбя сервис с одного адреса, — развести запросы по разным
каналам. Каждый канал держит свою сессию (свои cookie) и свой адаптивный
лимит частоты, так что бан одного канала не тормозит остальные.

Список прокси берётся из файла (по строке на прокси) или из переменной
окружения RU_SCHOOLS_PROXIES (через запятую). Поддерживаются форматы:

    ip:port:логин:пароль
    ip:port
    http://логин:пароль@ip:port

Учётные данные — секрет: держите файл вне репозитория (data/proxies.txt
уже в .gitignore).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from .http_client import HttpClient

log = logging.getLogger(__name__)

DEFAULT_PROXY_FILE = "data/proxies.txt"
ENV_VAR = "RU_SCHOOLS_PROXIES"


def parse_proxy(raw: str) -> Optional[str]:
    """Приводит строку к виду http://логин:пароль@хост:порт."""
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    if "://" in raw:
        return raw
    parts = raw.split(":")
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    log.warning("не понял строку прокси: %s", raw[:40])
    return None


def load_proxies(path: Optional[str] = None) -> List[str]:
    out: List[str] = []
    env = os.environ.get(ENV_VAR, "")
    for chunk in env.split(","):
        proxy = parse_proxy(chunk)
        if proxy:
            out.append(proxy)

    path = path or DEFAULT_PROXY_FILE
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                proxy = parse_proxy(line)
                if proxy:
                    out.append(proxy)
    # Один и тот же прокси дважды — это не два канала.
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


@dataclass
class Lane:
    """Канал сбора: прокси плюс привязанный к нему HTTP-клиент."""

    name: str
    proxy: Optional[str]
    client: HttpClient


def _hide(proxy: Optional[str]) -> str:
    """Прокси без пароля — для логов."""
    if not proxy:
        return "прямое соединение"
    tail = proxy.rsplit("@", 1)[-1]
    return tail


def build_lanes(
    rate: float,
    proxies: Optional[List[str]] = None,
    include_direct: bool = True,
    timeout: int = 60,
) -> List[Lane]:
    """Каналы для сбора: по одному на прокси плюс, по желанию, прямой."""
    proxies = proxies if proxies is not None else load_proxies()
    lanes: List[Lane] = []
    if include_direct or not proxies:
        lanes.append(Lane("прямой", None, HttpClient(rate=rate, timeout=timeout)))
    for proxy in proxies:
        lanes.append(
            Lane(_hide(proxy), proxy, HttpClient(rate=rate, timeout=timeout, proxy=proxy))
        )
    log.info("каналов сбора: %s (%s)", len(lanes), ", ".join(l.name for l in lanes))
    return lanes


def check_lanes(
    lanes: List[Lane],
    url: str = "https://egrul.nalog.ru/index.html",
    timeout: int = 10,
) -> List[Lane]:
    """Отсеивает каналы, через которые источник недоступен.

    Проверка идёт мимо повторов клиента: мёртвый прокси должен отсеиваться
    за секунды, а не за минуту ожиданий с экспоненциальной паузой.
    """
    alive = []
    for lane in lanes:
        try:
            resp = lane.client.session.get(
                url, timeout=timeout, verify=lane.client.verify, allow_redirects=True
            )
            if resp.status_code < 500:
                alive.append(lane)
                continue
            log.warning("канал %s отвечает %s — исключён", lane.name, resp.status_code)
        except Exception as exc:
            log.warning("канал %s недоступен (%s) — исключён", lane.name, type(exc).__name__)
    if not alive:
        raise RuntimeError("ни один канал не отвечает — проверьте прокси и сеть")
    log.info("рабочих каналов: %s из %s", len(alive), len(lanes))
    return alive
