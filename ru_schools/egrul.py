# -*- coding: utf-8 -*-
"""Клиент открытого сервиса ЕГРЮЛ ФНС России (https://egrul.nalog.ru).

Сервис публичный и бесплатный: поиск по реестру и выписка из ЕГРЮЛ в PDF
предоставляются без регистрации (ст. 6 ФЗ-129 — сведения ЕГРЮЛ открыты
и общедоступны).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from .http_client import HttpClient

log = logging.getLogger(__name__)

BASE = "https://egrul.nalog.ru"

# Поисковые запросы, покрывающие организационные формы школ.
# Поиск ЕГРЮЛ ищет вхождение подстроки, поэтому «ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА»
# сама по себе покрывает среднюю, основную и начальную школу — отдельные
# запросы на них только увеличили бы число обращений к сервису.
SCHOOL_QUERIES = [
    "ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА",
    "СРЕДНЯЯ ШКОЛА",
    "ГИМНАЗИЯ",
    "ЛИЦЕЙ",
    "ШКОЛА-ИНТЕРНАТ",
    "КАДЕТСКАЯ ШКОЛА",
    "КАДЕТСКИЙ КОРПУС",
    "ВЕЧЕРНЯЯ ШКОЛА",
]


@dataclass
class EgrulRow:
    """Строка результата поиска ЕГРЮЛ."""

    inn: str
    kpp: str
    ogrn: str
    name_short: str
    name_full: str
    head_raw: str
    region_name: str
    reg_date: str
    terminated_date: str
    token: str
    found_by: str = ""
    region_code: str = ""

    @property
    def is_active(self) -> bool:
        """Открытая (действующая) организация — без даты прекращения."""
        return not self.terminated_date

    @property
    def head_post(self) -> str:
        return _split_head(self.head_raw)[0]

    @property
    def head_name(self) -> str:
        return _split_head(self.head_raw)[1]

    @classmethod
    def from_json(cls, row: Dict) -> "EgrulRow":
        return cls(
            inn=(row.get("i") or "").strip(),
            kpp=(row.get("p") or "").strip(),
            ogrn=(row.get("o") or "").strip(),
            name_short=(row.get("c") or "").strip(),
            name_full=(row.get("n") or "").strip(),
            head_raw=(row.get("g") or "").strip(),
            region_name=(row.get("rn") or "").strip(),
            reg_date=(row.get("r") or "").strip(),
            terminated_date=(row.get("e") or "").strip(),
            token=(row.get("t") or "").strip(),
        )


def _split_head(raw: str) -> tuple:
    """'ДИРЕКТОР: Иванов Иван Иванович' -> ('Директор', 'Иванов Иван Иванович')."""
    if not raw:
        return "", ""
    if ":" in raw:
        post, name = raw.split(":", 1)
        post, name = post.strip(), name.strip()
    else:
        post, name = "", raw.strip()
    if post.isupper():
        post = post.capitalize()
    return post, name


class EgrulClient:
    def __init__(self, http: HttpClient, vyp_http: Optional[HttpClient] = None):
        """`vyp_http` — отдельный клиент для выписок.

        Жёстко ограничен именно поисковый POST; загрузка выписки идёт
        обычными GET-запросами и допускает более высокую частоту.
        """
        self.http = http
        self.vyp = vyp_http or http
        self._primed = False
        # Праймингом занимается ровно один поток: остальные ждут его,
        # иначе уходят в запрос по ещё не полученной cookie.
        self._prime_lock = threading.Lock()
        # После сброса сессии клиентом нужно заново получить cookie.
        http.on_throttle = self._invalidate
        if self.vyp is not http:
            self.vyp.on_throttle = self._invalidate

    def _invalidate(self) -> None:
        """После сброса сессии сразу берём новую cookie, а не ждём следующего
        обращения: повторная попытка уходит уже по свежему соединению."""
        self._primed = False
        try:
            self._prime()
        except Exception:  # источник сейчас недоступен — разберёмся выше
            self._primed = False

    def _prime(self) -> None:
        """Получить сессионные cookie перед первым запросом.

        Клиент выписок — отдельная сессия, и cookie ему нужна своя: без неё
        ФНС отвечает на запрос выписки страницей «сервис недоступен».
        """
        with self._prime_lock:
            if self._primed:
                return
            self.http.get(f"{BASE}/index.html", allow_redirects=True)
            if self.vyp is not self.http:
                self.vyp.get(f"{BASE}/index.html", allow_redirects=True)
            self._primed = True

    def search_page(self, query: str, region: str = "", page: int = 1) -> List[EgrulRow]:
        """Одна страница результатов поиска (до 20 записей)."""
        self._prime()
        data = {
            "vyp3CaptchaToken": "",
            "page": "" if page <= 1 else str(page),
            "query": query,
            "region": region,
            "PreventChromeAutocomplete": "",
        }
        resp = self.http.post(
            f"{BASE}/",
            data=data,
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/index.html"},
            # Переход по редиректу превращает POST в запрос статики → 405.
            allow_redirects=False,
        )
        payload = _json_or_none(resp)
        if not payload or "t" not in payload:
            raise RuntimeError(f"поиск не принят сервисом: {resp.status_code} {resp.text[:120]}")
        if payload.get("captchaRequired"):
            raise CaptchaRequired("ФНС запросила капчу — снизьте частоту запросов")

        token = payload["t"]
        # Результат готовится асинхронно: опрашиваем до готовности.
        for _ in range(12):
            r = self.http.get(
                f"{BASE}/search-result/{token}",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            res = _json_or_none(r)
            if res is None:
                time.sleep(1.0)
                continue
            if "rows" in res:
                return [EgrulRow.from_json(x) for x in res["rows"]]
            if res.get("status") == "wait":
                time.sleep(1.0)
                continue
            if res.get("captchaRequired"):
                raise CaptchaRequired("ФНС запросила капчу на выдаче результата")
            time.sleep(1.0)
        raise RuntimeError("сервис ЕГРЮЛ не отдал результат поиска")

    def search(
        self, query: str, region: str = "", max_pages: int = 250
    ) -> Iterator[EgrulRow]:
        """Постранично обходит выдачу, пока не кончатся записи."""
        seen = set()
        page = 1
        while page <= max_pages:
            try:
                rows = self.search_page(query, region, page)
            except CaptchaRequired:
                raise
            except RuntimeError as exc:
                if page == 1:
                    # Ничего не собрали — этап нельзя считать выполненным.
                    raise
                log.warning("регион %s «%s» стр. %s: %s", region, query, page, exc)
                break
            if not rows:
                break
            fresh = 0
            for row in rows:
                if row.inn and row.inn not in seen:
                    seen.add(row.inn)
                    fresh += 1
                    row.found_by = query
                    row.region_code = region
                    yield row
            if fresh == 0:
                # Сервис зациклил выдачу — дальше нового не будет.
                break
            if len(rows) < 20:
                break
            page += 1

    def vypiska_pdf(self, token: str, inn: str = "", attempts: int = 3) -> bytes:
        """Выписка из ЕГРЮЛ в PDF.

        При отказе сервиса токен обновляется повторным поиском по ИНН:
        сохранённый токен со временем перестаёт приниматься.
        """
        last = None
        refreshed = False
        for attempt in range(attempts):
            try:
                return self._vypiska_once(token)
            except CaptchaRequired:
                raise
            except RuntimeError as exc:  # включая ServiceMaintenance
                last = exc
                # Сохранённый токен со временем протухает, и на просроченный
                # ФНС отвечает то пятисотой, то своей страницей «сервис
                # временно недоступен» — неотличимо от настоящих работ.
                # Поэтому сначала обновляем токен и только потом верим отказу.
                if inn and not refreshed:
                    refreshed = True
                    try:
                        rows = self.search_page(inn)
                    except RuntimeError:
                        rows = []
                    if rows and rows[0].token:
                        token = rows[0].token
                        continue
                if isinstance(exc, ServiceMaintenance):
                    raise
                time.sleep(2.0 * (attempt + 1))
        raise RuntimeError(f"выписка недоступна: {last}")

    def _vypiska_once(self, token: str) -> bytes:
        self._prime()
        r = self.vyp.get(
            f"{BASE}/vyp-request/{token}",
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/index.html"},
        )
        payload = _json_or_none(r)
        if not payload or "t" not in payload:
            _check_maintenance(r)
            raise RuntimeError(f"выписка не заказана: {r.status_code}")
        if payload.get("captchaRequired"):
            raise CaptchaRequired("ФНС запросила капчу при заказе выписки")
        vt = payload["t"]

        for _ in range(20):
            s = self.vyp.get(
                f"{BASE}/vyp-status/{vt}",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            st = _json_or_none(s) or {}
            if st.get("status") == "ready":
                break
            if st.get("status") == "error":
                raise RuntimeError("ФНС вернула ошибку подготовки выписки")
            time.sleep(1.5)
        else:
            raise RuntimeError("выписка не подготовлена за отведённое время")

        d = self.vyp.get(f"{BASE}/vyp-download/{vt}")
        if d.status_code != 200 or not d.content.startswith(b"%PDF"):
            raise RuntimeError(f"скачивание выписки не удалось: {d.status_code}")
        return d.content


class CaptchaRequired(RuntimeError):
    pass


class ServiceMaintenance(RuntimeError):
    """Сервис ФНС закрыт на технологические работы (обычно ночью по МСК)."""


_MAINTENANCE_MARKERS = ("Технологические работы", "временно недоступен")


def _check_maintenance(resp) -> None:
    if not resp.headers.get("Content-Type", "").startswith("text/html"):
        return
    # Заголовок ответа не объявляет кодировку, поэтому resp.text пришёл бы
    # разобранным как latin-1 и кириллические маркеры не совпали бы ни разу.
    text = resp.content.decode("utf-8", errors="replace")
    if any(m in text for m in _MAINTENANCE_MARKERS):
        raise ServiceMaintenance("ФНС проводит технологические работы")


def _json_or_none(resp) -> Optional[Dict]:
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError):
        return None
