#!/usr/bin/env bash
# Снимок состояния в git через равные промежутки.
#
# Контейнер сборки откатывается к состоянию последнего коммита примерно
# раз в час, и всё, что собрано между откатами, пропадает вместе с диском.
# Единственное, что переживает откат, — отправленная в origin ветка,
# поэтому снимок базы уходит туда сам, не дожидаясь конца сбора.
#
# Интервал заметно короче часа: столько работы максимум теряется при откате.
set -u

cd "$(dirname "$0")"
DB="${DB:-data/schools.db}"
BRANCH="${BRANCH:-claude/russian-schools-parser-nc9nlq}"
EVERY="${EVERY:-900}"
LOG="${LOG:-data/snapshot.log}"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

say "=== снимки в git каждые ${EVERY} с ==="

while true; do
    sleep "$EVERY"

    [ -f "$DB" ] || { say "базы нет — пропускаю круг"; continue; }

    # Снимок пишется во временный файл: оборванный на полуслове дамп
    # уже однажды попал в git и стоил всей собранной партии.
    if ! python3 - "$DB" <<'PY'
import gzip, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
with gzip.open("data/state.sql.gz.tmp", "wt", encoding="utf-8") as fh:
    for line in conn.iterdump():
        fh.write(line + "\n")
PY
    then
        say "снимок не удался — оставляю прежний"
        rm -f data/state.sql.gz.tmp
        continue
    fi
    mv data/state.sql.gz.tmp data/state.sql.gz

    python3 -u -m ru_schools.cli --db "$DB" export \
        --csv data/schools.csv --jsonl data/schools.jsonl \
        --xlsx data/schools.xlsx >> "$LOG" 2>&1

    got=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute(\"select count(*) from contacts\").fetchone()[0])" 2>/dev/null || echo "?")

    git add -A data/state.sql.gz data/schools.csv data/schools.jsonl data/schools.xlsx
    if git diff --cached --quiet; then
        say "изменений нет — коммит не нужен"
        continue
    fi
    git commit -q -m "Данные: снимок состояния — контактов $got" \
        -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

    for attempt in 1 2 3 4; do
        if git push -u origin "$BRANCH" >> "$LOG" 2>&1; then
            say "снимок отправлен: контактов $got"
            break
        fi
        say "push не прошёл (попытка $attempt) — жду"
        sleep $((2 ** attempt))
    done
done
