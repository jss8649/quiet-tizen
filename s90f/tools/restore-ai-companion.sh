#!/bin/sh
set -eu

name=${1:?Backup phase name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
test -s "$D/AICompanionUI-original.tar.gz"
test -s "$D/Probe.dll"
test -s "$D/operation-and-sources-before.txt"
test -s "$D/preferences-before.txt"
tar -tzf "$D/AICompanionUI-original.tar.gz" | grep -qx 'com.samsung.tv.AICompanionUI/bin/AICompanionUI.dll'
app_launcher -u -k com.samsung.tv.AICompanionUI || true
rm -rf "$A"
tar -xzf "$D/AICompanionUI-original.tar.gz" -C /opt/usr/apps
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = fe1cb14b2a0d5994662c6856cee7c4ebe87e6d2b276ada0e080f5160f15b4b5c
original_operation=$(sed -n 's/^home_result=[^ ]* home=//p' "$D/operation-and-sources-before.txt")
test -n "$original_operation" && test "$original_operation" != null
original_home=$(awk '$0=="KEY=db/appfw/home_appid" {getline; sub(/^.*value = /, ""); sub(/ \([^)]*\)$/, ""); print; exit}' "$D/preferences-before.txt")
original_startup=$(awk '$0=="KEY=db/appfw/startup_appid" {getline; sub(/^.*value = /, ""); sub(/ \([^)]*\)$/, ""); print; exit}' "$D/preferences-before.txt")
test -n "$original_home" && test -n "$original_startup"
/usr/bin/dotnet "$D/Probe.dll" set-home "$original_operation"
vconftool set -f -t string db/appfw/home_appid "$original_home"
vconftool set -f -t string db/appfw/startup_appid "$original_startup"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$original_home"
test "$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$original_startup"
test "$(/usr/bin/dotnet "$D/Probe.dll" | sed -n 's/^home_result=[^ ]* home=//p')" = "$original_operation"
app_launcher -u -s com.samsung.tv.AICompanionUI
echo "Original AI Companion UI and Home/startup selectors restored from $D."
