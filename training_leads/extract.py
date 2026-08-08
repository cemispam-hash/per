# -*- coding: utf-8 -*-
"""Выделение служб обучения персонала и ответственных лиц из текста страниц."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ru_schools.contacts import EMAIL_RE, PHONE_RE, _JUNK_EMAIL, normalize_phone

# Подразделения, отвечающие за обучение. Порядок важен: сначала более
# частные названия, чтобы «корпоративный университет» не превращался
# в общее «управление персоналом».
DEPARTMENT_RE = re.compile(
    r"(корпоративн\w+ университет"
    r"|учебн\w+(?:[^\S\n]+\w+){0,2}[^\S\n]+центр|центр\w*[^\S\n]+подготовки(?:[^\S\n]+\w+){0,3}"
    r"|центр\w*[^\S\n]+обучения(?:[^\S\n]+\w+){0,3}"
    r"|отдел\w*[^\S\n]+(?:подготовки|обучения|развития)(?:[^\S\n]+\w+){0,3}"
    r"|управлени\w+[^\S\n]+(?:подготовки|обучения|развития|по[^\S\n]+работе[^\S\n]+с[^\S\n]+персоналом)(?:[^\S\n]+\w+){0,3}"
    r"|департамент\w*[^\S\n]+(?:по[^\S\n]+)?(?:управлени\w+[^\S\n]+)?персонал\w*"
    r"|дирекци\w+[^\S\n]+по[^\S\n]+персоналу|служб\w+[^\S\n]+(?:персонала|по[^\S\n]+персоналу|управления[^\S\n]+персоналом)"
    r"|отдел\w*[^\S\n]+кадров(?:[^\S\n]+и\s+\w+){0,2}"
    r"|управлени\w+[^\S\n]+персоналом"
    r"|техническ\w+[^\S\n]+учил\w+|учебно-\w+[^\S\n]+центр\w*"
    # «Академия» засчитывается только корпоративная: иначе в отделы
    # обучения попадает улица Академика и академия наук по соседству.
    r"|(?:корпоративн\w+|техническ\w+|производственн\w+)[^\S\n]+академи\w+"
    r"|академи\w+[^\S\n]+(?:персонала|развития|компании|групп\w+))",
    re.I,
)

# Должности людей, которые за обучение отвечают.
ROLE_RE = re.compile(
    r"((?:заместитель[^\S\n]+)?(?:генерального[^\S\n]+)?директор\w*[^\S\n]+по[^\S\n]+(?:персоналу|кадрам|"
    r"управлению[^\S\n]+персоналом|организационному[^\S\n]+развитию)"
    r"|директор\w*[^\S\n]+(?:корпоративного[^\S\n]+университета|учебного[^\S\n]+центра)"
    r"|начальник\w*[^\S\n]+(?:управления|отдела|центра|бюро)[^\S\n]+(?:[\w-]+[^\S\n]+){0,3}"
    r"(?:персонал\w*|кадров|обучения|подготовки|развития)"
    r"|руководител\w+[^\S\n]+(?:направления[^\S\n]+)?(?:по[^\S\n]+)?(?:обучени\w+|подготовк\w+|развити\w+"
    r"|учебного[^\S\n]+центра|корпоративного[^\S\n]+университета)"
    r"|(?:ведущий[^\S\n]+|главный[^\S\n]+)?(?:специалист|менеджер|инженер)\w*[^\S\n]+по[^\S\n]+(?:обучению|"
    r"подготовке[^\S\n]+кадров|развитию[^\S\n]+персонала|персоналу|кадрам)"
    r"|hr[- ]?директор|hr[- ]?менеджер"
    r"|начальник\w*[^\S\n]+отдела[^\S\n]+кадров)",
    re.I,
)

# «Иванов Иван Иванович» и «Иванов И. И.» — обе записи встречаются.
FIO_FULL_RE = re.compile(
    r"\b([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)[^\S\n]+([А-ЯЁ][а-яё]+)[^\S\n]+([А-ЯЁ][а-яё]+(?:ич|вна|чна|ична))\b"
)
FIO_SHORT_RE = re.compile(
    r"\b([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)[^\S\n]+([А-ЯЁ])\.\s?([А-ЯЁ])\.")
FIO_SHORT_PRE_RE = re.compile(
    r"\b([А-ЯЁ])\.\s?([А-ЯЁ])\.\s?([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\b")

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_BLOCK = re.compile(r"</(p|div|li|tr|h[1-6]|td|section|article|br)>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\xa0]+")


def html_to_text(html: str) -> str:
    """Текст страницы с сохранением границ блоков."""
    text = _TAGS.sub(" ", html)
    text = _BLOCK.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = (
        text.replace("&nbsp;", " ").replace("&#160;", " ")
        .replace("&laquo;", "«").replace("&raquo;", "»")
        .replace("&quot;", '"').replace("&amp;", "&").replace("&mdash;", "—")
        .replace("&#171;", "«").replace("&#187;", "»")
    )
    text = _SPACES.sub(" ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


@dataclass
class Lead:
    """Одна найденная зацепка: кто и где отвечает за обучение."""

    org_inn: str = ""
    org_name: str = ""
    department: str = ""
    role: str = ""
    person: str = ""
    email: str = ""
    phones: List[str] = field(default_factory=list)
    url: str = ""
    source: str = ""
    snippet: str = ""

    def key(self):
        return (self.org_inn, self.department.lower(), self.person.lower(),
                self.email.lower(), tuple(self.phones))

    def weight(self) -> int:
        """Насколько зацепка полезна: человек с почтой ценнее отдела без всего."""
        return (
            bool(self.person) * 4 + bool(self.email) * 3
            + bool(self.phones) * 2 + bool(self.role) * 2 + bool(self.department)
        )


def _clean_fio(match) -> str:
    return " ".join(part for part in match.groups() if part)


def find_person(chunk: str) -> str:
    m = FIO_FULL_RE.search(chunk)
    if m:
        return _clean_fio(m)
    m = FIO_SHORT_RE.search(chunk)
    if m:
        return f"{m.group(1)} {m.group(2)}. {m.group(3)}."
    m = FIO_SHORT_PRE_RE.search(chunk)
    if m:
        return f"{m.group(3)} {m.group(1)}. {m.group(2)}."
    return ""


def _emails(chunk: str) -> List[str]:
    return [e for e in EMAIL_RE.findall(chunk) if not _JUNK_EMAIL.search(e)]


def _phones(chunk: str) -> List[str]:
    out = []
    for raw in PHONE_RE.findall(chunk):
        norm = normalize_phone(raw)
        if norm and norm not in out:
            out.append(norm)
    return out[:3]


# Окно вокруг найденного упоминания: контакты в вёрстке стоят рядом с
# названием отдела, но не вплотную — между ними бывает разметка таблицы.
WINDOW = 300


def _nearest(regex, chunk: str, anchor: int, limit: int = WINDOW):
    """Ближайшее к упоминанию совпадение — и только если оно рядом.

    Брать первое попавшееся в окне нельзя: на странице с перечнем служб
    почта соседнего отдела оказывается ближе к началу окна, чем своя,
    и контакты расходятся по чужим строкам.
    """
    best, best_dist = None, limit + 1
    for m in regex.finditer(chunk):
        dist = 0 if m.start() <= anchor <= m.end() else min(
            abs(m.start() - anchor), abs(m.end() - anchor)
        )
        if dist < best_dist:
            best, best_dist = m, dist
    return best


def _tidy(value: str) -> str:
    return _SPACES.sub(" ", value).strip(" \n\t—-:;,")[:120]


def leads_from_text(text: str, url: str, source: str) -> List[Lead]:
    """Все зацепки со страницы: отдел или должность плюс контакты рядом."""
    found: List[Lead] = []
    seen = set()

    for regex, kind in ((ROLE_RE, "role"), (DEPARTMENT_RE, "dept")):
        for m in regex.finditer(text):
            start = max(0, m.start() - WINDOW // 2)
            chunk = text[start : m.end() + WINDOW]
            anchor = m.start() - start

            lead = Lead(url=url, source=source)
            if kind == "role":
                lead.role = _tidy(m.group(1))
                dept = _nearest(DEPARTMENT_RE, chunk, anchor)
                lead.department = _tidy(dept.group(1)) if dept else ""
            else:
                lead.department = _tidy(m.group(1))
                role = _nearest(ROLE_RE, chunk, anchor)
                lead.role = _tidy(role.group(1)) if role else ""

            person = _nearest(FIO_FULL_RE, chunk, anchor, 200) or _nearest(
                FIO_SHORT_RE, chunk, anchor, 200
            )
            lead.person = find_person(person.group(0)) if person else ""

            mail = _nearest(EMAIL_RE, chunk, anchor, 250)
            if mail and not _JUNK_EMAIL.search(mail.group(0)):
                lead.email = mail.group(0)
            phone = _nearest(PHONE_RE, chunk, anchor, 250)
            if phone:
                norm = normalize_phone(phone.group(0))
                lead.phones = [norm] if norm else []

            lead.snippet = _SPACES.sub(" ", chunk).replace("\n", " ").strip()[:300]
            if not (lead.person or lead.email or lead.phones):
                continue
            k = (lead.department.lower(), lead.role.lower(), lead.person.lower(),
                 lead.email.lower(), tuple(lead.phones))
            if k in seen:
                continue
            seen.add(k)
            found.append(lead)
    return found
