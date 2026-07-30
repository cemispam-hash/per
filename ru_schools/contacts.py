# -*- coding: utf-8 -*-
"""Поиск e-mail и телефонов школ в открытых источниках.

ЕГРЮЛ контактов не содержит, поэтому используются отдельные открытые
источники. Провайдеры перебираются по очереди, первый непустой ответ
побеждает; недоступные источники просто пропускаются.

Источники:
  * bus.gov.ru — ГИС ГМУ, официальный реестр государственных и муниципальных
    учреждений (раздел «Открытые данные»). Основной и самый полный источник;
    в отдельных сетевых окружениях может быть недоступен.
  * OpenStreetMap (Overpass API) — открытые данные под лицензией ODbL.
  * официальный сайт школы — раздел «Сведения об образовательной организации»,
    публикация которого обязательна по ст. 29 ФЗ-273 и ПП РФ № 1802.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .http_client import HttpClient

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,10}")
PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3,5}\)?[\s\-]?\d{1,3}[\s\-]?\d{2}[\s\-]?\d{2}"
)
_JUNK_EMAIL = re.compile(
    r"(example|sentry|noreply|no-reply|yandex\.ru/support|@sentry|\.png|\.jpg|\.webp)", re.I
)


@dataclass
class Contact:
    email: str = ""
    phones: List[str] = field(default_factory=list)
    website: str = ""
    source: str = ""

    def __bool__(self) -> bool:
        return bool(self.email or self.phones or self.website)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        return ""
    return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


def extract_contacts(text: str) -> Contact:
    emails = [e for e in EMAIL_RE.findall(text) if not _JUNK_EMAIL.search(e)]
    phones = []
    for p in PHONE_RE.findall(text):
        norm = normalize_phone(p)
        if norm and norm not in phones:
            phones.append(norm)
    return Contact(email=emails[0] if emails else "", phones=phones[:5])


class BusGovProvider:
    """ГИС ГМУ (bus.gov.ru) — официальный реестр учреждений."""

    name = "bus.gov.ru"
    SEARCH = "https://bus.gov.ru/public-rest/api/agency"

    def __init__(self, http: HttpClient):
        self.http = http

    def fetch(self, inn: str, **_) -> Optional[Contact]:
        resp = self.http.get(
            self.SEARCH,
            params={"inn": inn, "page": 1, "pageSize": 10},
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        items = data.get("agencies") or data.get("content") or data.get("result") or []
        if isinstance(items, dict):
            items = items.get("content", [])
        for it in items:
            if str(it.get("inn", "")).strip() != inn:
                continue
            phones = []
            for key in ("telephone", "phone", "phones", "contactPhone"):
                val = it.get(key)
                if isinstance(val, str):
                    for p in PHONE_RE.findall(val):
                        norm = normalize_phone(p)
                        if norm and norm not in phones:
                            phones.append(norm)
            email = ""
            for key in ("email", "eMail", "contactEmail"):
                if it.get(key):
                    email = str(it[key]).strip()
                    break
            return Contact(email=email, phones=phones, website=str(it.get("site") or ""), source=self.name)
        return None


class SabyProvider:
    """Публичная карточка контрагента saby.ru (ex-СБИС)."""

    name = "saby.ru"

    def __init__(self, http: HttpClient):
        self.http = http

    def fetch(self, inn: str, kpp: str = "", **_) -> Optional[Contact]:
        url = f"https://sbis.ru/contragents/{inn}/{kpp}" if kpp else f"https://sbis.ru/contragents/{inn}"
        resp = self.http.get(url)
        if resp.status_code != 200:
            return None
        html = resp.text
        site = ""
        m = re.search(r'href="(https?://(?!(?:sbis|saby|tensor)\.)[^"]+)"[^>]*>\s*(?:сайт|www)', html, re.I)
        if m:
            site = m.group(1)
        # Контакты в карточке размечены ссылками tel: / mailto:.
        emails = re.findall(r'mailto:([^"\'<>?]+)', html)
        phones = []
        for raw in re.findall(r'tel:([+\d\s\-()]+)', html):
            norm = normalize_phone(raw)
            if norm and norm not in phones:
                phones.append(norm)
        emails = [e for e in emails if not _JUNK_EMAIL.search(e)]
        c = Contact(email=emails[0] if emails else "", phones=phones[:5], website=site, source=self.name)
        return c if c else None


class OsmProvider:
    """OpenStreetMap через Overpass API (лицензия ODbL)."""

    name = "openstreetmap"
    OVERPASS = "https://overpass-api.de/api/interpreter"

    def __init__(self, http: HttpClient):
        self.http = http

    def fetch(self, inn: str, **_) -> Optional[Contact]:
        query = (
            f'[out:json][timeout:40];nwr["ref:INN"="{inn}"];out tags 3;'
        )
        resp = self.http.post(self.OVERPASS, data={"data": query})
        if resp.status_code != 200:
            return None
        try:
            elements = resp.json().get("elements", [])
        except ValueError:
            return None
        for el in elements:
            tags = el.get("tags", {})
            phones = []
            for key in ("contact:phone", "phone"):
                if tags.get(key):
                    for p in PHONE_RE.findall(tags[key]):
                        norm = normalize_phone(p)
                        if norm and norm not in phones:
                            phones.append(norm)
            c = Contact(
                email=tags.get("contact:email") or tags.get("email") or "",
                phones=phones,
                website=tags.get("contact:website") or tags.get("website") or "",
                source=self.name,
            )
            if c:
                return c
        return None


class WebsiteProvider:
    """Официальный сайт школы: раздел «Сведения об образовательной организации»."""

    name = "сайт школы"
    PAGES = ("/sveden/common", "/sveden/", "/contacts", "/kontakty", "/")

    def __init__(self, http: HttpClient):
        self.http = http

    def fetch(self, inn: str, website: str = "", **_) -> Optional[Contact]:
        if not website:
            return None
        base = website.rstrip("/")
        for path in self.PAGES:
            try:
                resp = self.http.get(base + path, allow_redirects=True)
            except RuntimeError:
                continue
            if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                continue
            c = extract_contacts(resp.text)
            if c.email or c.phones:
                c.website = base
                c.source = self.name
                return c
        return None


def build_providers(http: HttpClient, names: Optional[List[str]] = None) -> List:
    available = {
        "busgov": BusGovProvider,
        "saby": SabyProvider,
        "osm": OsmProvider,
        "site": WebsiteProvider,
    }
    names = names or ["busgov", "saby", "osm"]
    return [available[n](http) for n in names if n in available]


def collect(providers: List, inn: str, kpp: str = "", website: str = "") -> Contact:
    """Первый непустой ответ; недоступный источник молча пропускается.

    Если по дороге нашёлся адрес официального сайта, он дополнительно
    разбирается: раздел «Сведения об образовательной организации» школы
    обязателен к публикации и содержит телефон и e-mail.
    """
    merged = Contact()
    site_prov = next((p for p in providers if isinstance(p, WebsiteProvider)), None)
    for prov in providers:
        try:
            got = prov.fetch(inn=inn, kpp=kpp, website=website)
        except Exception as exc:  # источник недоступен — идём дальше
            log.debug("%s недоступен для ИНН %s: %s", prov.name, inn, exc)
            continue
        if not got:
            continue
        if not merged.email and got.email:
            merged.email, merged.source = got.email, got.source
        if not merged.phones and got.phones:
            merged.phones = got.phones
            merged.source = merged.source or got.source
        if not merged.website and got.website:
            merged.website = got.website
            merged.source = merged.source or got.source
        if merged.email and merged.phones:
            break

    if site_prov and merged.website and not (merged.email and merged.phones):
        try:
            got = site_prov.fetch(inn=inn, website=merged.website)
        except Exception:
            got = None
        if got:
            merged.email = merged.email or got.email
            merged.phones = merged.phones or got.phones
            merged.source = f"{merged.source}, {got.source}" if merged.source else got.source
    return merged
