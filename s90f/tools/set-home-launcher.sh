#!/bin/sh
set -eu

name=${1:?Backup name required}
case "$name" in quiet-home-s90f-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
APP=com.samsung.tv.AICompanionUI
PROBE=/usr/bin/dotnet
changed=0

test -s "$D/AICompanionUI-original.tar.gz"
test -s "$D/Probe.dll"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = 5577b460d00f5ec4a0d450bd2e57a494453e7b1ae834bddef3b7a88e19bb5609
test -s "$A/res/quiet-home/apps.json"
test -s "$D/install-phase.txt"

old_operation=$($PROBE "$D/Probe.dll" | sed -n 's/^home_result=[^ ]* home=//p')
old_home=$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')
old_startup=$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')
test "$old_operation" = com.samsung.tv.csfs
test "$old_home" = com.samsung.tv.csfs
test "$old_startup" = org.tizen.tv-viewer
test ! -e "$D/routing-before-home.txt"
{
    echo "operation=$old_operation"
    echo "home_appid=$old_home"
    echo "startup_appid=$old_startup"
} > "$D/routing-before-home.txt"
chmod 600 "$D/routing-before-home.txt"

rollback() {
    status=$?
    if [ "$changed" = 1 ]; then
        "$PROBE" "$D/Probe.dll" set-home "$old_operation" || true
        vconftool set -f -t string db/appfw/home_appid "$old_home" || true
    fi
    exit "$status"
}
trap rollback EXIT HUP INT TERM

changed=1
"$PROBE" "$D/Probe.dll" set-home "$APP"
vconftool set -f -t string db/appfw/home_appid "$APP"
new_operation=$($PROBE "$D/Probe.dll" | sed -n 's/^home_result=[^ ]* home=//p')
new_home=$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')
new_startup=$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')
test "$new_operation" = "$APP"
test "$new_home" = "$APP"
test "$new_startup" = "$old_startup"
changed=0
trap - EXIT HUP INT TERM
echo "Home operation and Home app preference now target $APP."
echo "Startup preference remains $new_startup."
echo "Prior route values saved at $D/routing-before-home.txt."
