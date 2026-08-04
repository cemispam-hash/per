# -*- coding: utf-8 -*-
"""Контакты школ из OpenStreetMap одним пакетом.

Поиск сайтов через xmlriver платный и временами недоступен целиком,
а OSM отдаёт все школы России с телефонами и почтой одним запросом к
Overpass API. Совпадение с ЕГРЮЛ ищется по адресу: населённый пункт,
улица и дом — названия у школ в OSM народные («Школа 22»), сверять по
ним нельзя.

Данные OSM распространяются под ODbL.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, Iterable, Optional, Tuple

from .contacts import Contact, normalize_phone
from .http_client import HttpClient

log = logging.getLogger(__name__)

OVERPASS = "https://overpass-api.de/api/interpreter"

# Школы России, у которых указан хоть какой-то способ связи.
QUERY = """
[out:json][timeout:500];
area["ISO3166-1"="RU"][admin_level=2]->.ru;
(
  nwr["amenity"="school"]["phone"](area.ru);
  nwr["amenity"="school"]["contact:phone"](area.ru);
  nwr["amenity"="school"]["email"](area.ru);
  nwr["amenity"="school"]["contact:email"](area.ru);
  nwr["amenity"="school"]["website"](area.ru);
);
out center tags;
"""

# Типы улиц и населённых пунктов: в ЕГРЮЛ они сокращены («УЛ.», «Г.»),
# в OSM записаны словом («улица», без города вовсе) — сверять можно
# только то, что останется после их отбрасывания.
_STREET_KINDS = re.compile(
    r"\b(улица|ул|проспект|пр-?кт|пр|переулок|пер|шоссе|ш|бульвар|б-?р|проезд"
    r"|набережная|наб|площадь|пл|микрорайон|мкр|тракт|аллея|линия|имени|им)\b\.?"
)
_PLACE_KINDS = re.compile(
    r"\b(город|г|село|с|посёлок|поселок|п|пгт|деревня|д|станица|ст|аул|а"
    r"|хутор|х|рп|мкр|го|м|р-н|мр-н)\b\.?"
)
_NON_WORD = re.compile(r"[^а-яёa-z0-9]+")
# Инициалы в названии улицы: «УЛ. ИМЕНИ В. И. ЛЕНИНА» против «улица Ленина».
# Без их отбрасывания такая улица не сходится сама с собой.
_INITIALS = re.compile(r"\b[а-яёa-z]\.")
# Дом в адресе ЕГРЮЛ идёт последним: «..., УЛ. СУВОРОВА, Д. 25».
_HOUSE_TAIL = re.compile(r".*,\s*(?:д|стр|влд|зд)\.?\s*", re.I)


def _norm_street(value: str) -> str:
    value = _INITIALS.sub(" ", (value or "").lower())
    return _NON_WORD.sub("", _STREET_KINDS.sub(" ", value))


def _norm_place(value: str) -> str:
    return _NON_WORD.sub("", _PLACE_KINDS.sub(" ", (value or "").lower()))


def _norm_house(value: str) -> str:
    m = re.search(r"(\d+[а-яa-z]?)", (value or "").lower())
    return m.group(1) if m else ""


def download(http: HttpClient, path: str) -> int:
    """Выгружает школы России из Overpass в файл. Возвращает число объектов."""
    resp = http.post(OVERPASS, data={"data": QUERY})
    resp.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return len(json.loads(resp.content).get("elements", []))


def index(path: str) -> Dict[Tuple[str, str, str], dict]:
    """Словарь «(нас. пункт, улица, дом) → теги OSM»."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out: Dict[Tuple[str, str, str], dict] = {}
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        key = (
            _norm_place(tags.get("addr:city") or tags.get("addr:place", "")),
            _norm_street(tags.get("addr:street", "")),
            _norm_house(tags.get("addr:housenumber", "")),
        )
        if all(key):
            out.setdefault(key, tags)
    return out


def contact_of(tags: dict) -> Optional[Contact]:
    """Контакт из тегов OSM. Пустой — значит сверять было нечего."""
    phones = []
    for key in ("phone", "contact:phone", "contact:mobile"):
        for raw in re.split(r"[;,]", tags.get(key, "")):
            norm = normalize_phone(raw)
            if norm and norm not in phones:
                phones.append(norm)
    email = ""
    for key in ("email", "contact:email"):
        if tags.get(key):
            email = tags[key].split(";")[0].strip()
            break
    site = tags.get("website") or tags.get("contact:website") or ""
    if not (phones or email):
        return None
    return Contact(email=email, phones=phones[:5], website=site, source="OpenStreetMap")


def match(row, osm: Dict[Tuple[str, str, str], dict]) -> Optional[dict]:
    """Теги OSM для организации из ЕГРЮЛ, если адрес сошёлся."""
    house = _norm_house(_HOUSE_TAIL.sub("", row["address"] or ""))
    street = _norm_street(row["street"])
    for place in (row["city"], row["settlement"]):
        key = (_norm_place(place), street, house)
        if all(key) and key in osm:
            return osm[key]
    return None
