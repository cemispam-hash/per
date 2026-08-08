# -*- coding: utf-8 -*-
"""Официальный сайт организации по её наименованию и ИНН."""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ru_schools.contacts import (
    SearchUnavailable,
    XmlRiverProvider,
    xmlriver_credentials,
)
from ru_schools.http_client import HttpClient

log = logging.getLogger(__name__)

# Справочники, агрегаторы и отраслевые порталы: официальным сайтом
# компании они не являются, но выдачу по крупным заводам занимают плотно.
NOT_OWN_SITE = (
    "rusprofile", "list-org", "checko", "audit-it", "sbis.ru", "saby.ru",
    "zachestnyibiznes", "kartoteka", "seldon", "spark", "e-ecolog",
    "nalog.ru", "zakupki.gov", "vk.com", "ok.ru", "youtube", "wikipedia",
    "hh.ru", "superjob", "rabota.ru", "avito", "2gis", "yandex.", "google.",
    "rbc.ru", "interfax", "tass.ru", "kommersant", "vedomosti", "forbes",
    "t.me", "telegram", "dzen.ru", "livejournal", "habr", "-portal.",
    "portal.ru", "metalinfo", "metaltorg", "prom.ua", "pulscen", "b2b",
)

# Слова, которые есть в имени почти каждой компании и различать не помогают.
_STOP_WORDS = re.compile(
    r"\b(ПАО|АО|ОАО|ЗАО|ООО|ПК|АК|ИМ|НАУЧНО|ПРОИЗВОДСТВЕННАЯ|КОРПОРАЦИЯ"
    r"|КОМПАНИЯ|УК|ПО|КОМБИНАТ|ЗАВОД|ОБЪЕДИНЕНИЕ|ГРУППА|ХОЛДИНГ)\b",
    re.I,
)


def _looks_like_own_site(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return bool(host) and not any(bad in host for bad in NOT_OWN_SITE)


def brand_words(name: str) -> List[str]:
    """Значимые слова наименования: по ним домен узнаётся в выдаче."""
    cleaned = _STOP_WORDS.sub(" ", re.sub(r'["«»().]', " ", name or ""))
    return [w.lower() for w in re.findall(r"[А-Яа-яЁёA-Za-z]{4,}", cleaned)]


_PAIRS = {"sh": "ш", "ch": "ч", "zh": "ж", "ya": "я", "yu": "ю", "kh": "х", "ts": "ц"}
_LETTERS = {
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е", "z": "з",
    "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о",
    "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "h": "х",
    "c": "ц", "y": "ы",
}


def translit(host: str) -> str:
    """Грубая обратная транслитерация домена: nlmk → нлмк, kamaz → камаз."""
    out, i = [], 0
    while i < len(host):
        two = host[i : i + 2]
        if two in _PAIRS:
            out.append(_PAIRS[two])
            i += 2
            continue
        out.append(_LETTERS.get(host[i], host[i]))
        i += 1
    return "".join(out)


# Двухуровневые окончания: в них «последние две метки» — ещё не домен.
_MULTI_TLD = ("com.ru", "org.ru", "net.ru", "co.uk", "com.tr", "spb.ru", "msk.ru")


def registrable(host: str) -> str:
    """Корневой домен: museum.uralkali.com → uralkali.com.

    Поддомены музеев, профкомов и личных кабинетов совпадают с брендом
    не хуже основного сайта, и без сведения к корню выигрывают именно они.
    """
    host = host.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    tail2 = ".".join(parts[-2:])
    keep = 3 if tail2 in _MULTI_TLD else 2
    return ".".join(parts[-keep:])


def domain_score(host: str, words: List[str]) -> int:
    """Насколько корневой домен похож на имя компании."""
    root = registrable(host)
    label = root.split(".")[0]
    variants = (label, translit(label))
    best = 0
    for w in words:
        if len(w) < 4:
            continue
        # Домен, равный имени бренда, — лучшее, что бывает (kamaz → камаз).
        # Имя внутри домена слабее: так же выглядят «industrial-kamaz»
        # и «cu-avtovaz», а это дилеры и отдельные проекты.
        if any(w == v for v in variants):
            best = max(best, 5)
        elif any(w in v for v in variants):
            best = max(best, 3)
        elif len(w) >= 6 and any(w[:6] in v for v in variants):
            best = max(best, 2)
        elif len(w) >= 5 and any(w[:5] in v for v in variants):
            best = max(best, 1)
    return best


class SiteFinder:
    """Ищет домен компании в выдаче и выбирает наиболее правдоподобный.

    Выбор взвешенный: решает совпадение имени компании с самим доменом,
    а загрузка главной страницы лишь подтверждает. Одной проверки «имя
    встречается на странице» мало — оно встречается и у поставщиков, и у
    дилеров, и вместо «АвтоВАЗа» находится «Лада-Имидж».
    """

    QUERIES = ("{name} официальный сайт", "ИНН {inn} официальный сайт компании")

    def __init__(self, http: Optional[HttpClient] = None):
        user, key = xmlriver_credentials()
        if not (user and key):
            raise RuntimeError("не задан ключ xmlriver (data/xmlriver.txt)")
        self.search = XmlRiverProvider(http or HttpClient(rate=2), user, key, None)
        # Сайты компаний бывают неспешны и капризны — им отдельный клиент
        # с коротким терпением, чтобы проверка не подвешивала поиск.
        self.page_http = HttpClient(rate=2, timeout=15, retries=1)

    def candidates(self, name: str, inn: str, queries=None) -> List[str]:
        """Корневые домены из выдачи, в порядке появления."""
        roots: List[str] = []
        for tpl in queries or self.QUERIES:
            q = tpl.format(name=name, inn=inn)
            try:
                urls, _ = self.search.search_docs(q)
            except SearchUnavailable:
                log.warning("поиск занят на запросе «%s»", q[:60])
                continue
            except Exception as exc:
                log.warning("поиск не отработал: %s", exc)
                continue
            for u in urls:
                if not _looks_like_own_site(u):
                    continue
                # Считаем по корню: поддомены музея, профкома и личного
                # кабинета совпадают с брендом не хуже основного сайта.
                root = registrable(urlparse(u).netloc)
                if root and root not in roots:
                    roots.append(root)
        return roots

    @staticmethod
    def _zone_bonus(domain: str) -> int:
        """Российская компания живёт в своей зоне: kamaz.ru, а не kamaz.market."""
        if domain.endswith(".ru") or domain.endswith(".рф"):
            return 2
        if domain.endswith(".com"):
            return 1
        return 0

    def find(self, name: str, inn: str) -> Tuple[str, int]:
        """(адрес сайта, уверенность). Пустая строка — не нашлось."""
        words = brand_words(name)
        roots = self.candidates(name, inn)
        if not roots:
            return "", 0

        scored: List[Tuple[int, int, str]] = []
        for pos, domain in enumerate(roots):
            score = domain_score(domain, words) * 2 + self._zone_bonus(domain)
            scored.append((score, -pos, domain))
        scored.sort(reverse=True)

        # Страницу грузим только у лучших кандидатов: подтверждение дорогое,
        # а на исход влияет лишь когда домены неразличимы.
        best_score = scored[0][0]
        for score, _, domain in scored[:4]:
            if score < best_score:
                break
            if self.page_mentions("https://" + domain, words):
                return "https://" + domain, score + 2
        return "https://" + scored[0][2], best_score

    def page_text(self, root: str) -> str:
        try:
            resp = self.page_http.get(root + "/", allow_redirects=True)
        except Exception:
            return ""
        if resp.status_code != 200:
            return ""
        return resp.content.decode(resp.encoding or "utf-8", errors="replace")

    def page_mentions(self, root: str, words: List[str]) -> bool:
        text = self.page_text(root).lower()
        return any(w in text[:300_000] for w in words if len(w) >= 5)

    def title_mentions(self, root: str, words: List[str]) -> bool:
        """Имя компании в заголовке главной страницы.

        Признак куда более верный, чем упоминание где-то в теле: имя
        завода встречается и у дилеров, и у профкома, и у рейтингового
        агентства, а в <title> его ставит сам владелец сайта.
        """
        text = self.page_text(root)
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        head = (m.group(1) if m else "")[:300].lower()
        og = re.search(r'property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)', text, re.I)
        if og:
            head += " " + og.group(1).lower()
        return any(w in head for w in words if len(w) >= 4)
