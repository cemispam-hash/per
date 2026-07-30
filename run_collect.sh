#!/usr/bin/env bash
# Непрерывный сбор: поиск в ЕГРЮЛ → выписки → численность → выгрузка.
# Скрипт возобновляемый: состояние в SQLite, можно останавливать и запускать снова.
set -u

cd "$(dirname "$0")"
DB="${DB:-data/schools.db}"
RATE="${RATE:-0.7}"
WORKERS="${WORKERS:-2}"
LOG="${LOG:-data/collect.log}"
SSHR="${SSHR:-data/raw/sshr2019.zip}"

say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# Этап 1: поиск. Несколько проходов — незавершённые запросы повторяются.
for pass in 1 2 3 4 5; do
    say "поиск в ЕГРЮЛ, проход $pass"
    python3 -u -m ru_schools.cli --db "$DB" --rate "$RATE" discover >> "$LOG" 2>&1
    left=$(python3 - "$DB" <<'PY'
import sqlite3, sys
from ru_schools.regions import ALL_REGION_CODES
from ru_schools.egrul import SCHOOL_QUERIES
c = sqlite3.connect(sys.argv[1])
done = {r[0] for r in c.execute("SELECT key FROM progress WHERE value='done'")}
print(sum(1 for reg in ALL_REGION_CODES for q in SCHOOL_QUERIES
          if f"discover:{reg}:{q}" not in done))
PY
)
    say "не завершено поисковых запросов: $left"
    [ "$left" = "0" ] && break
done

# Этап 2: выписки из ЕГРЮЛ — порциями, с выгрузкой после каждой порции.
while true; do
    before=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from details').fetchone()[0])")
    say "выписки: разобрано $before"
    python3 -u -m ru_schools.cli --db "$DB" --rate "$RATE" details --limit 500 --workers "$WORKERS" >> "$LOG" 2>&1
    after=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from details').fetchone()[0])")
    python3 -u -m ru_schools.cli --db "$DB" export --csv data/schools.csv --jsonl data/schools.jsonl >> "$LOG" 2>&1
    [ "$after" = "$before" ] && { say "новых выписок нет — этап завершён"; break; }
done

# Этап 3: численность работников из открытых данных ФНС.
if [ -f "$SSHR" ]; then
    say "сопоставление численности"
    python3 -u -m ru_schools.cli --db "$DB" staff --zip "$SSHR" >> "$LOG" 2>&1
fi

python3 -u -m ru_schools.cli --db "$DB" export --csv data/schools.csv --jsonl data/schools.jsonl >> "$LOG" 2>&1
say "готово"
python3 -m ru_schools.cli --db "$DB" stats | tee -a "$LOG"
