# -*- coding: utf-8 -*-
"""Клиент открытого сервиса ЕГРЮЛ ФНС России (https://egrul.nalog.ru).

Сервис публичный и бесплатный: поиск по реестру и выписка из ЕГРЮЛ в PDF
предоставляются без регистрации (ст. 6 ФЗ-129 — сведения ЕГРЮЛ открыты
и общедоступны).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from .http_client import HttpClient

log = logging.getLogger(__name__)

BASE = "https://egrul.nalog.ru"

# Поисковые запросы, покрывающие организационные формы школ.
SCHOOL_QUERIES = [
    "СРЕДНЯЯ ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА",
    "ОСНОВНАЯ ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА",
    "НАЧАЛЬНАЯ ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА",
    "ОБЩЕОБРАЗОВАТЕЛЬНАЯ ШКОЛА",
    "СРЕДНЯЯ ШКОЛА",
    "ОБЩЕОБРАЗОВАТЕЛЬНАЯ ОРГАНИЗАЦИЯ",
    "ГИМНАЗИЯ",
    "ЛИЦЕЙ",
    "ШКОЛА-ИНТЕРНАТ",
    "КАДЕТСКАЯ ШКОЛА",
    "КАДЕТСКИЙ КОРПУС",
    "ВЕЧЕРНЯЯ ШКОЛА",
    "ШКОЛА",
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
    def __init__(self, http: HttpClient):
        self.http = http
        self._primed = False
        # После сброса сессии клиентом нужно заново получить cookie.
        http.on_throttle = self._invalidate

    def _invalidate(self) -> None:
        self._primed = False

    def _prime(self) -> None:
        """Получить сессионные cookie перед первым запросом."""
        if not self._primed:
            self._primed = True
            self.http.get(f"{BASE}/index.html", allow_redirects=True)

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
        for attempt in range(attempts):
            try:
                return self._vypiska_once(token)
            except CaptchaRequired:
                raise
            except RuntimeError as exc:
                last = exc
                time.sleep(2.0 * (attempt + 1))
                if inn:
                    rows = self.search_page(inn)
                    if rows and rows[0].token:
                        token = rows[0].token
        raise RuntimeError(f"выписка недоступна: {last}")

    def _vypiska_once(self, token: str) -> bytes:
        self._prime()
        r = self.http.get(
            f"{BASE}/vyp-request/{token}",
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/index.html"},
        )
        payload = _json_or_none(r)
        if not payload or "t" not in payload:
            raise RuntimeError(f"выписка не заказана: {r.status_code}")
        if payload.get("captchaRequired"):
            raise CaptchaRequired("ФНС запросила капчу при заказе выписки")
        vt = payload["t"]

        for _ in range(20):
            s = self.http.get(
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

        d = self.http.get(f"{BASE}/vyp-download/{vt}")
        if d.status_code != 200 or not d.content.startswith(b"%PDF"):
            raise RuntimeError(f"скачивание выписки не удалось: {d.status_code}")
        return d.content


class CaptchaRequired(RuntimeError):
    pass


def _json_or_none(resp) -> Optional[Dict]:
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError):
        return None
