# -*- coding: utf-8 -*-
"""Отбор одной записи о службе обучения на организацию.

Пайплайн намеренно однопроходный и идёт всегда от сырых находок: при
повторной фильтрации «поверх» уже отфильтрованного однажды потерялись
записи с собственного сайта компании, и их место заняли худшие.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from ru_schools.http_client import HttpClient

from .collect import grade
from .crawl import page_encoding
from .extract import Lead, html_to_text
from .normalize import department, drop_head_of_company, role
from .sites import brand_words, domain_score

log = logging.getLogger(__name__)

# Признак того, что запись и вправду про обучение, а не про кадры вообще.
TRAINING_RE = re.compile(
    r"обучени|подготовк|учебн|развити|персонал|кадр|университет|академи", re.I
)
BINARY = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".rtf", ".zip")


class Selector:
    def __init__(self, site_finder=None):
        self.http = HttpClient(rate=4, timeout=12, retries=1)
        self.finder = site_finder
        self._pages: Dict[str, Optional[str]] = {}

    def page(self, url: str) -> Optional[str]:
        if url not in self._pages:
            try:
                resp = self.http.get(url, allow_redirects=True)
                self._pages[url] = html_to_text(
                    resp.content[:900_000].decode(page_encoding(resp), errors="replace")
                ).lower()
            except Exception:
                self._pages[url] = None
        return self._pages[url]

    def own_sites(self, domains: List[str], words: List[str]) -> List[str]:
        """Домены, действительно принадлежащие организации.

        Проверка по заголовку одна не годится: половина заводских сайтов
        недоступна, и настоящий сайт остаётся неподтверждённым. Поэтому
        засчитывается либо совпадение домена с именем, либо заголовок.
        """
        out = []
        for d in domains:
            own = domain_score(d, words) >= 3
            if not own and self.finder is not None:
                own = self.finder.title_mentions("https://" + d, words)
            if own:
                out.append(d)
        return out

    def corroborated(self, lead: Dict[str, str], org: dict, sites: List[str]) -> bool:
        """Есть ли на чужой странице привязка именно к этой организации.

        Названия вроде «Сокол» носят и гостиница, и авиазавод в другом
        городе, и однофамилец. Одного имени мало — нужен ИНН, город
        организации или ссылка на её собственный сайт.
        """
        text = self.page(lead.get("url", "")) or lead.get("snippet", "").lower()
        inn = org.get("inn", "")
        if inn and inn in text:
            return True
        for place in (org.get("city", ""), org.get("region", "")):
            token = re.sub(r"^(г|город|д|деревня|рп|пгт)\s+", "", (place or "").lower()).strip()
            if len(token) >= 5 and token in text:
                return True
        return any(d.lower() in text for d in sites)

    def check(self, lead: Dict[str, str]) -> str:
        """Подтверждается ли находка на своей странице."""
        if lead.get("grade") == "сайт компании":
            return "со своего сайта"
        url = lead.get("url", "")
        if url.lower().endswith(BINARY):
            return ""
        text = self.page(url)
        if text is None:
            return "страница недоступна, проверить вручную"
        needle = (lead["person"].split()[0] if lead.get("person") else lead.get("email", "")).lower()
        return "подтверждено на странице" if needle and needle in text else ""

    @staticmethod
    def rank(lead: Dict[str, str]) -> int:
        return (
            bool(lead.get("person")) * 4
            + bool(TRAINING_RE.search(lead.get("department", "") + lead.get("role", ""))) * 3
            + bool(lead.get("email")) * 2
            + bool(lead.get("phones"))
            + (lead.get("grade") == "сайт компании") * 3
        )

    def choose(self, raw: List[dict], org: dict, domains: List[str]) -> List[dict]:
        """Пригодные записи, лучшая первой."""
        name = org.get("name_short") or ""
        words = brand_words(name)
        sites = [d.lower() for d in self.own_sites(domains, words)]
        head = org.get("head_name", "")
        kept = []
        for item in raw:
            lead = dict(item)
            mark = grade(Lead(url=lead["url"], snippet=lead["snippet"]), sites, words,
                         org.get("inn", ""))
            if not mark:
                continue
            lead["grade"] = mark
            if drop_head_of_company(lead, head):
                continue
            checked = self.check(lead)
            if not checked:
                continue
            if mark != "сайт компании" and not self.corroborated(lead, org, sites):
                # Оставляем как след, но в основную строку такое не годится.
                lead["checked"] = "требует ручной сверки: привязка к организации не подтверждена"
                lead["weak"] = True
                kept.append(lead)
                continue
            lead["checked"] = checked
            lead["department"] = department(lead.get("department", ""))
            lead["role"] = role(lead.get("role", ""))
            kept.append(lead)
        kept.sort(key=lambda l: (not l.get("weak"), self.rank(l)), reverse=True)
        return kept
