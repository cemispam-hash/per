# -*- coding: utf-8 -*-
"""Приведение найденных названий и лиц к пригодному для таблицы виду."""
from __future__ import annotations

import re
from typing import Dict, Optional

# Названия попадают в текст в косвенном падеже — «руководитель учебного
# центра» даёт «учебного центр». В таблице нужен именительный.
CANONICAL = (
    (re.compile(r"корпоративн\w*\s+университет\w*", re.I), "Корпоративный университет"),
    (re.compile(r"учебно-\w+\s+центр\w*", re.I), "Учебно-производственный центр"),
    (re.compile(r"учебн\w*\s+центр\w*", re.I), "Учебный центр"),
    (re.compile(r"центр\w*\s+подготовки\s+кадров", re.I), "Центр подготовки кадров"),
    (re.compile(r"центр\w*\s+подготовки\w*", re.I), "Центр подготовки"),
    (re.compile(r"центр\w*\s+обучения\w*", re.I), "Центр обучения"),
    (re.compile(r"отдел\w*\s+подготовки\s+кадров", re.I), "Отдел подготовки кадров"),
    (re.compile(r"отдел\w*\s+обучения\w*", re.I), "Отдел обучения"),
    (re.compile(r"отдел\w*\s+развития\s+персонала", re.I), "Отдел развития персонала"),
    (re.compile(r"управлени\w*\s+подготовки\s+кадров", re.I), "Управление подготовки кадров"),
    (re.compile(r"управлени\w*\s+(?:по\s+работе\s+с\s+персоналом|персоналом)", re.I),
     "Управление по работе с персоналом"),
    (re.compile(r"департамент\w*\s+(?:по\s+)?(?:управлени\w+\s+)?персонал\w*", re.I),
     "Департамент по управлению персоналом"),
    (re.compile(r"дирекци\w*\s+по\s+персоналу", re.I), "Дирекция по персоналу"),
    (re.compile(r"служб\w*\s+(?:управления\s+персоналом|персонала|по\s+персоналу)", re.I),
     "Служба управления персоналом"),
    (re.compile(r"отдел\w*\s+кадров", re.I), "Отдел кадров"),
    (re.compile(r"(?:корпоративн\w+|техническ\w+|производственн\w+)\s+академи\w*", re.I),
     "Корпоративная академия"),
)


def department(value: str) -> str:
    """Название подразделения в именительном падеже."""
    text = re.sub(r"\s+", " ", value or "").strip(" .,:;—-")
    if not text:
        return ""
    for regex, canon in CANONICAL:
        if regex.search(text):
            return canon
    return text[:1].upper() + text[1:]


def role(value: str) -> str:
    """Должность с заглавной буквы и без хвостов разметки."""
    text = re.sub(r"\s+", " ", value or "").strip(" .,:;—-")
    return (text[:1].upper() + text[1:]) if text else ""


_SURNAME = re.compile(r"^([А-ЯЁ][а-яё\-]+)")

# Должности, при которых человек и вправду заведует обучением.
PERSONNEL_ROLE = re.compile(
    r"(персонал|кадр|обучени|подготовк|учебн|развити|hr|университет|академи)", re.I
)


def same_person(a: str, b: str) -> bool:
    """Один ли это человек — сравниваем по фамилии."""
    ma, mb = _SURNAME.match(a or ""), _SURNAME.match(b or "")
    return bool(ma and mb and ma.group(1).lower() == mb.group(1).lower())


def drop_head_of_company(lead: Dict[str, str], company_head: str) -> bool:
    """Не выдавать первое лицо за руководителя службы обучения.

    Генеральный директор попадает в находки просто потому, что упомянут
    рядом с учебным центром — на странице новости или в шапке сайта.
    Засчитывать его можно, только если названная должность и вправду
    кадровая.
    """
    if not company_head or not lead.get("person"):
        return False
    if not same_person(lead["person"], company_head):
        return False
    return not PERSONNEL_ROLE.search(lead.get("role", "") or "")
