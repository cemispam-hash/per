# -*- coding: utf-8 -*-
"""Хранилище на SQLite: обеспечивает возобновляемость сбора."""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    inn             TEXT PRIMARY KEY,
    kpp             TEXT,
    ogrn            TEXT,
    name_short      TEXT,
    name_full       TEXT,
    head_post       TEXT,
    head_name       TEXT,
    region_code     TEXT,
    region_name     TEXT,
    reg_date        TEXT,
    terminated_date TEXT,
    found_by        TEXT,
    token           TEXT
);

CREATE TABLE IF NOT EXISTS details (
    inn             TEXT PRIMARY KEY,
    kpp             TEXT,
    ogrn            TEXT,
    name_short      TEXT,
    name_full       TEXT,
    address         TEXT,
    postal_code     TEXT,
    region          TEXT,
    district        TEXT,
    city            TEXT,
    settlement      TEXT,
    street          TEXT,
    head_post       TEXT,
    head_name       TEXT,
    okved_main      TEXT,
    okved_main_name TEXT,
    okved_extra     TEXT,
    license_no      TEXT,
    status          TEXT,
    is_school       INTEGER,
    fetched_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
    inn        TEXT PRIMARY KEY,
    email      TEXT,
    phones     TEXT,
    website    TEXT,
    source     TEXT,
    fetched_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS staff (
    inn        TEXT PRIMARY KEY,
    headcount  INTEGER,
    period     TEXT,
    source     TEXT
);

CREATE TABLE IF NOT EXISTS failures (
    inn        TEXT,
    stage      TEXT,
    error      TEXT,
    ts         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS progress (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_orgs_region ON orgs(region_code);
CREATE INDEX IF NOT EXISTS idx_orgs_term   ON orgs(terminated_date);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.commit()

    # --- запись ------------------------------------------------------------
    def add_orgs(self, rows: Iterable) -> int:
        payload = [
            (
                r.inn, r.kpp, r.ogrn, r.name_short, r.name_full, r.head_post,
                r.head_name, r.region_code, r.region_name, r.reg_date,
                r.terminated_date, r.found_by, r.token,
            )
            for r in rows
            if r.inn
        ]
        if not payload:
            return 0
        with self._lock:
            cur = self.conn.executemany(
                """INSERT INTO orgs (inn,kpp,ogrn,name_short,name_full,head_post,head_name,
                       region_code,region_name,reg_date,terminated_date,found_by,token)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(inn) DO UPDATE SET
                       token=excluded.token,
                       kpp=COALESCE(NULLIF(excluded.kpp,''), orgs.kpp),
                       head_post=COALESCE(NULLIF(excluded.head_post,''), orgs.head_post),
                       head_name=COALESCE(NULLIF(excluded.head_name,''), orgs.head_name),
                       region_code=COALESCE(NULLIF(excluded.region_code,''), orgs.region_code)""",
                payload,
            )
            self.conn.commit()
            return cur.rowcount

    def add_details(self, inn: str, v, is_school: bool) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO details
                   (inn,kpp,ogrn,name_short,name_full,address,postal_code,region,district,
                    city,settlement,street,head_post,head_name,okved_main,okved_main_name,
                    okved_extra,license_no,status,is_school)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    inn, v.kpp, v.ogrn, v.name_short, v.name_full, v.address,
                    v.postal_code, v.region, v.district, v.city, v.settlement,
                    v.street, v.head_post, v.head_name, v.okved_main,
                    v.okved_main_name, json.dumps(v.okved_extra, ensure_ascii=False),
                    v.license_no, v.status, int(is_school),
                ),
            )
            self.conn.commit()

    def add_contacts(self, inn: str, email: str, phones: List[str], website: str, source: str) -> None:
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO contacts (inn,email,phones,website,source)
                   VALUES (?,?,?,?,?)""",
                (inn, email or "", json.dumps(phones or [], ensure_ascii=False), website or "", source),
            )
            self.conn.commit()

    def add_staff(self, items: Iterable, period: str, source: str) -> int:
        payload = [(inn, cnt, period, source) for inn, cnt in items]
        if not payload:
            return 0
        with self._lock:
            cur = self.conn.executemany(
                "INSERT OR REPLACE INTO staff (inn,headcount,period,source) VALUES (?,?,?,?)",
                payload,
            )
            self.conn.commit()
            return cur.rowcount

    def add_failure(self, inn: str, stage: str, error: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO failures (inn,stage,error) VALUES (?,?,?)", (inn, stage, str(error)[:500])
            )
            self.conn.commit()

    def set_progress(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO progress (key,value) VALUES (?,?)", (key, str(value))
            )
            self.conn.commit()

    def get_progress(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM progress WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    # --- чтение ------------------------------------------------------------
    def count(self, table: str, where: str = "") -> int:
        sql = f"SELECT COUNT(*) c FROM {table}"
        if where:
            sql += " WHERE " + where
        return self.conn.execute(sql).fetchone()["c"]

    # Организация, упавшая столько раз подряд, больше не запрашивается —
    # иначе цикл сбора никогда не завершится.
    MAX_ATTEMPTS = 5

    def pending_details(self, limit: Optional[int] = None) -> List[sqlite3.Row]:
        sql = """SELECT o.inn, o.token, o.region_code, o.region_name
                 FROM orgs o
                 LEFT JOIN details d ON d.inn = o.inn
                 LEFT JOIN (SELECT inn, COUNT(*) n FROM failures
                            WHERE stage = 'details' GROUP BY inn) f ON f.inn = o.inn
                 WHERE d.inn IS NULL
                   AND (o.terminated_date IS NULL OR o.terminated_date = '')
                   AND COALESCE(f.n, 0) < ?
                 ORDER BY o.region_code, o.inn"""
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.conn.execute(sql, (self.MAX_ATTEMPTS,)).fetchall()

    def pending_contacts(self, limit: Optional[int] = None) -> List[sqlite3.Row]:
        sql = """SELECT d.inn, d.kpp, d.name_short, d.name_full, d.address,
                        d.city, d.settlement, d.street, d.region
                 FROM details d
                 LEFT JOIN contacts c ON c.inn = d.inn
                 LEFT JOIN (SELECT inn, COUNT(*) n FROM failures
                            WHERE stage = 'contacts' GROUP BY inn) f ON f.inn = d.inn
                 WHERE c.inn IS NULL AND d.is_school = 1
                   AND COALESCE(f.n, 0) < ?"""
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.conn.execute(sql, (self.MAX_ATTEMPTS,)).fetchall()

    def remaining(self) -> Dict[str, int]:
        """Сколько работы осталось на каждом этапе."""
        return {
            "details": len(self.pending_details()),
            "contacts": len(self.pending_contacts()),
        }

    def export_rows(self, schools_only: bool = True) -> List[sqlite3.Row]:
        sql = """
        SELECT
            o.inn                                          AS inn,
            COALESCE(NULLIF(d.kpp,''), o.kpp)              AS kpp,
            COALESCE(NULLIF(d.ogrn,''), o.ogrn)            AS ogrn,
            COALESCE(NULLIF(d.name_short,''), o.name_short) AS name_short,
            COALESCE(NULLIF(d.name_full,''), o.name_full)  AS name_full,
            d.address                                      AS address,
            d.postal_code                                  AS postal_code,
            COALESCE(NULLIF(d.region,''), o.region_name)   AS region,
            d.district                                     AS district,
            d.city                                         AS city,
            d.settlement                                   AS settlement,
            COALESCE(NULLIF(d.head_post,''), o.head_post)  AS head_post,
            COALESCE(NULLIF(d.head_name,''), o.head_name)  AS head_name,
            c.email                                        AS email,
            c.phones                                       AS phones,
            c.website                                      AS website,
            c.source                                       AS contact_source,
            s.headcount                                    AS headcount,
            s.period                                       AS headcount_period,
            d.okved_main                                   AS okved_main,
            d.okved_main_name                              AS okved_main_name,
            d.status                                       AS status,
            o.region_code                                  AS region_code
        FROM orgs o
        LEFT JOIN details  d ON d.inn = o.inn
        LEFT JOIN contacts c ON c.inn = o.inn
        LEFT JOIN staff    s ON s.inn = o.inn
        WHERE (o.terminated_date IS NULL OR o.terminated_date = '')
        """
        if schools_only:
            sql += " AND d.is_school = 1"
        sql += " ORDER BY o.region_code, d.city, o.name_short"
        return self.conn.execute(sql).fetchall()

    def all_inns(self) -> List[str]:
        return [r["inn"] for r in self.conn.execute("SELECT inn FROM orgs")]

    def stats(self) -> Dict[str, int]:
        return {
            "найдено организаций": self.count("orgs"),
            "из них действующих": self.count("orgs", "terminated_date IS NULL OR terminated_date=''"),
            "выписок разобрано": self.count("details"),
            "признаны школами": self.count("details", "is_school=1"),
            "с контактами": self.count("contacts", "email<>'' OR phones<>'[]'"),
            "с численностью": self.count("staff"),
            "ошибок": self.count("failures"),
        }

    def close(self) -> None:
        self.conn.close()
