# -*- coding: utf-8 -*-
"""Численность работников из открытых данных ФНС России.

Набор «Сведения о среднесписочной численности работников организации»
(https://www.nalog.gov.ru/opendata/7707329152-sshr2019/) публикуется ФНС
в открытом доступе на условиях свободного использования.
"""
from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, Iterator, Optional, Tuple

from .http_client import HttpClient

log = logging.getLogger(__name__)

DATASET_PAGE = "https://www.nalog.gov.ru/opendata/7707329152-sshr2019/"
_ZIP_RE = re.compile(r'href="(https://file\.nalog\.ru/opendata/7707329152-sshr2019/[^"]+\.zip)"')


def latest_dataset_url(http: HttpClient) -> str:
    """Ссылка на актуальный архив набора (ФНС обновляет его ежегодно)."""
    html = http.get(DATASET_PAGE).text
    urls = _ZIP_RE.findall(html)
    if not urls:
        raise RuntimeError("не найдена ссылка на архив набора ФНС")
    return urls[0]


def download(http: HttpClient, dest: str, url: Optional[str] = None) -> str:
    url = url or latest_dataset_url(http)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    log.info("скачиваю набор ФНС: %s", url)
    resp = http.get(url, stream=True)
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(1 << 20):
            fh.write(chunk)
    return dest


def iter_headcounts(zip_path: str) -> Iterator[Tuple[str, int, str]]:
    """(ИНН, среднесписочная численность, дата составления) из архива ФНС."""
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.lower().endswith(".xml"):
                continue
            try:
                root = ET.fromstring(z.read(name))
            except ET.ParseError as exc:
                log.warning("не разобран %s: %s", name, exc)
                continue
            for doc in root.iter("Документ"):
                period = doc.get("ДатаСост") or doc.get("ДатаДок") or ""
                inn = ""
                for np in doc.iter("СведНП"):
                    inn = np.get("ИННЮЛ") or ""
                    break
                count = None
                for s in doc.iter("СведССЧР"):
                    raw = s.get("КолРаб")
                    if raw is not None and raw.strip().isdigit():
                        count = int(raw)
                    break
                if inn and count is not None:
                    yield inn, count, period


def load_for(zip_path: str, inns) -> Dict[str, Tuple[int, str]]:
    """Численность только по интересующим ИНН (архив читается потоково)."""
    wanted = set(inns)
    out: Dict[str, Tuple[int, str]] = {}
    for inn, count, period in iter_headcounts(zip_path):
        if inn in wanted:
            out[inn] = (count, period)
    return out
