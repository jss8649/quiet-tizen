#!/bin/sh
set -eu
name=${1:?backup name}
case "$name" in quiet-home-s90f-keymap-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
test -s "$D/app-context.db"
DB=/opt/dbspace/.app-context.db
cp /opt/dbspace/.app-context.db "$D/app-context.db.live-before-restore"
cp "$D/app-context.db" "$DB"
chown 0:0 "$DB"
test "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = ok
echo "restored full key_filter database from $D/app-context.db"
sqlite3 "$DB" "SELECT count(*) FROM key_filter;"
