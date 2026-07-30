# -*- coding: utf-8 -*-
"""Командный интерфейс парсера школ России."""
from __future__ import annotations

import argparse
import logging
import sys

from . import export as export_mod
from . import pipeline
from .egrul import SCHOOL_QUERIES
from .http_client import HttpClient
from .proxies import build_lanes, check_lanes, load_proxies
from .regions import ALL_REGION_CODES
from .store import Store

DEFAULT_DB = "data/schools.db"
DEFAULT_SSHR = "data/raw/sshr.zip"


def _logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ru-schools",
        description="Сбор открытых сведений о школах России (ЕГРЮЛ ФНС и другие открытые данные)",
    )
    p.add_argument("--db", default=DEFAULT_DB, help="файл базы SQLite")
    p.add_argument("--rate", type=float, default=0.7, help="запросов в секунду к источникам")
    p.add_argument(
        "--proxies",
        default=None,
        help="файл со списком прокси (по умолчанию data/proxies.txt, если он есть)",
    )
    p.add_argument(
        "--no-direct",
        action="store_true",
        help="не использовать прямое соединение, только прокси",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="этап 1: поиск школ в ЕГРЮЛ")
    d.add_argument("--regions", nargs="*", default=None, help="коды регионов (по умолчанию все)")
    d.add_argument("--queries", nargs="*", default=None, help="поисковые запросы")
    d.add_argument("--max-pages", type=int, default=250)

    det = sub.add_parser("details", help="этап 2: выписки из ЕГРЮЛ (адрес, ОКВЭД, директор)")
    det.add_argument("--limit", type=int, default=None)
    det.add_argument("--workers", type=int, default=4)

    st = sub.add_parser("staff", help="этап 3: численность работников (открытые данные ФНС)")
    st.add_argument("--zip", dest="zip_path", default=DEFAULT_SSHR)

    c = sub.add_parser("contacts", help="этап 4: e-mail и телефоны")
    c.add_argument("--limit", type=int, default=None)
    c.add_argument("--workers", type=int, default=4)
    c.add_argument("--providers", nargs="*", default=None, help="busgov saby osm site")

    e = sub.add_parser("export", help="выгрузка результата")
    e.add_argument("--csv", default="data/schools.csv")
    e.add_argument("--jsonl", default="data/schools.jsonl")
    e.add_argument("--xlsx", default=None)
    e.add_argument("--all", action="store_true", help="включая организации без признака школы")

    a = sub.add_parser("run", help="все этапы подряд")
    a.add_argument("--regions", nargs="*", default=None)
    a.add_argument("--workers", type=int, default=4)
    a.add_argument("--zip", dest="zip_path", default=DEFAULT_SSHR)
    a.add_argument("--skip-contacts", action="store_true")

    sub.add_parser("stats", help="статистика по базе")
    sub.add_parser("regions", help="список кодов регионов")
    sub.add_parser("todo", help="сколько работы осталось: поиск, выписки, контакты")

    r = sub.add_parser("restore", help="восстановить базу из снимка data/state.sql.gz")
    r.add_argument("--snapshot", default="data/state.sql.gz")
    return p


def _todo(store: Store) -> tuple:
    """(незавершённых поисковых запросов, выписок, контактов)."""
    done = {
        r[0]
        for r in store.conn.execute("SELECT key FROM progress WHERE value='done'")
    }
    left_discover = sum(
        1
        for reg in ALL_REGION_CODES
        for q in SCHOOL_QUERIES
        if f"discover:{reg}:{q}" not in done
    )
    rest = store.remaining()
    return left_discover, rest["details"], rest["contacts"]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _logging(args.verbose)

    if args.cmd == "restore":
        import gzip
        import sqlite3

        conn = sqlite3.connect(args.db)
        with gzip.open(args.snapshot, "rt", encoding="utf-8") as fh:
            conn.executescript(fh.read())
        conn.commit()
        conn.close()
        print(f"база {args.db} восстановлена из {args.snapshot}")
        return 0

    if args.cmd == "regions":
        from .regions import region_name

        for code in ALL_REGION_CODES:
            print(f"{code}  {region_name(code)}")
        return 0

    store = Store(args.db)
    http = HttpClient(rate=args.rate)

    # Каналы поднимаются только для сетевых этапов и только если прокси
    # заданы: проверка каналов сама ходит в сеть, а todo/export к ней
    # обращаться не должны.
    lanes = None
    if args.cmd in ("discover", "details", "run"):
        proxy_list = load_proxies(args.proxies)
        if proxy_list:
            lanes = check_lanes(
                build_lanes(args.rate, proxy_list, include_direct=not args.no_direct)
            )

    if args.cmd == "discover":
        n = pipeline.discover(
            store, http, args.regions, args.queries, args.max_pages, lanes=lanes
        )
        print(f"новых организаций: {n}")
    elif args.cmd == "details":
        n = pipeline.fetch_details(store, http, args.limit, args.workers, lanes=lanes)
        print(f"разобрано выписок: {n}")
    elif args.cmd == "staff":
        n = pipeline.fetch_staff(store, http, args.zip_path)
        print(f"проставлена численность: {n}")
    elif args.cmd == "contacts":
        n = pipeline.fetch_contacts(store, http, args.limit, args.workers, args.providers)
        print(f"обработано организаций: {n}")
    elif args.cmd == "export":
        only = not args.all
        if args.csv:
            print(f"CSV:   {args.csv} — {export_mod.to_csv(store, args.csv, only)} строк")
        if args.jsonl:
            print(f"JSONL: {args.jsonl} — {export_mod.to_jsonl(store, args.jsonl, only)} строк")
        if args.xlsx:
            print(f"XLSX:  {args.xlsx} — {export_mod.to_xlsx(store, args.xlsx, only)} строк")
    elif args.cmd == "run":
        pipeline.discover(store, http, args.regions, lanes=lanes)
        pipeline.fetch_details(store, http, workers=args.workers, lanes=lanes)
        pipeline.fetch_staff(store, http, args.zip_path)
        if not args.skip_contacts:
            pipeline.fetch_contacts(store, http, workers=args.workers)
        export_mod.to_csv(store, "data/schools.csv")
        export_mod.to_jsonl(store, "data/schools.jsonl")
    elif args.cmd == "stats":
        for k, v in store.stats().items():
            print(f"{k:22}: {v}")
    elif args.cmd == "todo":
        # Формат разбирается скриптом сбора, менять с осторожностью.
        print("%d %d %d" % _todo(store))
        store.close()
        return 0

    if args.cmd not in ("stats", "regions"):
        print("--- итог ---")
        for k, v in store.stats().items():
            print(f"{k:22}: {v}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
