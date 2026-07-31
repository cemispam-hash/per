# -*- coding: utf-8 -*-
"""Этапы сбора: поиск → выписки → численность → контакты → выгрузка."""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from typing import Iterable, List, Optional

from . import contacts as contacts_mod
from . import sshr
from .egrul import SCHOOL_QUERIES, CaptchaRequired, EgrulClient, ServiceMaintenance
from .http_client import HttpClient, RateLimiter
from .regions import ALL_REGION_CODES, region_name
from .store import Store
from .vypiska import parse_pdf

log = logging.getLogger(__name__)

# Столько ответов «сервис недоступен» подряд считаем настоящими
# технологическими работами, а не разовым отказом под нагрузкой.
MAINTENANCE_LIMIT = 15


class Budget:
    """Счётчик оставшихся запросов на заход; None — без ограничения."""

    def __init__(self, limit: Optional[int]):
        self.left = limit
        self._lock = threading.Lock()

    def take(self) -> bool:
        if self.left is None:
            return True
        with self._lock:
            if self.left <= 0:
                return False
            self.left -= 1
            return True


# Названия, по которым организация относится к общеобразовательным.
SCHOOL_NAME_RE = re.compile(
    r"(ОБЩЕОБРАЗОВАТЕЛЬН|ГИМНАЗИ|ЛИЦЕ[ЙЯ]|ШКОЛА|ШКОЛЫ|ШКОЛА-ИНТЕРНАТ|КАДЕТСК)", re.I
)
# Явно не общеобразовательные организации.
NOT_SCHOOL_RE = re.compile(
    r"(АВТОШКОЛА|АВТОМОБИЛЬНАЯ ШКОЛА|МУЗЫКАЛЬНАЯ ШКОЛА|ХУДОЖЕСТВЕННАЯ ШКОЛА"
    r"|СПОРТИВНАЯ ШКОЛА|ШКОЛА ИСКУССТВ|ДЕТСКО-ЮНОШЕСКАЯ|ДЮСШ|ДШИ|ВЫСШАЯ ШКОЛА"
    r"|ШКОЛА ТАНЦЕВ|ЯЗЫКОВАЯ ШКОЛА|ШКОЛА БИЗНЕСА|УЧЕБНЫЙ ЦЕНТР)",
    re.I,
)


def discover(
    store: Store,
    http: HttpClient,
    regions: Optional[List[str]] = None,
    queries: Optional[List[str]] = None,
    max_pages: int = 250,
    lanes: Optional[List] = None,
    max_queries: Optional[int] = None,
) -> int:
    """Этап 1. Поиск школ в ЕГРЮЛ по регионам и вариантам наименования.

    С несколькими каналами регионы разбираются параллельно: лимит частоты
    у ФНС считается по IP, поэтому каждый канал живёт своей жизнью.

    `max_queries` ограничивает объём одного захода, чтобы управление
    возвращалось наверх и следующие этапы тоже получали своё время.
    """
    budget = Budget(max_queries)
    regions = regions or ALL_REGION_CODES
    queries = queries or SCHOOL_QUERIES
    clients = [EgrulClient(lane.client) for lane in lanes] if lanes else [EgrulClient(http)]

    def one_region(idx_region) -> int:
        idx, reg = idx_region
        client = clients[idx % len(clients)]
        new_here = 0
        for q in queries:
            key = f"discover:{reg}:{q}"
            if store.get_progress(key) == "done":
                continue
            if not budget.take():
                break
            batch, found = [], 0
            try:
                for row in client.search(q, region=reg, max_pages=max_pages):
                    row.region_name = row.region_name or region_name(reg)
                    batch.append(row)
                    found += 1
                    if len(batch) >= 200:
                        new_here += store.add_orgs(batch)
                        batch = []
            except CaptchaRequired as exc:
                store.add_orgs(batch)
                log.error("капча ФНС: %s — пауза 120 с", exc)
                time.sleep(120)
                continue
            except Exception as exc:
                store.add_orgs(batch)
                store.add_failure("", f"discover:{reg}:{q}", str(exc))
                log.warning("регион %s «%s»: %s", reg, q, exc)
                continue

            new_here += store.add_orgs(batch)
            store.set_progress(key, "done")
            log.info(
                "регион %s (%s) «%s»: %s записей, всего в базе %s",
                reg, region_name(reg), q, found, store.count("orgs"),
            )
        return new_here

    tasks = list(enumerate(regions))
    if len(clients) == 1:
        return sum(one_region(t) for t in tasks)

    total_new = 0
    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        for got in pool.map(one_region, tasks):
            total_new += got
    return total_new


def _looks_like_school(name: str) -> bool:
    if not name:
        return False
    if NOT_SCHOOL_RE.search(name):
        return False
    return bool(SCHOOL_NAME_RE.search(name))


def fetch_details(
    store: Store,
    http: HttpClient,
    limit: Optional[int] = None,
    workers: int = 4,
    vyp_rate: float = 2.5,
    lanes: Optional[List] = None,
) -> int:
    """Этап 2. Официальная выписка из ЕГРЮЛ: адрес, ОКВЭД, руководитель.

    Выписки качаются отдельным клиентом: строгий лимит частоты у ФНС
    действует на поисковый POST, а не на загрузку выписки. При нескольких
    каналах загрузка раскладывается по ним поровну.
    """
    if lanes:
        clients = [
            EgrulClient(lane.client, vyp_http=HttpClient(rate=vyp_rate, proxy=lane.proxy))
            for lane in lanes
        ]
        workers = max(workers, len(clients))
    else:
        # По клиенту на поток: сессия у каждого своя, а лимит частоты общий.
        # С одной сессией на всех сброс после отказа выбивал cookie у соседа,
        # и тот получал от ФНС страницу «сервис недоступен».
        vyp_limiter = RateLimiter(1.0 / vyp_rate if vyp_rate > 0 else 0.0)
        clients = [
            EgrulClient(
                HttpClient(rate=0, limiter=http.limiter),
                vyp_http=HttpClient(rate=0, limiter=vyp_limiter),
            )
            for _ in range(max(1, workers))
        ]
    pending = store.pending_details(limit)
    if not pending:
        return 0
    log.info("выписок к загрузке: %s (каналов: %s)", len(pending), len(clients))
    done = 0

    def work(indexed):
        idx, row = indexed
        client = clients[idx % len(clients)]
        inn, token = row["inn"], row["token"]
        pdf = client.vypiska_pdf(token, inn=inn)
        v = parse_pdf(pdf)
        name = v.name_full or v.name_short
        is_school = v.is_general_school or (
            not v.okved_main and _looks_like_school(name)
        )
        if NOT_SCHOOL_RE.search(name or ""):
            is_school = False
        return inn, v, is_school

    maintenance = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(work, (i, r)): r["inn"] for i, r in enumerate(pending)
        }
        for fut in as_completed(futures):
            inn = futures[fut]
            try:
                inn, v, is_school = fut.result()
            except CancelledError:
                # Задача снята нами же при остановке этапа — это не отказ
                # по конкретной организации, отметку ставить нельзя.
                continue
            except ServiceMaintenance:
                # Разовый ответ «сервис недоступен» ещё не повод бросать
                # партию: этап останавливаем, только если недоступность
                # держится подряд и ни одна выписка между ними не прошла.
                maintenance += 1
                if maintenance >= MAINTENANCE_LIMIT:
                    log.warning(
                        "ЕГРЮЛ на технологических работах (%s отказов подряд) "
                        "— выписки временно недоступны, этап продолжится позже",
                        maintenance,
                    )
                    for pending_fut in futures:
                        pending_fut.cancel()
                continue
            except Exception as exc:
                store.add_failure(inn, "details", str(exc))
                continue
            maintenance = 0  # выписка прошла — недоступности нет
            store.add_details(inn, v, is_school)
            done += 1
            if done % 100 == 0:
                log.info("разобрано выписок: %s / %s", done, len(pending))
    return done


def fetch_staff(store: Store, http: HttpClient, zip_path: str) -> int:
    """Этап 3. Среднесписочная численность работников из открытых данных ФНС."""
    if not os.path.exists(zip_path):
        sshr.download(http, zip_path)
    wanted = set(store.all_inns())
    if not wanted:
        return 0
    log.info("сопоставляю численность по %s ИНН", len(wanted))
    found, period = [], ""
    for inn, count, per in sshr.iter_headcounts(zip_path):
        if inn in wanted:
            found.append((inn, count))
            period = period or per
    return store.add_staff(found, period, "ФНС, открытые данные (ССЧР)")


def fetch_contacts(
    store: Store,
    http: HttpClient,
    limit: Optional[int] = None,
    workers: int = 4,
    providers: Optional[List[str]] = None,
) -> int:
    """Этап 4. E-mail и телефоны из открытых источников."""
    provs = contacts_mod.build_providers(http, providers)
    if not provs:
        return 0
    pending = store.pending_contacts(limit)
    log.info("организаций без контактов: %s", len(pending))
    done = 0

    def work(row):
        c = contacts_mod.collect(provs, row["inn"], row["kpp"] or "")
        return row["inn"], c

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, r): r["inn"] for r in pending}
        for fut in as_completed(futures):
            inn = futures[fut]
            try:
                inn, c = fut.result()
            except Exception as exc:
                store.add_failure(inn, "contacts", str(exc))
                continue
            store.add_contacts(inn, c.email, c.phones, c.website, c.source)
            done += 1
            if done % 100 == 0:
                log.info("контакты: обработано %s / %s", done, len(pending))
    return done
