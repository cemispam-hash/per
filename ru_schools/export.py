# -*- coding: utf-8 -*-
"""Выгрузка результата в CSV / JSONL / XLSX."""
from __future__ import annotations

import csv
import json
import os
from typing import List

from .store import Store

COLUMNS = [
    ("inn", "ИНН"),
    ("kpp", "КПП"),
    ("ogrn", "ОГРН"),
    ("name_short", "Наименование краткое"),
    ("name_full", "Наименование полное"),
    ("address", "Адрес юридический"),
    ("postal_code", "Индекс"),
    ("region", "Регион (область)"),
    ("district", "Район"),
    ("city", "Город"),
    ("settlement", "Населённый пункт"),
    ("email", "E-mail"),
    ("phones", "Телефоны"),
    ("website", "Сайт"),
    ("head_post", "Должность руководителя"),
    ("head_name", "ФИО руководителя"),
    ("headcount", "Численность работников"),
    ("headcount_period", "Численность на дату"),
    ("okved_main", "ОКВЭД"),
    ("okved_main_name", "ОКВЭД наименование"),
    ("status", "Статус"),
]


def _row_dict(row) -> dict:
    out = {}
    for key, title in COLUMNS:
        val = row[key] if key in row.keys() else None
        if key == "phones" and val:
            try:
                val = ", ".join(json.loads(val))
            except (ValueError, TypeError):
                pass
        out[title] = "" if val is None else val
    return out


def to_csv(store: Store, path: str, schools_only: bool = True) -> int:
    rows = store.export_rows(schools_only)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[t for _, t in COLUMNS], delimiter=";")
        writer.writeheader()
        for r in rows:
            writer.writerow(_row_dict(r))
    return len(rows)


def to_jsonl(store: Store, path: str, schools_only: bool = True) -> int:
    rows = store.export_rows(schools_only)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            d = dict(r)
            if d.get("phones"):
                try:
                    d["phones"] = json.loads(d["phones"])
                except (ValueError, TypeError):
                    d["phones"] = []
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    return len(rows)


def to_xlsx(store: Store, path: str, schools_only: bool = True) -> int:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("для XLSX нужен openpyxl: pip install openpyxl") from exc

    rows = store.export_rows(schools_only)
    wb = Workbook()
    ws = wb.active
    ws.title = "Школы России"
    titles = [t for _, t in COLUMNS]
    ws.append(titles)
    for r in rows:
        d = _row_dict(r)
        ws.append([d[t] for t in titles])
    ws.freeze_panes = "A2"
    for i, t in enumerate(titles, start=1):
        width = max(12, min(55, len(t) + 4))
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb.save(path)
    return len(rows)
