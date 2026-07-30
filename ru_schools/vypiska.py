# -*- coding: utf-8 -*-
"""Разбор официальной выписки из ЕГРЮЛ (PDF) в структурированные поля.

Выписка свёрстана как таблица «№ | Наименование показателя | Значение».
Значения многострочные, поэтому разбор идёт по позиции колонки значения.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

HAS_PDFTOTEXT = shutil.which("pdftotext") is not None

# Коды ОКВЭД общего образования (ОКВЭД2, ОК 029-2014).
GENERAL_EDU_OKVED = {"85.12", "85.13", "85.14"}

_ROW_RE = re.compile(r"^(\s{0,8})(\d{1,3})(\s+)(\S.*?)(\s\s+)(\S.*)$")
_ROW_NOVAL_RE = re.compile(r"^(\s{0,8})(\d{1,3})(\s+)(\S.*)$")

# Показатели, которые встречаются в выписке без собственного номера строки.
_SUBLABELS = ("фамилия", "имя", "отчество", "инн", "должность", "грн")
_FOOTER_RE = re.compile(
    r"^\s*(Выписка из ЕГРЮЛ|\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\s+ОГРН|Страница \d+ из \d+)"
)


@dataclass
class Row:
    num: str
    label: str
    value: str
    value_col: int
    section: str
    label_col: int = 0


@dataclass
class Vypiska:
    inn: str = ""
    kpp: str = ""
    ogrn: str = ""
    name_full: str = ""
    name_short: str = ""
    address: str = ""
    postal_code: str = ""
    region: str = ""
    district: str = ""
    city: str = ""
    settlement: str = ""
    street: str = ""
    head_post: str = ""
    head_name: str = ""
    head_inn: str = ""
    okved_main: str = ""
    okved_main_name: str = ""
    okved_extra: List[str] = field(default_factory=list)
    status: str = ""
    reg_date: str = ""
    license_no: str = ""

    @property
    def is_general_school(self) -> bool:
        """Организация общего образования (начальное/основное/среднее)."""
        if self.okved_main in GENERAL_EDU_OKVED:
            return True
        return any(c in GENERAL_EDU_OKVED for c in self.okved_extra)


def pdf_to_text(pdf: bytes) -> str:
    """Текстовый слой выписки. Требуется poppler-utils (pdftotext)."""
    if not HAS_PDFTOTEXT:
        raise RuntimeError("не найден pdftotext — установите poppler-utils")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as fh:
        fh.write(pdf)
        fh.flush()
        out = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", fh.name, "-"],
            capture_output=True,
            timeout=180,
        )
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext вернул {out.returncode}: {out.stderr[:200]!r}")
    return out.stdout.decode("utf-8", errors="replace")


def parse_rows(text: str) -> List[Row]:
    rows: List[Row] = []
    # Заголовки идут «лесенкой» (раздел + уточнение), поэтому держим окно.
    headers: List[str] = []
    section = ""
    cur: Optional[Row] = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if _FOOTER_RE.match(line):
            cur = None
            continue

        m = _ROW_RE.match(line)
        if m:
            label_col = len(m.group(1)) + len(m.group(2)) + len(m.group(3))
            value_col = label_col + len(m.group(4)) + len(m.group(5))
            cur = Row(
                m.group(2), m.group(4).strip(), m.group(6).strip(), value_col, section, label_col
            )
            rows.append(cur)
            continue

        m = _ROW_NOVAL_RE.match(line)
        if m and cur is None:
            label_col = len(m.group(1)) + len(m.group(2)) + len(m.group(3))
            cur = Row(m.group(2), m.group(4).strip(), "", 10 ** 6, section, label_col)
            rows.append(cur)
            continue

        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if cur is not None and cur.value_col < 10 ** 5:
            if abs(indent - cur.value_col) <= 3:
                cur.value = (cur.value + " " + stripped).strip()
                continue
            if abs(indent - cur.label_col) <= 3:
                head = line[: max(0, cur.value_col - 4)].strip()
                tail = line[max(0, cur.value_col - 4):].strip()
                if head and tail:
                    if head.lower().startswith(_SUBLABELS):
                        # Безномерной подпункт блока (Имя / Отчество и т.п.).
                        cur = Row(cur.num, head, tail, cur.value_col, section, cur.label_col)
                        rows.append(cur)
                    else:
                        # Перенос сразу и в показателе, и в значении.
                        cur.label = (cur.label + " " + head).strip()
                        cur.value = (cur.value + " " + tail).strip()
                elif head:
                    cur.label = (cur.label + " " + head).strip()
                elif tail:
                    cur.value = (cur.value + " " + tail).strip()
                continue

        # Центрированный заголовок раздела.
        if indent > 8:
            headers.append(stripped)
            section = " | ".join(headers[-3:])
            cur = None

    return rows


def parse_text(text: str) -> Vypiska:
    rows = parse_rows(text)
    v = Vypiska()

    v.name_full = _first(rows, "Полное наименование на русском")
    v.name_short = _first(rows, "Сокращенное наименование на русском")
    v.address = _clean(_first(rows, "Адрес юридического лица"))
    v.postal_code = _first(rows, "Почтовый индекс") or _postal(v.address)
    v.region = _first(rows, "Субъект Российской Федерации")
    v.district = _first(rows, "Район (улус")
    v.city = _first(rows, "Город (волость")
    v.settlement = _first(rows, "Населенный пункт")
    v.street = _first(rows, "Улица (проспект")
    v.reg_date = _first(rows, "Дата регистрации") or _first(rows, "Дата присвоения ОГРН")
    v.license_no = _first(rows, "Серия и номер лицензии")

    _fill_person(rows, v)
    _fill_okved(rows, v)
    _fill_address_parts(v)

    m = re.search(r"ИНН\s*((?:\d\s*){10,12})", text)
    if m:
        v.inn = re.sub(r"\s", "", m.group(1))[:12]
    m = re.search(r"ОГРН\s*((?:\d\s*){13,15})", text)
    if m:
        v.ogrn = re.sub(r"\s", "", m.group(1))[:15]
    kpp = _first(rows, "КПП")
    if kpp:
        v.kpp = re.sub(r"\D", "", kpp)[:9]

    terminated = any(
        "прекращени" in r.section.lower() and "юридического лица" in r.section.lower()
        for r in rows
    )
    v.status = "прекратила деятельность" if terminated else "действующая"
    return v


def parse_pdf(pdf: bytes) -> Vypiska:
    return parse_text(pdf_to_text(pdf))


# --- вспомогательные разборщики ------------------------------------------------


def _fill_person(rows: List[Row], v: Vypiska) -> None:
    """Руководитель — блок «Сведения о лице, имеющем право без доверенности…»."""
    idx = None
    for i, r in enumerate(rows):
        if "имеющем право без доверенности" in r.section.lower():
            idx = i
            break
    scope = rows[idx:] if idx is not None else rows
    fam = nam = otch = ""
    for r in scope:
        low = r.label.lower()
        if not fam and low.startswith("фамилия"):
            fam = r.value
        elif not nam and low.startswith("имя"):
            nam = r.value
        elif not otch and low.startswith("отчество"):
            otch = r.value
        elif not v.head_post and low.startswith("должность"):
            v.head_post = _title_post(r.value)
        elif not v.head_inn and low.startswith("инн") and re.fullmatch(r"\d{12}", r.value or ""):
            v.head_inn = r.value
        if fam and nam and v.head_post:
            break
    v.head_name = " ".join(p.title() for p in (fam, nam, otch) if p).strip()


def _fill_okved(rows: List[Row], v: Vypiska) -> None:
    extra = []
    for r in rows:
        if not r.label.lower().startswith("код и наименование вида деятельности"):
            continue
        m = re.match(r"(\d{2}(?:\.\d{1,2}){0,2})\s*(.*)", r.value)
        if not m:
            continue
        code, name = m.group(1), _clean(m.group(2))
        if "основном виде" in r.section.lower() and not v.okved_main:
            v.okved_main, v.okved_main_name = code, name
        else:
            extra.append(code)
    if not v.okved_main and extra:
        v.okved_main = extra[0]
    v.okved_extra = sorted(set(extra))


_REGION_RE = re.compile(
    r"(ОБЛАСТЬ|КРАЙ|РЕСПУБЛИКА|АВТОНОМН\w*\s+ОКРУГ|АВТОНОМНАЯ\s+ОБЛАСТЬ|Г\.?\s*МОСКВА"
    r"|Г\.?\s*САНКТ-ПЕТЕРБУРГ|Г\.?\s*СЕВАСТОПОЛЬ|ЧУВАШСКАЯ|УДМУРТСКАЯ|КАБАРДИНО|КАРАЧАЕВО)",
    re.I,
)
_CITY_RE = re.compile(r"^(Г|ГОРОД|Г\.)[\s.]", re.I)
_SETTLE_RE = re.compile(
    r"^(С|СЕЛО|П|ПОС|ПГТ|РП|Д|ДЕР|ДЕРЕВНЯ|СТ-ЦА|СТАНИЦА|АУЛ|Х|ХУТОР|СЛ|МКР|УЛУС|НАСЕЛЕННЫЙ)[\s.]",
    re.I,
)
_HOUSE_RE = re.compile(
    r"^(Д|ДОМ|ВЛД|КОРП|КОРПУС|СТР|СТРОЕНИЕ|ПОМЕЩ\w*|КВ|ОФИС|ЛИТ\w*|ЭТАЖ|КОМ)[\s.]*\d",
    re.I,
)
_STREET_RE = re.compile(
    r"^(УЛ|УЛИЦА|ПР-КТ|ПРОСПЕКТ|ПЕР|ПЕРЕУЛОК|Ш|ШОССЕ|ПЛ|ПЛОЩАДЬ|Б-Р|БУЛЬВАР|НАБ"
    r"|НАБЕРЕЖНАЯ|ПРОЕЗД|ТУПИК|ТЕР|ТРАКТ|КВ-Л|МКР|ЛИНИЯ|АЛЛЕЯ|ГОРОДОК)[\s.]",
    re.I,
)


def _fill_address_parts(v: Vypiska) -> None:
    """Достаёт регион/город/улицу, если выписка отдала адрес одной строкой."""
    if not v.address:
        return
    parts = [p.strip() for p in v.address.split(",") if p.strip()]
    for p in parts:
        if re.fullmatch(r"\d{6}", p):
            v.postal_code = v.postal_code or p
            continue
        if not v.region and _REGION_RE.search(p) and not _CITY_RE.match(p):
            v.region = p
            continue
        if not v.city and _CITY_RE.match(p):
            v.city = p
            continue
        if _HOUSE_RE.match(p):
            continue
        if not v.settlement and _SETTLE_RE.match(p):
            v.settlement = p
            continue
        if not v.street and _STREET_RE.match(p):
            v.street = p
            continue
    # Города федерального значения одновременно и регион, и город.
    if not v.city and v.region and re.search(r"МОСКВА|САНКТ-ПЕТЕРБУРГ|СЕВАСТОПОЛЬ", v.region, re.I):
        v.city = v.region


def _first(rows: List[Row], label: str) -> str:
    low = label.lower()
    for r in rows:
        if r.label.lower().startswith(low) and r.value:
            return _clean(r.value)
    return ""


def _title_post(value: str) -> str:
    value = _clean(value)
    return value.capitalize() if value.isupper() else value


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _postal(addr: str) -> str:
    m = re.match(r"\s*(\d{6})\b", addr or "")
    return m.group(1) if m else ""
