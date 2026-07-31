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
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from .http_client import HttpClient

log = logging.getLogger(__name__)

# Доступ к xmlriver: из переменных окружения или из файла вне репозитория.
XMLRIVER_FILE = "data/xmlriver.txt"


def xmlriver_credentials(path: str = XMLRIVER_FILE):
    """(user, key) для поиска — из окружения либо из файла «user:key»."""
    user = os.environ.get("XMLRIVER_USER", "")
    key = os.environ.get("XMLRIVER_KEY", "")
    if not (user and key) and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    user, key = line.split(":", 1)
                    user, key = user.strip(), key.strip()
                break
    return user, key


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,10}")
PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3,5}\)?[\s\-]?\d{1,3}[\s\-]?\d{2}[\s\-]?\d{2}"
)
_JUNK_EMAIL = re.compile(
    r"(example|sentry|noreply|no-reply|yandex\.ru/support|@sentry|\.png|\.jpg|\.webp"
    r"|\.js$|\.css$|\.svg$|\.min$|@\d+\.\d|@2x|domain\.|mail\.example|your@|@site\.)",
    re.I,
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


class XmlRiverProvider:
    """Поиск официального сайта школы и снятие контактов с него.

    ЕГРЮЛ контактов не содержит, зато школа обязана публиковать телефон и
    e-mail у себя на сайте (ст. 29 ФЗ-273, ПП РФ № 1802). Сайт ищется через
    xmlriver.com — прослойку к выдаче Яндекса и Google.
    """

    name = "сайт школы (поиск)"
    SEARCH = "https://xmlriver.com/search/xml"

    # Справочники и агрегаторы: контактов школы там либо нет, либо они
    # перепечатаны с ошибками — нужен именно сайт самой школы.
    AGGREGATORS = (
        "2gis.ru", "yandex.", "google.", "rusprofile.ru", "list-org.com",
        "checko.ru", "audit-it.ru", "rbc.ru", "tochka.com", "tbank.ru",
        "tinkoff.ru", "sbis.ru", "saby.ru", "zachestnyibiznes.ru", "zanad.ru",
        "orgs.biz", "vk.com", "ok.ru", "facebook.com", "instagram.com",
        "wikipedia.org", "schoolotzyv.ru", "sudact.ru", "synapsenet.ru",
        "bus.gov.ru", "zakupki.gov.ru", "nalog.ru", "e-ecolog.ru", "spark",
        "kartoteka.ru", "seldon", "avito.ru", "youtube.com", "prodoctorov",
        "otzovik", "flamp.ru", "zoon.ru", "bizly.ru", "companies.rbc.ru",
        # Педагогические порталы и каталоги: страницы школ там есть,
        # а контакты — чужие либо редакционные.
        "edu2you.ru", "nsportal.ru", "infourok.ru", "uchi.ru", "maam.ru",
        "multiurok.ru", "videouroki.net", "prodlenka.org", "znanio.ru",
        "obrazovaka.ru", "shkolniku.com", "edu-time.ru", "schoolsdata.ru",
        "russiaschools.ru", "mapdata.ru", "orgpage.ru", "yell.ru", "spr.ru",
        "rusbase", "sbertb", "vipiska-nalog.com", "kontragent",
        "companium.ru", "outstat.ru", "sparkinterfax", "b2b-in.ru",
    )
    # Признаки сайта образовательной организации.
    SCHOOL_HINTS = (
        "shkola", "school", "shkol", "mbou", "mkou", "maou", "mou", "gimn",
        "licey", "lyceum", "sch", "edu", "obr", "internat", "kadet",
        "школ", "мбоу", "гимназ", "лицей",
    )

    def __init__(self, http: HttpClient, user: str, key: str, site: "WebsiteProvider"):
        self.http = http
        self.user = user
        self.key = key
        self.site = site

    def search_docs(self, query: str, attempts: int = 3):
        """(ссылки, текст сниппетов). Сниппеты нужны как запасной источник:
        телефон школы часто виден прямо в выдаче, а её сайт может быть
        недоступен."""
        for attempt in range(attempts):
            resp = self.http.get(
                self.SEARCH, params={"query": query, "key": self.key, "user": self.user}
            )
            if resp.status_code != 200:
                return [], ""
            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError:
                return [], ""
            err = root.find(".//error")
            if err is None:
                urls = [d.findtext("url") or "" for d in root.iter("doc")]
                snippets = " ".join(
                    (t.text or "") for t in root.iter("passage")
                ) + " " + " ".join((t.text or "") for t in root.iter("title"))
                return urls, snippets
            text = err.text or ""
            if "перезапрос" in text.lower() and attempt < attempts - 1:
                continue
            log.warning("xmlriver: %s", text[:120])
            return [], ""
        return [], ""

    def search(self, query: str, attempts: int = 3) -> List[str]:
        for attempt in range(attempts):
            resp = self.http.get(
                self.SEARCH, params={"query": query, "key": self.key, "user": self.user}
            )
            if resp.status_code != 200:
                return []
            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError:
                return []
            err = root.find(".//error")
            if err is None:
                return [d.findtext("url") or "" for d in root.iter("doc")]
            text = (err.text or "")
            # «Выполните перезапрос» — поисковик не ответил, это лечится повтором.
            if "перезапрос" in text.lower() and attempt < attempts - 1:
                continue
            log.warning("xmlriver: %s", text[:120])
            return []
        return []

    @classmethod
    def candidates(cls, urls: List[str], limit: int = 3) -> List[str]:
        """Сайты-кандидаты: агрегаторы отброшены, похожие на школьные — вперёд."""
        hosts, seen = [], set()
        for url in urls:
            host = _host(url).lower()
            if not host or host in seen or any(a in host for a in cls.AGGREGATORS):
                continue
            seen.add(host)
            hosts.append(host)
        # «Госвеб» — государственная платформа сайтов школ: если школа там,
        # это её официальный сайт, и структура разделов у него стандартная.
        hosts.sort(
            key=lambda h: (
                0 if "gosweb.gosuslugi.ru" in h
                else 1 if any(x in h for x in cls.SCHOOL_HINTS)
                else 2
            )
        )
        return [f"https://{h}" for h in hosts[:limit]]

    def fetch(self, inn: str, name: str = "", address: str = "", **_) -> Optional[Contact]:
        query = " ".join(x for x in (name, _locality_of(address)) if x).strip()
        if not query:
            return None
        urls, snippets = self.search_docs(f"{query} официальный сайт")
        for site in self.candidates(urls):
            got = self.site.fetch(inn=inn, website=site, verify_inn=inn)
            if got and (got.email or got.phones):
                got.website = got.website or site
                got.source = self.name
                return got

        # Сайт недоступен или не подтвердился — берём, что видно в выдаче.
        from_snippet = extract_contacts(snippets)
        if from_snippet.email or from_snippet.phones:
            from_snippet.source = "выдача поиска"
            return from_snippet
        return None


def _locality_of(address: str) -> str:
    """Город или населённый пункт из адреса — для поискового запроса."""
    for part in (address or "").split(","):
        part = part.strip()
        if re.match(r"^(Г\.|ГОРОД|С\.|СЕЛО|П\.|ПГТ|СТ-ЦА|АУЛ|Х\.|Д\.\s*[А-ЯЁ])", part, re.I):
            return part
    return ""


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except ValueError:
        return ""


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
    # Раздел «Основные сведения» обязателен и содержит ИНН — по нему сайт и
    # подтверждается. Порядок важен: сначала главная, она есть всегда, и на
    # ней же обычно висят телефон и почта самой школы.
    PAGES = (
        "/",
        "/svedeniya-ob-obrazovatelnoy-organizatsii/osnovnye-svedeniya",
        "/sveden/common",
        "/contacts",
    )

    def __init__(self, http: HttpClient):
        """Сайтам школ нужен свой клиент: их тысячи, часть не отвечает вовсе,
        и ждать каждый по минуте с пятью повторами, как ФНС, недопустимо."""
        self.http = HttpClient(rate=4.0, timeout=8, retries=1)

    # Страницы школьных сайтов бывают на мегабайты; регулярным выражениям
    # столько не нужно, а время они съедают целиком.
    MAX_PAGE = 400_000

    @staticmethod
    def _has_inn(text: str, inn: str) -> bool:
        """ИНН на странице. Быстрая проверка подстрокой, и только если она
        не сработала — разбор с разделителями внутри номера."""
        if not inn:
            return False
        if inn in text:
            return True
        return bool(re.search(r"\D".join(inn), text))

    def _page(self, url: str) -> Optional[str]:
        try:
            resp = self.http.get(url, allow_redirects=True)
        except RuntimeError:
            return None
        if resp.status_code != 200:
            return None
        if "text/html" not in resp.headers.get("Content-Type", ""):
            return None
        text = resp.content.decode(resp.encoding or "utf-8", errors="replace")
        return text[: self.MAX_PAGE]

    def fetch(
        self, inn: str, website: str = "", verify_inn: str = "", **_
    ) -> Optional[Contact]:
        """Контакты с сайта школы.

        `verify_inn` включает проверку принадлежности: сайт засчитывается,
        только если ИНН организации найден на нём. Школы публикуют его в
        разделе «Основные сведения», а справочники и чужие сайты — нет.
        """
        if not website:
            return None
        base = website.rstrip("/")

        # Мёртвый хост отсеивается одним запросом, а не девятью.
        home = self._page(base + "/")
        if home is None:
            return None

        pages = [home]
        confirmed = not verify_inn or self._has_inn(home, verify_inn)
        found = extract_contacts(home)

        if not confirmed or not (found.email or found.phones):
            for path in self.PAGES[1:]:
                text = self._page(base + path)
                if text is None:
                    continue
                pages.append(text)
                if verify_inn and self._has_inn(text, verify_inn):
                    confirmed = True
                more = extract_contacts(text)
                found.email = found.email or more.email
                found.phones = found.phones or more.phones
                if confirmed and (found.email or found.phones):
                    break

        if not confirmed or not (found.email or found.phones):
            return None
        found.website = base
        found.source = self.name
        return found


def build_providers(http: HttpClient, names: Optional[List[str]] = None) -> List:
    simple = {
        "busgov": BusGovProvider,
        "saby": SabyProvider,
        "osm": OsmProvider,
        "site": WebsiteProvider,
    }
    names = names or ["busgov", "search", "osm"]
    out = []
    for n in names:
        if n in simple:
            out.append(simple[n](http))
        elif n == "search":
            user, key = xmlriver_credentials()
            if not (user and key):
                log.warning("поиск сайтов отключён: не задан ключ xmlriver")
                continue
            out.append(XmlRiverProvider(http, user, key, WebsiteProvider(http)))
    return out


def collect(
    providers: List,
    inn: str,
    kpp: str = "",
    website: str = "",
    name: str = "",
    address: str = "",
) -> Contact:
    """Первый непустой ответ; недоступный источник молча пропускается.

    Если по дороге нашёлся адрес официального сайта, он дополнительно
    разбирается: раздел «Сведения об образовательной организации» школы
    обязателен к публикации и содержит телефон и e-mail.
    """
    merged = Contact()
    site_prov = next((p for p in providers if isinstance(p, WebsiteProvider)), None)
    for prov in providers:
        try:
            got = prov.fetch(
                inn=inn, kpp=kpp, website=website, name=name, address=address
            )
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
