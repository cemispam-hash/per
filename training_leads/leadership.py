# -*- coding: utf-8 -*-
"""Страницы руководства и структуры: кто в компании отвечает за кадры.

Отдел подготовки кадров редко имеет собственную страницу с контактами,
зато его начальник обычно перечислен там же, где остальное руководство —
в разделах «Руководство», «Структура управления», «Телефонный справочник».
Этот обход идёт целенаправленно по ним.
"""
from __future__ import annotations

import logging
import re
from typing import List

from .crawl import SiteCrawler
from .extract import Lead, html_to_text, leads_from_text

log = logging.getLogger(__name__)

# Разделы, где перечисляют людей с должностями.
LEADERSHIP_LINKS = (
    re.compile(
        r"руководств|менеджмент|правлен|структур|дирекци|аппарат"
        r"|телефонн\w*\s*справочник|справочник\s*телефон|контакты\s*(?:служб|подраздел)"
        r"|состав\s*правления|топ-менеджмент|команда|management|governance|board",
        re.I,
    ),
)

# Должности, чьи носители направляют людей на обучение. Список шире, чем
# при поиске учебных центров: в структуре крупного завода служба обучения
# сидит внутри блока по персоналу и отдельной страницы не имеет.
PERSONNEL_ROLE_RE = re.compile(
    r"((?:первый[^\S\n]+)?заместител\w+[^\S\n]+(?:генерального[^\S\n]+)?директора"
    r"[^\S\n]+по[^\S\n]+(?:персоналу|кадрам|управлению[^\S\n]+персоналом"
    r"|кадрам[^\S\n]+и[^\S\n]+[\w-]+|социальным[^\S\n]+вопросам|общим[^\S\n]+вопросам)"
    r"|вице-президент\w*[^\S\n]+по[^\S\n]+(?:персоналу|управлению[^\S\n]+персоналом|кадрам)"
    r"|директор\w*[^\S\n]+(?:департамента[^\S\n]+)?по[^\S\n]+(?:персоналу|кадрам"
    r"|управлению[^\S\n]+персоналом|организационному[^\S\n]+развитию"
    r"|развитию[^\S\n]+персонала)"
    r"|директор\w*[^\S\n]+(?:корпоративного[^\S\n]+университета|учебного[^\S\n]+центра"
    r"|департамента[^\S\n]+управления[^\S\n]+персоналом)"
    r"|начальник\w*[^\S\n]+(?:управления|департамента|отдела|бюро|центра|службы)"
    r"[^\S\n]+(?:[\w-]+[^\S\n]+){0,3}(?:персонал\w*|кадр\w+|обучени\w+|подготовк\w+"
    r"|развити\w+[^\S\n]+персонала)"
    r"|начальник\w*[^\S\n]+(?:отдела|управления)[^\S\n]+кадров"
    r"|руководител\w+[^\S\n]+(?:службы|блока|направления)[^\S\n]+(?:по[^\S\n]+)?"
    r"(?:персоналу|управления[^\S\n]+персоналом|обучения|подготовки[^\S\n]+кадров)"
    r"|hr[- ]?директор|директор[^\S\n]+по[^\S\n]+hr)",
    re.I,
)


class LeadershipCrawler(SiteCrawler):
    """Тот же обход, но нацеленный на разделы с перечнем руководителей."""

    def links(self, html: str, base: str):
        found = super().links(html, base)
        # Родительский обход ранжирует по словам про обучение; здесь важнее
        # страницы с людьми, поэтому им поднимается вес.
        boosted = []
        for weight, url, text in found:
            if any(r.search(text) or r.search(url) for r in LEADERSHIP_LINKS):
                weight = max(weight, 12)
            boosted.append((weight, url, text))
        boosted.sort(key=lambda t: -t[0])
        return boosted


# Перечни руководителей свёрстаны таблицей или списком: строка таблицы —
# это один человек. Разбор по окну символов такие строки перемешивает,
# и телефон соседа достаётся не тому руководителю.
_RECORD_END = re.compile(r"</(tr|li|p|article|section|h[1-6])\s*>", re.I)

# На заводских страницах номер пишут без кода страны: «(3439) 37-25-01».
# Общее правило такие номера пропускает, а другого телефона там нет.
LOCAL_PHONE_RE = re.compile(r"\((\d{3,5})\)[ \u00a0]?(\d{2,3})[- ]?(\d{2})[- ]?(\d{2})")


def local_phone(text: str) -> str:
    m = LOCAL_PHONE_RE.search(text)
    if not m:
        return ""
    from ru_schools.contacts import normalize_phone

    return normalize_phone("8" + "".join(m.groups()))


def records(html: str) -> List[str]:
    """Текст записей страницы: строк таблицы, пунктов списка, абзацев."""
    from .extract import html_to_text

    parts = _RECORD_END.split(html)
    # split возвращает и содержимое, и имена тегов — берём только содержимое.
    chunks = [p for i, p in enumerate(parts) if i % 2 == 0]
    out = []
    for chunk in chunks:
        text = html_to_text(chunk).strip()
        if text:
            out.append(re.sub(r"\s+", " ", text))
    return out


def leads_from_leadership(html: str, url: str, source: str) -> List[Lead]:
    """Руководители кадрового блока со страницы структуры.

    Отличие от общего разбора: пляшем не от названия отдела, а от
    должности — на странице руководства отделы обычно не названы вовсе.
    """
    from ru_schools.contacts import EMAIL_RE, PHONE_RE, _JUNK_EMAIL, normalize_phone

    from .extract import _tidy, find_person

    out: List[Lead] = []
    seen = set()
    blocks = records(html)
    for i, block in enumerate(blocks):
        m = PERSONNEL_ROLE_RE.search(block)
        if not m:
            continue
        lead = Lead(url=url, source=source)
        lead.role = _tidy(m.group(1))
        lead.person = find_person(block)
        # В строке таблицы фамилия иногда стоит в соседней ячейке, которая
        # разбором попала в предыдущую запись — заглядываем и туда.
        if not lead.person and i:
            lead.person = find_person(blocks[i - 1])
        mails = [e for e in EMAIL_RE.findall(block) if not _JUNK_EMAIL.search(e)]
        lead.email = mails[0] if mails else ""
        for raw in PHONE_RE.findall(block):
            norm = normalize_phone(raw)
            if norm:
                lead.phones = [norm]
                break
        if not lead.phones:
            local = local_phone(block)
            if local:
                lead.phones = [local]
        lead.snippet = block[:300]

        if not (lead.person or lead.email or lead.phones):
            continue
        key = (lead.role.lower(), lead.person.lower(), lead.email.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def crawl_leadership(root: str, max_pages: int = 12) -> List[Lead]:
    crawler = LeadershipCrawler(max_pages=max_pages)
    start = root if root.startswith("http") else "https://" + root
    home = crawler.fetch(start + "/")
    if not home:
        return []
    found: List[Lead] = []
    queue = crawler.links(home, start)
    visited = {start + "/"}
    opened = 0
    while queue and opened < max_pages:
        weight, url, _ = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        html = crawler.fetch(url)
        opened += 1
        if not html:
            continue
        found += leads_from_leadership(html, url, "страница руководства")
        found += leads_from_text(html_to_text(html), url, "страница руководства")
        if weight >= 12:
            for w2, u2, t2 in crawler.links(html, start)[:6]:
                if u2 not in visited and w2 >= 10:
                    queue.append((w2, u2, t2))
    return found
