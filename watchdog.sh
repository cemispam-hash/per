#!/usr/bin/env bash
# Сторож: держит сбор запущенным, пока он не соберёт всё.
# Если run_collect.sh упал (обрыв сети, OOM, что угодно) — поднимает заново.
set -u

cd "$(dirname "$0")"
DONE_MARKER="${DONE_MARKER:-data/COLLECT_DONE}"
LOG="${LOG:-data/collect.log}"
RESTART_PAUSE="${RESTART_PAUSE:-30}"

say() { echo "[$(date '+%m-%d %H:%M:%S')] сторож: $*" | tee -a "$LOG"; }

if [ -f "$DONE_MARKER" ]; then
    say "сбор уже завершён ($(cat "$DONE_MARKER")) — нечего делать"
    exit 0
fi

attempt=0
while [ ! -f "$DONE_MARKER" ]; do
    attempt=$((attempt + 1))
    # Осиротевшие после падения процессы продолжают ходить к ЕГРЮЛ и
    # удваивают частоту запросов — снимаем их перед новым запуском.
    pkill -f "ru_schools.cli" 2>/dev/null && sleep 3
    say "запуск сбора, попытка $attempt"
    ./run_collect.sh >> data/supervisor.log 2>&1
    code=$?
    [ -f "$DONE_MARKER" ] && break
    say "сбор завершился с кодом $code, перезапуск через ${RESTART_PAUSE}с"
    sleep "$RESTART_PAUSE"
done

say "сбор завершён полностью"
