#!/usr/bin/env bash
# Сбор контактов школ — отдельным процессом от основного сбора.
#
# Контакты идут по своим хостам (поиск и сайты школ) и за лимиты ФНС не
# конкурируют, поэтому ждать очереди внутри общего круга незачем: там
# партия выписок занимает часы, и до контактов дело не доходило вовсе.
#
# Поиск платный, поэтому цикл останавливается, когда на счету остаётся
# меньше MIN_BALANCE — не дожидаясь, пока запросы начнут отвергаться.
set -u

cd "$(dirname "$0")"
DB="${DB:-data/schools.db}"
LOG="${LOG:-data/contacts.log}"
CHUNK="${CHUNK:-300}"
WORKERS="${WORKERS:-8}"
MIN_BALANCE="${MIN_BALANCE:-3}"
PROVIDERS="${PROVIDERS:-search}"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

balance() {
    local user key
    IFS=: read -r user key < <(grep -v '^#' data/xmlriver.txt | head -1)
    curl -sS --max-time 30 \
        "https://xmlriver.com/api/get_balance/?user=${user}&key=${key}" 2>/dev/null
}

say "=== сбор контактов (партия $CHUNK, потоков $WORKERS) ==="

while true; do
    left=$(python3 -c "
import sqlite3
c = sqlite3.connect('$DB')
print(len(c.execute('''
    SELECT d.inn FROM details d
    LEFT JOIN contacts k ON k.inn = d.inn
    WHERE k.inn IS NULL AND d.is_school = 1
''').fetchall()))
" 2>/dev/null || echo 0)

    if [ "$left" = "0" ]; then
        say "контакты собраны по всем школам"
        break
    fi

    bal=$(balance)
    say "осталось школ: $left, баланс поиска: ${bal:-неизвестен} ₽"
    if [ -n "$bal" ] && awk "BEGIN{exit !($bal < $MIN_BALANCE)}"; then
        say "баланс поиска исчерпан — пополните счёт xmlriver и запустите снова"
        break
    fi

    before=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from contacts').fetchone()[0])")
    python3 -u -m ru_schools.cli --db "$DB" --rate 3 \
        contacts --limit "$CHUNK" --workers "$WORKERS" --providers $PROVIDERS >> "$LOG" 2>&1
    after=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from contacts').fetchone()[0])")

    with_mail=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute(\"select count(*) from contacts where email<>''\").fetchone()[0])")
    say "обработано за партию: $((after - before)); всего с почтой: $with_mail"

    if [ "$after" = "$before" ]; then
        say "партия не дала результата — пауза 5 минут"
        sleep 300
    fi
done
