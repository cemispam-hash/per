# -*- coding: utf-8 -*-
"""Сверка реквизитов организаций по DaData.

DaData отдаёт сведения ЕГРЮЛ в разобранном виде: действующее
наименование, ИНН, КПП, юридический адрес с индексом и состояние
организации. Для актуализации это надёжнее поиска: в исходных списках
названия устаревают, а ИНН иногда стоит вовсе от другой организации.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional

from ru_schools.http_client import HttpClient

log = logging.getLogger(__name__)

CREDENTIALS_FILE = "data/dadata.txt"
FIND_BY_ID = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
SUGGEST = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"


def credentials(path: str = CREDENTIALS_FILE) -> str:
    """API-ключ: из окружения либо из файла «ключ:секрет»."""
    token = os.environ.get("DADATA_TOKEN", "")
    if not token and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    token = line.split(":")[0].strip()
                    break
    return token


STATUS_RU = {
    "ACTIVE": "действующее",
    "LIQUIDATING": "в процессе ликвидации",
    "LIQUIDATED": "ликвидировано",
    "REORGANIZING": "в процессе реорганизации",
    "BANKRUPT": "банкротство",
}


class DaData:
    def __init__(self, token: Optional[str] = None):
        self.token = token or credentials()
        if not self.token:
            raise RuntimeError("не задан ключ DaData (data/dadata.txt)")
        self.http = HttpClient(rate=5, timeout=20, retries=3)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Token " + self.token,
        }

    def _post(self, url: str, payload: dict) -> List[dict]:
        resp = self.http.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers=self.headers)
        if resp.status_code != 200:
            log.warning("DaData ответила %s на %s", resp.status_code, payload)
            return []
        try:
            return resp.json().get("suggestions", [])
        except ValueError:
            return []

    def by_inn(self, inn: str) -> List[dict]:
        return self._post(FIND_BY_ID, {"query": inn, "count": 5})

    def by_name(self, name: str, count: int = 10) -> List[dict]:
        return self._post(SUGGEST, {"query": name, "count": count})


def unpack(item: dict) -> Dict[str, str]:
    """Плоские поля из ответа DaData."""
    d = item.get("data", {})
    address = d.get("address") or {}
    adata = address.get("data") or {}
    state = d.get("state") or {}
    mgmt = d.get("management") or {}
    name = d.get("name") or {}
    return {
        "name_short": name.get("short_with_opf") or item.get("value") or "",
        "name_full": name.get("full_with_opf") or "",
        "inn": d.get("inn") or "",
        "kpp": d.get("kpp") or "",
        "ogrn": d.get("ogrn") or "",
        "postal_code": adata.get("postal_code") or "",
        "address": address.get("unrestricted_value") or address.get("value") or "",
        "region": adata.get("region_with_type") or "",
        "city": adata.get("city_with_type") or adata.get("settlement_with_type") or "",
        "status": STATUS_RU.get(state.get("status") or "", state.get("status") or ""),
        "liquidation_date": _date(state.get("liquidation_date")),
        "head_name": mgmt.get("name") or "",
        "head_post": mgmt.get("post") or "",
        "branch_type": d.get("branch_type") or "",
        "okved": d.get("okved") or "",
    }


def _date(ms) -> str:
    if not ms:
        return ""
    return time.strftime("%d.%m.%Y", time.gmtime(ms / 1000))


_NOISE = re.compile(
    r'(центральный[^\S\n]+оф(?:ис)?\.?|филиал|представительство|обособленное[^\S\n]+подразделение)',
    re.I,
)
_QUOTES = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"'})


def clean_name(name: str) -> str:
    """Наименование без пометок вроде «Центральный оф.» — для поиска."""
    out = _NOISE.sub(" ", (name or "").translate(_QUOTES))
    return re.sub(r"\s+", " ", out).strip(" .,")
