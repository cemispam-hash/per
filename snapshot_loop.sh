#!/usr/bin/env bash
# Снимок состояния в git через равные промежутки.
#
# Контейнер сборки откатывается к состоянию последнего коммита примерно
# раз в час, и всё, что собрано между откатами, пропадает вместе с диском.
# Единственное, что переживает откат, — отправленная в origin ветка,
# поэтому снимок уходит туда сам, не дожидаясь конца сбора.
#
# Возится при этом только таблица контактов: перечень организаций и
# выписки давно собраны и не меняются, а полный снимок с выгрузками — это
# около 90 МБ на круг, и отправка такого объёма раз в десять минут просто
# не успевала пройти (за час доезжал один снимок из шести). Наложение
# лёгкого файла поверх полного делает `restore`.
set -u

cd "$(dirname "$0")"
DB="${DB:-data/schools.db}"
BRANCH="${BRANCH:-claude/russian-schools-parser-nc9nlq}"
EVERY="${EVERY:-600}"
LOG="${LOG:-data/snapshot.log}"
OVERLAY="${OVERLAY:-data/contacts.sql.gz}"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

say "=== снимки контактов в git каждые ${EVERY} с ==="

while true; do
    sleep "$EVERY"

    [ -f "$DB" ] || { say "базы нет — пропускаю круг"; continue; }

    # Пишется во временный файл: оборванный на полуслове дамп уже однажды
    # попал в git и стоил всей собранной партии.
    if ! python3 - "$DB" "$OVERLAY.tmp" <<'PY'
import gzip, sqlite3, sys

db, out = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db)


def lit(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


with gzip.open(out, "wt", encoding="utf-8") as fh:
    fh.write("BEGIN TRANSACTION;\n")
    rows = conn.execute(
        "SELECT inn,email,phones,website,source,fetched_at FROM contacts"
    )
    for row in rows:
        fh.write(
            "INSERT OR REPLACE INTO contacts "
            "(inn,email,phones,website,source,fetched_at) VALUES ("
            + ",".join(lit(v) for v in row)
            + ");\n"
        )
    # Отказы возятся вместе с контактами: по ним считаются попытки, и без
    # них школа, отвалившаяся пять раз, после отката пошла бы по кругу.
    rows = conn.execute(
        "SELECT inn,stage,error,ts FROM failures WHERE stage='contacts'"
    )
    for row in rows:
        fh.write(
            "INSERT INTO failures (inn,stage,error,ts) VALUES ("
            + ",".join(lit(v) for v in row)
            + ");\n"
        )
    fh.write("COMMIT;\n")
PY
    then
        say "снимок не удался — оставляю прежний"
        rm -f "$OVERLAY.tmp"
        continue
    fi
    mv "$OVERLAY.tmp" "$OVERLAY"

    got=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute(\"select count(*) from contacts\").fetchone()[0])" 2>/dev/null || echo "?")

    git add -A "$OVERLAY"
    if git diff --cached --quiet; then
        say "изменений нет — коммит не нужен"
        continue
    fi
    git commit -q -m "Данные: контакты — $got школ" \
        -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

    pushed=0
    for attempt in 1 2 3 4; do
        if git push -u origin "$BRANCH" >> "$LOG" 2>&1; then
            pushed=1
            say "снимок отправлен: контактов $got ($(du -h "$OVERLAY" | cut -f1))"
            break
        fi
        say "push не прошёл (попытка $attempt) — жду"
        sleep $((2 ** attempt))
    done
    [ "$pushed" = "0" ] && say "снимок остался только на диске — откат его потеряет"
done
