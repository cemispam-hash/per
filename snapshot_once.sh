#!/usr/bin/env bash
# Разовый снимок контактов в git — тот же файл, что возит snapshot_loop.sh.
#
# Нужен, когда сбор идёт партиями на переднем плане: контейнер живёт
# минут пятнадцать после конца хода, поэтому собранное отправляется
# сразу, а не по расписанию фонового цикла.
set -eu

cd "$(dirname "$0")"
DB="${DB:-data/schools.db}"
BRANCH="${BRANCH:-claude/russian-schools-parser-nc9nlq}"
OVERLAY="${OVERLAY:-data/contacts.sql.gz}"

python3 - "$DB" "$OVERLAY.tmp" <<'PY'
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
mv "$OVERLAY.tmp" "$OVERLAY"

got=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from contacts').fetchone()[0])")

git add -A "$OVERLAY"
if git diff --cached --quiet; then
    echo "изменений нет — коммит не нужен"
    exit 0
fi
git commit -q -m "Данные: контакты — $got школ" \
    -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

for attempt in 1 2 3 4; do
    if git push -u origin "$BRANCH" > /dev/null 2>&1; then
        echo "отправлено: контактов $got"
        exit 0
    fi
    sleep $((2 ** attempt))
done
echo "push не прошёл — снимок остался на диске" >&2
exit 1
