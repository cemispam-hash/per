# -*- coding: utf-8 -*-
"""Актуализация реквизитов организаций из готового списка.

В исходных списках названия успевают устареть, а ИНН нередко стоит от
другой организации — в разбираемом файле он и вовсе оказался смещён на
строку. Поэтому опорой служит не ИНН из файла, а связка «наименование +
адрес»: по ней организация ищется в DaData, а ИНН из файла лишь
сверяется и, если не сходится, отмечается как несовпадение.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from .dadata import DaData, clean_name, unpack

log = logging.getLogger(__name__)

_QUOTES = re.compile(r'["«»\']')
_OPF = re.compile(
    r"\b(ПАО|ОАО|АО|ЗАО|ООО|АК|НПО|ВПК|ГК|ФГУП|МУП|ПК)\b\.?", re.I
)
# Профкомы, советы ветеранов и подобные живут по адресу предприятия и
# носят его имя, но предприятием не являются.
_SATELLITE = re.compile(
    r"(профсоюз|профком|первичная\s+профсоюзная|ветеран|тсж|жск|фонд|"
    r"некоммерческ|обществен\w+\s+организац|\bппо\b)",
    re.I,
)


def _core(name: str) -> str:
    """Ядро наименования: без кавычек, организационной формы и мусора."""
    text = _OPF.sub(" ", _QUOTES.sub(" ", clean_name(name)))
    return re.sub(r"[^А-Яа-яЁёA-Za-z0-9 ]", " ", text).lower().split()


def _city_words(address: str) -> List[str]:
    """Названия населённых пунктов из адреса файла."""
    out = []
    for m in re.finditer(r"(?:г\.|город|д\.|деревня|п/о|пос\.|посёлок|поселок|г)\s*([А-ЯЁ][а-яё\-]+)", address):
        out.append(m.group(1).lower())
    return out


def _house(address: str) -> str:
    """Номер дома из адреса файла: «..., д. 217.» → «217»."""
    m = re.search(r"(?:д|стр|влд|зд|дом)\.?\s*(\d+[а-я]?)\s*\.?\s*$", address.strip(), re.I)
    if m:
        return m.group(1).lower()
    m = re.search(r",\s*(\d+[а-я]?)\s*\.?\s*$", address.strip())
    return m.group(1).lower() if m else ""


def _place_tokens(address: str) -> List[str]:
    """Заметные слова адреса: улицы, деревни, промзоны."""
    words = re.findall(r"[А-ЯЁ][а-яё]{4,}", address)
    stop = {"Московская", "Область", "Истринский", "Красногорский", "Балашиха"}
    return [w.lower() for w in words if w not in stop]


def address_agrees(candidate: Dict[str, str], index: str, address: str) -> bool:
    """Сходится ли адрес кандидата с адресом из файла.

    Без этого совпадение по одному названию уводит к однофамильцам:
    у «Данфосса» так находилось представительство датской головной
    компании, у которого адреса в реестре нет вовсе.
    """
    if index and candidate.get("postal_code") == index:
        return True
    found = (candidate.get("address") or "").lower()
    if not found:
        return False
    cities = _city_words(address)
    if cities and any(c in found for c in cities):
        return True
    house = _house(address)
    tokens = _place_tokens(address)
    return bool(house and tokens and re.search(rf"\b{re.escape(house)}\b", found)
                and any(t in found for t in tokens))


def score(candidate: Dict[str, str], name: str, index: str, address: str) -> int:
    """Насколько кандидат DaData похож на строку файла."""
    points = 0
    if index and candidate.get("postal_code") == index:
        points += 4
    cities = _city_words(address)
    city = (candidate.get("city") or "").lower()
    if cities and any(c in city for c in cities):
        points += 3
    if "московская" in (candidate.get("region") or "").lower() and "московская" in address.lower():
        points += 1

    # Адрес — довод весомее названия: организация может смениться именем,
    # но продолжать работать на прежней площадке.
    found_address = (candidate.get("address") or "").lower()
    house = _house(address)
    if house and re.search(rf"\b{re.escape(house)}\b", found_address):
        points += 3
    tokens = _place_tokens(address)
    if tokens and any(t in found_address for t in tokens):
        points += 2

    # Организационно-правовая форма из файла тоже довод: по одному адресу
    # у группы бывают и ООО, и АО, а строке соответствует лишь одно из них.
    opf_file = {w.upper() for w in _OPF.findall(name)}
    opf_found = {w.upper() for w in _OPF.findall(candidate.get("name_short", ""))}
    if opf_file and opf_found:
        points += 2 if opf_file & opf_found else -2

    want, got = set(_core(name)), set(_core(candidate.get("name_short", "")))
    if want and want <= got:
        points += 3
    elif want & got:
        points += 1

    # Из двух организаций по одному адресу нужна работающая: ликвидированная
    # — это прошлое той же площадки, а актуализируем мы настоящее.
    if candidate.get("status") == "действующее":
        points += 4
    if _SATELLITE.search(candidate.get("name_short", "") + " " + candidate.get("name_full", "")):
        points -= 8
    # Филиал засчитываем, только если он и в файле назван филиалом.
    if candidate.get("branch_type") and candidate["branch_type"] != "MAIN":
        points -= 0 if re.search(r"филиал|представительств", name, re.I) else 4
    return points


_INN_RE = re.compile(r"\b(\d{10})\b")


def by_address(search, name: str, index: str, address: str) -> List[str]:
    """ИНН, найденные в выдаче по адресу организации.

    Нужно, когда организация сменила имя: по старому названию в реестре
    её уже нет, а по адресу площадки правопреемник находится сразу.
    Из выдачи берём только числа, похожие на ИНН, — проверять их всё
    равно будет DaData.
    """
    from ru_schools.contacts import SearchUnavailable

    place = re.sub(r"^Московская область,\s*", "", address).strip(" .")
    queries = [f"{name} {place} ИНН", f"{index} {place} ИНН организации"]
    found: List[str] = []
    for q in queries:
        try:
            _, snippets = search.search_docs(q)
        except SearchUnavailable:
            continue
        except Exception:
            continue
        for m in _INN_RE.finditer(snippets or ""):
            if m.group(1) not in found:
                found.append(m.group(1))
    return found[:12]


def resolve(dd: DaData, name: str, index: str, address: str, inn: str, search=None) -> Tuple[Optional[dict], str]:
    """(лучший кандидат, примечание). Ищем по имени, ИНН только сверяем."""
    seen: Dict[str, dict] = {}
    # Кавычки и пометки вроде «Центральный оф.» подсказку только сбивают,
    # поэтому спрашиваем и полным написанием, и одним ядром названия.
    queries = [clean_name(name), " ".join(_core(name))]
    for q in dict.fromkeys(q for q in queries if q):
        for s in dd.by_name(q, count=10):
            u = unpack(s)
            if u["inn"]:
                seen.setdefault(u["inn"] + u["kpp"], u)
    # Название могло смениться целиком — тогда поможет только ИНН из файла.
    by_inn = [unpack(s) for s in dd.by_inn(inn)] if inn else []
    for u in by_inn:
        seen.setdefault(u["inn"] + u["kpp"], u)

    def pick():
        if not seen:
            return None
        top = max(seen.values(), key=lambda c: score(c, name, index, address))
        return top if score(top, name, index, address) > 0 else None

    best = pick()
    # Ничего не нашлось или нашлась ликвидированная — ищем по адресу:
    # площадка та же, а организация на ней могла смениться именем.
    weak = best is None or best.get("status") != "действующее" or not address_agrees(
        best, index, address
    )
    if search is not None and weak:
        for candidate_inn in by_address(search, clean_name(name), index, address):
            for u in (unpack(x) for x in dd.by_inn(candidate_inn)):
                if u["inn"]:
                    seen.setdefault(u["inn"] + u["kpp"], u)
        best = pick()

    if best is None:
        return None, "в DaData не найдено"

    notes = []
    if inn and best["inn"] != inn:
        owner = next((u["name_short"] for u in by_inn if u["inn"] == inn), "")
        notes.append(
            f"ИНН в файле ({inn}) принадлежит другой организации"
            + (f" — {owner}" if owner else "")
        )
    elif not inn:
        notes.append("ИНН в файле отсутствовал")
    return best, "; ".join(notes)
