#!/bin/sh
# Run via tools/tv.py exec --script recipes/snapshot.sh --arg UNIQUE_PHASE_NAME
set -eu
test "$(id -u)" = 0
name=${1:?Give this snapshot a unique phase name}
case "$name" in ''|*[!A-Za-z0-9_-]*) echo 'Invalid snapshot name' >&2; exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.bixby-promotion
umask 077
test ! -e "$D" || { echo 'Snapshot already exists; never overwrite the original.' >&2; exit 1; }
test -s "$A/bin/BixbyPromotion.dll"
test ! -e "$A/res/quiet-home"
mkdir -p "$D"
for name in .pkgmgr_parser .app-context .webappservice; do
    test -f "/opt/dbspace/$name.db"
    sqlite3 -readonly "/opt/dbspace/$name.db" ".backup '$D/$name.db'"
    test "$(sqlite3 -readonly "$D/$name.db" 'PRAGMA quick_check;')" = ok
done
cp -a "$A" "$D/bixby-promotion-original"
tar -czf "$D/bixby-promotion-original.tar.gz" -C "$D" bixby-promotion-original
stat -c '%n|%s|%u:%g|%a' "$A/bin/BixbyPromotion.dll" > "$D/original-metadata.txt"
sha256sum "$A/bin/BixbyPromotion.dll" > "$D/original-assembly.sha256"
test "$(sha256sum "$D/bixby-promotion-original/bin/BixbyPromotion.dll" | cut -d ' ' -f 1)" = "$(cut -d ' ' -f 1 "$D/original-assembly.sha256")"
test -s "$D/bixby-promotion-original.tar.gz"
for key in db/appfw/home_appid db/appfw/startup_appid; do
    vconftool get "$key" >/dev/null
done
for key in db/appfw/home_appid db/appfw/startup_appid \
    db/was/preload_by_country db/menu/autorun_tv_plus \
    db/menu/voice/voice_activated db/menu/voice/wakeupless_status \
    db/si_service/voice_recog_enable db/multi-assistant/prelaunch_mode; do
    printf '%s\n' "$key"
    vconftool get "$key" || printf 'unavailable\n'
done > "$D/preferences-before.txt"
echo "Consistent snapshots: $D"
echo 'Record the main-operation home app with Probe.dll before changing launcher routing.'
