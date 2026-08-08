# -*- coding: utf-8 -*-
"""Сайты, на которых может быть сказано, кто заведует обучением.

У крупного предприятия таких сайтов обычно несколько: собственный,
сайт группы, корпоративный университет, учебный центр, сайт филиала.
Служба обучения описана то на одном, то на другом, поэтому берутся все,
чей домен связан с компанией или с её учебным подразделением.
"""
from __future__ import annotations

import logging
from typing import Dict, List
from urllib.parse import urlparse

from .sites import SiteFinder, brand_words, domain_score, registrable

log = logging.getLogger(__name__)

# Запросы подобраны так, чтобы поднять в выдачу именно учебные
# подразделения: корпоративные университеты, учебные центры, отделы
# подготовки кадров — у них часто отдельные сайты и поддомены.
TRAINING_QUERIES = (
    "{name} корпоративный университет",
    "{name} учебный центр обучение персонала",
    "{name} отдел подготовки кадров контакты",
    "{name} директор по персоналу",
    "{name} обучение и развитие персонала контакты",
)

# Слова, по которым домен виден как учебный, даже если имени компании в
# нём нет: corporate university, учебный центр, образование.
TRAINING_DOMAIN_HINTS = (
    "univer", "university", "edu", "uchebn", "training", "learn", "academy",
    "akadem", "cu-", "-cu", "kadr", "personal", "hr-", "-hr",
)


def related_sites(finder: SiteFinder, name: str, inn: str, primary: str) -> List[str]:
    """Домены, которые стоит обойти по этой компании."""
    found: List[str] = []
    if primary:
        found.append(registrable(urlparse(primary).netloc))

    roots = finder.candidates(name, inn, queries=TRAINING_QUERIES)
    words = brand_words(name)
    for domain in roots:
        if domain in found:
            continue
        label = domain.split(".")[0]
        related = domain_score(domain, words) >= 3
        educational = any(h in label for h in TRAINING_DOMAIN_HINTS)
        # Чужой учебный центр нам не нужен: домен должен быть либо
        # брендовым, либо учебным И при этом упоминать компанию.
        if related:
            found.append(domain)
        elif educational and finder.page_mentions("https://" + domain, words):
            found.append(domain)
    return found
