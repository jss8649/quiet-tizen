#!/bin/sh
# Restore a launcher preview before Home/startup routing has been changed.
# Input: the unique snapshot phase name used for the preview.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.bixby-promotion
test -s "$D/bixby-promotion-original/bin/BixbyPromotion.dll"
test -s "$D/original-assembly.sha256"
test "$(sha256sum "$D/bixby-promotion-original/bin/BixbyPromotion.dll" | cut -d ' ' -f 1)" = "$(cut -d ' ' -f 1 "$D/original-assembly.sha256")"
test "$(vconftool get db/appfw/home_appid)" = "$(sed -n '2p' "$D/preferences-before.txt")"
test "$(vconftool get db/appfw/startup_appid)" = "$(sed -n '4p' "$D/preferences-before.txt")"
before=$(sqlite3 -readonly -separator '|' "$D/.pkgmgr_parser.db" "SELECT app_disable,app_onboot,app_autorestart FROM package_app_info WHERE app_id='com.samsung.tv.bixby-promotion';")
current=$(sqlite3 -readonly -separator '|' /opt/dbspace/.pkgmgr_parser.db "SELECT app_disable,app_onboot,app_autorestart FROM package_app_info WHERE app_id='com.samsung.tv.bixby-promotion';")
test -n "$before"
test -n "$current"
if [ "$current" != "$before" ]; then
    test "$current" = 'false|false|false' || { echo 'Launcher registry flags drifted' >&2; exit 1; }
fi
test ! -e "$D/preview-native-image"
app_launcher -u 5001 -k com.samsung.tv.bixby-promotion || true
if [ -d "$D/home-native-image" ]; then
    if [ -e "$A/bin/.native_image" ]; then mv "$A/bin/.native_image" "$D/preview-native-image"; fi
    cp -a "$D/home-native-image" "$A/bin/.native_image"
fi
cp -a "$D/bixby-promotion-original/bin/BixbyPromotion.dll" "$A/bin/BixbyPromotion.dll"
chsmack -a User::Pkg::com.samsung.tv.bixby-promotion::RO "$A/bin/BixbyPromotion.dll"
sha256sum -c "$D/original-assembly.sha256"
if [ "$current" != "$before" ]; then
sqlite3 -bail /opt/dbspace/.pkgmgr_parser.db <<SQL
ATTACH '$D/.pkgmgr_parser.db' AS before;
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM package_app_info WHERE app_id='com.samsung.tv.bixby-promotion' AND app_disable='false' AND app_onboot='false' AND app_autorestart='false';
UPDATE package_app_info SET
app_disable=(SELECT app_disable FROM before.package_app_info WHERE app_id='com.samsung.tv.bixby-promotion'),
app_onboot=(SELECT app_onboot FROM before.package_app_info WHERE app_id='com.samsung.tv.bixby-promotion'),
app_autorestart=(SELECT app_autorestart FROM before.package_app_info WHERE app_id='com.samsung.tv.bixby-promotion')
WHERE app_id='com.samsung.tv.bixby-promotion';
DROP TABLE guard;
COMMIT;
SQL
fi
echo 'Original launcher assembly restored; Home/startup routing was unchanged.'
