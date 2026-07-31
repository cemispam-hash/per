#!/usr/bin/env bash
# Непрерывный сбор до полного завершения: поиск в ЕГРЮЛ → выписки →
# численность → контакты → выгрузка. Скрипт возобновляемый: состояние
# лежит в SQLite, поэтому его можно останавливать и запускать сколько угодно.
#
# Цикл крутится, пока не будет собрано всё: незавершённые запросы
# повторяются, недоступность сервиса переживается паузой. Организации,
# упавшие MAX_ATTEMPTS раз подряд, из очереди выбывают — иначе завершения
# не дождаться.
set -u

cd "$(dirname "$0")"
DB="${DB:-data/schools.db}"
RATE="${RATE:-0.7}"
# Пять потоков дают около восемнадцати выписок в минуту против
# тринадцати на двух; дальше упирается в лимиты самой ФНС.
WORKERS="${WORKERS:-5}"
LOG="${LOG:-data/collect.log}"
SSHR="${SSHR:-data/raw/sshr2019.zip}"
DONE_MARKER="${DONE_MARKER:-data/COLLECT_DONE}"
IDLE_SLEEP="${IDLE_SLEEP:-600}"
# Выписки — узкое место по объёму: на каждую организацию три
# запроса, тогда как весь поиск укладывается в тысячи страниц.
# Поэтому круг перекошен в их пользу.
DISCOVER_CHUNK="${DISCOVER_CHUNK:-20}"
DETAILS_CHUNK="${DETAILS_CHUNK:-6000}"
CONTACTS_CHUNK="${CONTACTS_CHUNK:-500}"
CONTACTS_WORKERS="${CONTACTS_WORKERS:-12}"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
todo() { python3 -m ru_schools.cli --db "$DB" todo 2>/dev/null || echo "-1 -1 -1"; }

# Выгрузка результата во все форматы; Excel — основной для заказчика.
export_all() {
    python3 -u -m ru_schools.cli --db "$DB" export \
        --csv data/schools.csv --jsonl data/schools.jsonl \
        --xlsx data/schools.xlsx >> "$LOG" 2>&1
}

# Выгрузки и снимок остаются на диске; в git их отправляют вручную.
# Автокоммиты из фонового скрипта GitHub всё равно помечал как Unverified,
# и после каждой партии данных приходилось переписывать вершину ветки.
commit_data() {
    say "выгрузка обновлена ($1) — файлы в data/, коммит вручную"
}

# Снимок базы, чтобы сбор можно было продолжить на чистой машине.
# Файл тяжёлый, поэтому обновляется редко — раз в COMMIT_EVERY выписок.
COMMIT_EVERY="${COMMIT_EVERY:-10000}"
SNAPSHOT_ORGS="${SNAPSHOT_ORGS:-10000}"
last_commit=0
last_snapshot_orgs=0
snapshot() {
    python3 - "$DB" <<'PY'
import gzip, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
with gzip.open("data/state.sql.gz", "wt", encoding="utf-8") as fh:
    for line in conn.iterdump():
        fh.write(line + "\n")
PY
    say "снимок состояния обновлён ($(du -h data/state.sql.gz | cut -f1))"
}

say "=== запуск сбора (rate=$RATE, workers=$WORKERS) ==="
round=0

while true; do
    round=$((round + 1))
    read -r left_discover left_details left_contacts <<< "$(todo)"
    say "круг $round: осталось поиск=$left_discover выписок=$left_details контактов=$left_contacts"

    if [ "$left_discover" = "0" ] && [ "$left_details" = "0" ] && [ "$left_contacts" = "0" ]; then
        say "=== собрано всё ==="
        python3 -u -m ru_schools.cli --db "$DB" staff --zip "$SSHR" >> "$LOG" 2>&1
        export_all
        snapshot
        commit_data "сбор завершён"
        python3 -m ru_schools.cli --db "$DB" stats | tee -a "$LOG"
        date > "$DONE_MARKER"
        break
    fi

    progressed=0

    # Снимок по мере роста перечня: до первых выписок он иначе не делался
    # бы вовсе, и потеря контейнера стоила бы всего собранного поиска.
    orgs=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from orgs').fetchone()[0])")
    if [ $((orgs - last_snapshot_orgs)) -ge "$SNAPSHOT_ORGS" ]; then
        last_snapshot_orgs=$orgs
        snapshot
        commit_data "перечень организаций — $orgs"
    fi

    # Этап 1: перечень школ.
    if [ "$left_discover" != "0" ]; then
        say "поиск в ЕГРЮЛ ($left_discover запросов осталось)"
        # Заход ограничен, чтобы выписки не ждали конца всего поиска
        # и таблица начала наполняться раньше.
        python3 -u -m ru_schools.cli --db "$DB" --rate "$RATE" \
            discover --max-queries "$DISCOVER_CHUNK" >> "$LOG" 2>&1
        read -r now_discover _ _ <<< "$(todo)"
        [ "$now_discover" != "$left_discover" ] && progressed=1
    fi

    # Этап 2: выписки из ЕГРЮЛ.
    if [ "$left_details" != "0" ]; then
        before=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from details').fetchone()[0])")
        python3 -u -m ru_schools.cli --db "$DB" --rate "$RATE" \
            details --limit "$DETAILS_CHUNK" --workers "$WORKERS" >> "$LOG" 2>&1
        after=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from details').fetchone()[0])")
        say "выписок разобрано: $after (+$((after - before)))"
        [ "$after" != "$before" ] && progressed=1
        export_all
        # Выгрузки тяжёлые, поэтому в git они уходят не каждый круг.
        if [ $((after - last_commit)) -ge "$COMMIT_EVERY" ]; then
            last_commit=$after
            snapshot
            commit_data "собрано выписок — $after"
        fi
    fi

    # Этап 3: контакты. Идут по своим хостам — поиску и сайтам школ, — с
    # ФНС за лимит не конкурируют, поэтому ждать конца выписок незачем.
    # Работа сетевая и почти вся в ожидании, отсюда много потоков.
    if [ "$left_contacts" != "0" ]; then
        python3 -u -m ru_schools.cli --db "$DB" --rate 2 \
            contacts --limit "$CONTACTS_CHUNK" --workers "$CONTACTS_WORKERS" >> "$LOG" 2>&1
        progressed=1
    fi

    if [ "$progressed" = "0" ]; then
        say "сервис недоступен или лимит частоты — пауза ${IDLE_SLEEP}с"
        sleep "$IDLE_SLEEP"
    fi
done
