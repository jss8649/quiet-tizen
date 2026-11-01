#!/bin/sh
set -eu

name=${1:?Backup phase name required}
stage=${2:?Temporary staging directory required}
expected_package_hash=${3:?Expected package hash required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 2;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/quiet-tizen-install-*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI

test "$(sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "SELECT count(*) FROM package_app_info WHERE app_id='com.samsung.tv.AICompanionUI' AND app_component='uiapp' AND app_exec='/opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.dll' AND app_type='dotnet-inhouse' AND app_package_type='tpk' AND app_package_system='false' AND package='com.samsung.tv.AICompanionUI';")" = 1
test "$(sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "SELECT count(*) FROM package_info WHERE package='com.samsung.tv.AICompanionUI' AND package_removable='true' AND package_readonly='false';")" = 1
test "$(stat -c %u:%g "$A/bin/AICompanionUI.dll")" = 201:0
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = fe1cb14b2a0d5994662c6856cee7c4ebe87e6d2b276ada0e080f5160f15b4b5c
test -s "$A/bin/AICompanionUI.runtimeconfig.json"
test -s "$A/AICompanionUI.deps.json"
test -d "$A/res"
test ! -d "$A/res/quiet-home"
test "$(sha256sum "$stage/package-s90f.tar.gz" | cut -d ' ' -f 1)" = "$expected_package_hash"
mkdir -p /opt/usr/share/quiet-tizen-backups
mkdir "$D"
umask 077
for n in .pkgmgr_parser .app-context .webappservice; do
    sqlite3 -readonly "/opt/dbspace/$n.db" ".backup '$D/$n.db'"
    test "$(sqlite3 -readonly "$D/$n.db" 'PRAGMA quick_check;')" = ok
done
for key in db/appfw/home_appid db/appfw/startup_appid db/was/preload_by_country db/menu/autorun_tv_plus; do
    echo "KEY=$key"
    vconftool get "$key"
done > "$D/preferences-before.txt"
/usr/bin/dotnet "$stage/Probe.dll" > "$D/operation-and-sources-before.txt"
cp "$stage/Probe.dll" "$D/Probe.dll"
tar -czf "$D/AICompanionUI-original.tar.gz" -C /opt/usr/apps com.samsung.tv.AICompanionUI
tar -czf "$stage/recovery-bundle.tar.gz" -C /opt/usr/share/quiet-tizen-backups "$name"
chmod 644 "$stage/recovery-bundle.tar.gz"
sha256sum "$stage/recovery-bundle.tar.gz"
echo "Backup ready: $D"
