# -*- coding: utf-8 -*-
"""Сбор сведений об учебных службах: обход сайтов плюс поисковая выдача.

Половина заводских сайтов из песочницы недоступна или отдаёт пустую
JS-оболочку, поэтому выдача поиска — не запасной, а равноправный путь:
в сниппете нередко видно и должность, и фамилию, и телефон.
"""
from __future__ import annotations

import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Dict, List
from urllib.parse import urlparse

from ru_schools.contacts import SearchUnavailable, XmlRiverProvider, xmlriver_credentials
from ru_schools.http_client import HttpClient

from .crawl import SiteCrawler
from .extract import Lead, leads_from_text

log = logging.getLogger(__name__)

# Резюме, доски объявлений и справочники: сведения там о посторонних
# людях либо перепечатаны, и ссылка ведёт не к компании.
JUNK_SOURCE = (
    "careerist", "hh.ru", "superjob", "rabota", "trudvsem", "zarplata",
    "orgs.biz", "vk.com", "ok.ru", "avito", "youla", "yandex.", "google.",
    "rusprofile", "list-org", "checko", "zachestnyibiznes", "sbis.ru",
    "spark-interfax", "e-ecolog", "kartoteka", "otzyv", "pikabu", "dzen.ru",
    "vc.ru", "livejournal", "wikipedia", "t.me",
)


def is_junk_source(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(bad in host for bad in JUNK_SOURCE)

# Запросы к выдаче: то же, что ищем на сайте, но чужими глазами.
SEARCH_QUERIES = (
    "{name} начальник отдела подготовки кадров",
    "{name} руководитель учебного центра контакты",
    "{name} директор по персоналу email",
    "{name} обучение персонала телефон отдела",
    "{name} корпоративный университет руководитель",
)


# Запросы про руководство: ищем не учебный центр, а человека, который
# в структуре завода отвечает за персонал и направляет людей на обучение.
LEADERSHIP_QUERIES = (
    "{name} заместитель генерального директора по персоналу",
    "{name} начальник управления по работе с персоналом",
    "{name} руководство структура управления персоналом",
    "{name} телефонный справочник отдел подготовки кадров",
    "{name} начальник отдела подготовки кадров ФИО",
)


class Collector:
    def __init__(self, max_pages: int = 14):
        user, key = xmlriver_credentials()
        if not (user and key):
            raise RuntimeError("не задан ключ xmlriver (data/xmlriver.txt)")
        self.search = XmlRiverProvider(HttpClient(rate=2), user, key, None)
        self.crawler = SiteCrawler(max_pages=max_pages)

    def from_sites(self, sites: List[str]) -> List[Lead]:
        found: List[Lead] = []
        for domain in sites:
            try:
                found += self.crawler.crawl("https://" + domain.lstrip("htps:/"))
            except Exception as exc:
                log.warning("обход %s не удался: %s", domain, exc)
        return found

    def documents(self, query: str):
        """[(адрес, текст сниппета)] — каждый документ отдельно.

        Склеивать сниппеты всей выдачи нельзя: тогда найденное лицо
        приписывается первой ссылке, и в таблицу попадают чужие страницы
        вроде резюме на кадровом сайте.
        """
        resp = self.search.http.get(
            self.search.SEARCH,
            params={"query": query, "key": self.search.key, "user": self.search.user},
        )
        if resp.status_code != 200:
            return []
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return []
        err = root.find(".//error")
        if err is not None:
            text = (err.text or "").lower()
            if "перезапрос" in text or "канал" in text:
                raise SearchUnavailable(text[:120])
            return []
        out = []
        for doc in root.iter("doc"):
            url = doc.findtext("url") or ""
            parts = [t.text or "" for t in doc.iter("passage")]
            parts += [t.text or "" for t in doc.iter("title")]
            out.append((url, "\n".join(p for p in parts if p)))
        return out

    def from_search(self, name: str, queries=None, parser=None) -> List[Lead]:
        found: List[Lead] = []
        parser = parser or leads_from_text
        for tpl in queries or SEARCH_QUERIES:
            q = tpl.format(name=name)
            for attempt in range(6):
                try:
                    docs = self.documents(q)
                    break
                except SearchUnavailable:
                    time.sleep(1.5)
                except Exception as exc:
                    log.warning("поиск не отработал: %s", exc)
                    docs = []
                    break
            else:
                log.warning("поиск занят: %s", q[:50])
                continue
            for url, snippet in docs:
                if not snippet or is_junk_source(url):
                    continue
                found += parser(snippet, url, "выдача поиска")
        return found


def grade(lead: Lead, sites: List[str], words: List[str]) -> str:
    """Насколько записи можно верить.

    Одно и то же название «учебный центр» встречается и на сайте завода,
    и на сайте техникума, который для него готовит рабочих. Первое — про
    службу заказчика, второе — про постороннюю организацию, и различать
    их обязательно.
    """
    host = urlparse(lead.url).netloc.lower().replace("www.", "")
    if any(host.endswith(d) for d in sites):
        return "сайт компании"
    haystack = (lead.snippet + " " + lead.url).lower()
    if any(w in haystack for w in words if len(w) >= 5):
        return "сторонний сайт, компания упомянута"
    return ""


def dedupe(leads: List[Lead]) -> List[Lead]:
    """Схлопывает повторы, оставляя самую содержательную запись."""
    best: Dict[tuple, Lead] = {}
    for lead in leads:
        # Одно и то же лицо описано на нескольких страницах по-разному:
        # ключом берём человека и почту, а не название отдела.
        key = (lead.person.lower(), lead.email.lower(),
               tuple(lead.phones) if not (lead.person or lead.email) else ())
        if key == ("", "", ()):
            continue
        old = best.get(key)
        if old is None or lead.weight() > old.weight():
            best[key] = lead
    return sorted(best.values(), key=lambda l: -l.weight())


def to_dict(lead: Lead) -> dict:
    return {
        "department": lead.department, "role": lead.role, "person": lead.person,
        "email": lead.email, "phones": lead.phones, "url": lead.url,
        "source": lead.source, "snippet": lead.snippet,
    }
