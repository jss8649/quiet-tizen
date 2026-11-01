#!/bin/sh
set -eu
name=${1:?backup name}; key=${2:?key}
case "$name" in quiet-home-s90f-keymap-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
case "$key" in XF86[A-Za-z0-9]*) ;; *) exit 2;; esac
case "$key" in *[!A-Za-z0-9]*) exit 2;; esac
DB=/opt/dbspace/.app-context.db
D=/opt/usr/share/quiet-tizen-backups/$name
test ! -e "$D"
test "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = ok
mkdir -m 700 "$D"
sqlite3 "$DB" ".backup '$D/app-context.db'"
test "$(sqlite3 "$D/app-context.db" 'PRAGMA integrity_check;')" = ok
chmod 600 "$D/app-context.db"
echo "Rows matching $key before delete:"
sqlite3 -separator '|' "$DB" "SELECT quote(appid),quote(key),quote(longpress),quote(override),quote(on_selector),quote(request),quote(target_selector),quote(args) FROM key_filter WHERE key='$key';" > "$D/removed-rows.txt"
cat "$D/removed-rows.txt"
removed=$(wc -l < "$D/removed-rows.txt")
before=$(sqlite3 "$DB" 'SELECT count(*) FROM key_filter;')
sqlite3 -cmd '.timeout 8000' "$DB" "DELETE FROM key_filter WHERE key='$key';"
after=$(sqlite3 "$DB" 'SELECT count(*) FROM key_filter;')
test "$after" = "$((before - removed))"
test "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = ok
echo "rows $before -> $after (removed $removed matching $key)"
echo "Full backup: $D/app-context.db"
echo "Removed-row record: $D/removed-rows.txt"
