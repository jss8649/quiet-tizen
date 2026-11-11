#!/bin/sh
# Restore light-shell registry flags with that phase's generated restore.sh first.
set -eu
test "$(id -u)" = 0
name=${1:?Settings-bridge snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
Q=/opt/usr/apps/com.samsung.tv.quicklaunch
test -s "$D/QuickLaunch-before.dll"
test -s "$D/.app-context.db"
sha256sum -c "$D/installed-bridge.sha256"
for database in /opt/dbspace/.app-context.db "$D/.app-context.db"; do
    [ "$(sqlite3 -readonly "$database" "SELECT count(*) FROM key_filter WHERE appid='com.samsung.tv.quicklaunch' AND key='XF86More';")" -ge 1 ]
    [ "$(sqlite3 -readonly "$database" "SELECT count(*) FROM key_filter WHERE appid='org.tizen.menu' AND key='XF86SysMenu';")" -ge 1 ]
done
sqlite3 -bail /opt/dbspace/.app-context.db <<SQL
ATTACH '$D/.app-context.db' AS before;
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)>=1 FROM key_filter WHERE appid='com.samsung.tv.quicklaunch' AND key='XF86More'
AND target_selector='package:com.samsung.tv.AICompanionUI' AND args='quiet_page:settings __K_SPLASH_SCREEN:LA_UI_VR_TRANSPARENT';
INSERT INTO guard SELECT count(*)>=1 FROM key_filter WHERE appid='org.tizen.menu' AND key='XF86SysMenu'
AND target_selector='package:com.samsung.tv.AICompanionUI' AND args='quiet_page:settings __K_SPLASH_SCREEN:LA_UI_VR_TRANSPARENT';
INSERT INTO guard SELECT NOT EXISTS (SELECT 1 FROM key_filter
WHERE ((appid='com.samsung.tv.quicklaunch' AND key='XF86More') OR (appid='org.tizen.menu' AND key='XF86SysMenu'))
AND NOT (target_selector='package:com.samsung.tv.AICompanionUI' AND args='quiet_page:settings __K_SPLASH_SCREEN:LA_UI_VR_TRANSPARENT'));
UPDATE key_filter SET target_selector=(SELECT old.target_selector FROM before.key_filter old WHERE old.appid=key_filter.appid AND old.key=key_filter.key),
args=(SELECT old.args FROM before.key_filter old WHERE old.appid=key_filter.appid AND old.key=key_filter.key)
WHERE (appid='com.samsung.tv.quicklaunch' AND key='XF86More') OR (appid='org.tizen.menu' AND key='XF86SysMenu');
DROP TABLE guard;
COMMIT;
SQL
app_launcher -u 5001 -k com.samsung.tv.quicklaunch || true
cp -a "$D/QuickLaunch-before.dll" "$Q/bin/QuickLaunch.dll"
chsmack -a User::Pkg::com.samsung.tv.quicklaunch::RO "$Q/bin/QuickLaunch.dll"
if [ -d "$D/quicklaunch-native-image" ]; then
    test ! -e "$Q/bin/.native_image"
    cp -a "$D/quicklaunch-native-image" "$Q/bin/.native_image"
fi
vconftool set -f -t int memory/appfw/app_context_db_change 1
echo 'Original settings routing and QuickLaunch restored. Restart after all restoration steps finish.'
