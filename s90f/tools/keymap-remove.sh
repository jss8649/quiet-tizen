#!/bin/sh
set -eu
key=${1:?key}; appid=${2:?app id}
case "$key" in XF86[A-Za-z0-9]*) ;; *) exit 2;; esac
case "$key" in *[!A-Za-z0-9]*) exit 2;; esac
case "$appid" in *[!A-Za-z0-9._-]*|"") exit 2;; esac
DB=/opt/dbspace/.app-context.db
before=$(sqlite3 "$DB" 'SELECT count(*) FROM key_filter;')
sqlite3 -cmd '.timeout 8000' "$DB" "DELETE FROM key_filter WHERE appid='$appid' AND key='$key' AND longpress IS NULL AND override='true' AND on_selector='' AND request='launch' AND target_selector='package:$appid' AND args IS NULL;"
after=$(sqlite3 "$DB" 'SELECT count(*) FROM key_filter;')
test "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = ok
echo "rows $before -> $after"
sqlite3 "$DB" "SELECT appid,key,override,request FROM key_filter WHERE key='$key';"
