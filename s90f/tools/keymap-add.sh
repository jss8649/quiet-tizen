#!/bin/sh
set -eu
name=${1:?backup name}; key=${2:?key}; appid=${3:?app id}
case "$name" in quiet-home-s90f-keymap-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
case "$key" in XF86[A-Za-z0-9]*) ;; *) exit 2;; esac
case "$key" in *[!A-Za-z0-9]*) exit 2;; esac
case "$appid" in *[!A-Za-z0-9._-]*|"") exit 2;; esac
DB=/opt/dbspace/.app-context.db
D=/opt/usr/share/quiet-tizen-backups/$name
pkg=${appid%%.*}
test -d "/opt/usr/apps/$pkg"
test ! -e "$D"
test "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = ok
before=$(sqlite3 "$DB" 'SELECT count(*) FROM key_filter;')
exists=$(sqlite3 "$DB" "SELECT count(*) FROM key_filter WHERE appid='$appid' AND key='$key';")
test "$exists" = 0
mkdir -m 700 "$D"
sqlite3 "$DB" ".backup '$D/app-context.db'"
test "$(sqlite3 "$D/app-context.db" 'PRAGMA integrity_check;')" = ok
test "$(sqlite3 "$D/app-context.db" 'SELECT count(*) FROM key_filter;')" = "$before"
printf "DELETE FROM key_filter WHERE appid='%s' AND key='%s' AND longpress IS NULL AND override='true' AND on_selector='' AND request='launch' AND target_selector='package:%s' AND args IS NULL;\n" "$appid" "$key" "$appid" > "$D/rollback.sql"
chmod 600 "$D/app-context.db" "$D/rollback.sql"
sqlite3 -cmd '.timeout 8000' "$DB" "INSERT INTO key_filter(appid,key,longpress,override,on_selector,request,target_selector,args) VALUES('$appid','$key',NULL,'true','','launch','package:$appid',NULL);"
after=$(sqlite3 "$DB" 'SELECT count(*) FROM key_filter;')
test "$after" = "$((before + 1))"
test "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = ok
sqlite3 "$DB" "SELECT appid,key,override,request,target_selector FROM key_filter WHERE key='$key';"
echo "rows $before -> $after; rollback: $D/rollback.sql"
