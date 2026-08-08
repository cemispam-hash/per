# -*- coding: utf-8 -*-
"""Обход сайта компании в поисках раздела об обучении персонала."""
from __future__ import annotations

import logging
import re
from typing import Dict, Iterable, List, Set, Tuple
from urllib.parse import urljoin, urlparse

from ru_schools.http_client import HttpClient

from .extract import Lead, html_to_text, leads_from_text

log = logging.getLogger(__name__)

# Ссылки, ведущие к сведениям о персонале и обучении. Вес — насколько
# охотно страницу стоит открыть: «обучение» вернее, чем «о компании».
LINK_WEIGHTS = (
    (re.compile(r"обучени|подготовк[аи]\s+кадров|учебн|университет|академи", re.I), 10),
    (re.compile(r"персонал|кадр|карьер|сотрудник|развити[ея]", re.I), 8),
    (re.compile(r"ваканси|работа\s+у\s+нас|присоединяйся|hr\b", re.I), 6),
    (re.compile(r"контакт|руководств|структур|управлени", re.I), 5),
    (re.compile(r"training|career|personnel|staff|hr|about|contact|team", re.I), 4),
)

# Разделы, которые заведомо не про людей: новости, закупки, продукция.
SKIP_LINK = re.compile(
    r"(новост|press|news|закупк|тендер|продукц|каталог|акционер|investor"
    r"|отчет|отчёт|финанс|shop|store|basket|login|search|\.pdf$|\.doc|\.xls"
    r"|\.jpg$|\.png$|\.zip$)",
    re.I,
)

_HREF = re.compile(r'<a\b[^>]*href=["\']([^"\'#]+)[^>]*>(.*?)</a>', re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


def page_encoding(resp) -> str:
    """Кодировка ответа: заголовок, затем угадывание.

    Российские заводские сайты нередко отдают cp1251 без указания в
    заголовке — без угадывания страница превращается в мусор и ни одно
    название отдела в ней не находится.
    """
    ctype = resp.headers.get("Content-Type", "").lower()
    if "charset=" in ctype:
        return resp.encoding or "utf-8"
    head = resp.content[:2000].decode("latin-1", errors="replace").lower()
    m = re.search(r'charset=["\']?([\w-]+)', head)
    if m:
        return m.group(1)
    return resp.apparent_encoding or "utf-8"


class SiteCrawler:
    """Обходит сайт вширь, начиная с главной, по самым обещающим ссылкам."""

    def __init__(self, http: HttpClient = None, max_pages: int = 14):
        self.http = http or HttpClient(rate=2, timeout=15, retries=1)
        self.max_pages = max_pages

    def fetch(self, url: str) -> str:
        try:
            resp = self.http.get(url, allow_redirects=True)
        except Exception as exc:
            log.debug("не открылось %s: %s", url, exc)
            return ""
        if resp.status_code != 200:
            return ""
        if "html" not in resp.headers.get("Content-Type", "text/html").lower():
            return ""
        return resp.content[:800_000].decode(page_encoding(resp), errors="replace")

    @staticmethod
    def links(html: str, base: str) -> List[Tuple[int, str, str]]:
        """(вес, адрес, текст ссылки) — только в пределах того же сайта."""
        host = urlparse(base).netloc.lower().replace("www.", "")
        out, seen = [], set()
        for href, anchor in _HREF.findall(html):
            url = urljoin(base, href.strip())
            p = urlparse(url)
            if p.scheme not in ("http", "https"):
                continue
            if host not in p.netloc.lower():
                continue
            url = url.split("?")[0]
            if url in seen or SKIP_LINK.search(url):
                continue
            text = _TAG.sub(" ", anchor).strip()[:100]
            if SKIP_LINK.search(text):
                continue
            weight = 0
            for regex, w in LINK_WEIGHTS:
                if regex.search(text) or regex.search(url):
                    weight = max(weight, w)
            if weight:
                seen.add(url)
                out.append((weight, url, text))
        out.sort(key=lambda t: -t[0])
        return out

    def crawl(self, root: str) -> List[Lead]:
        """Зацепки со страниц сайта, начиная с главной."""
        start = root if root.startswith("http") else "https://" + root
        home = self.fetch(start + "/")
        if not home:
            return []

        found: List[Lead] = []
        found += leads_from_text(html_to_text(home), start + "/", "сайт компании")

        queue = self.links(home, start)
        visited: Set[str] = {start + "/"}
        opened = 0
        while queue and opened < self.max_pages:
            weight, url, _ = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            html = self.fetch(url)
            opened += 1
            if not html:
                continue
            found += leads_from_text(html_to_text(html), url, "сайт компании")
            # Со страниц про персонал спускаемся глубже: раздел «Карьера»
            # обычно лишь оглавление, а нужное — на вложенной странице.
            if weight >= 8:
                for w2, u2, t2 in self.links(html, start)[:6]:
                    if u2 not in visited and w2 >= 8:
                        queue.append((w2, u2, t2))
        return found
