#!/bin/sh
# Assign Home/startup only after the installed preview has been visibly tested.
# Input: the unique backup phase name used for preview installation.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
S=/home/owner/share/tmp/sdk_tools/quiet-tizen
S=${2:-$S}
case "$S" in /home/owner/share/tmp/sdk_tools/quiet-tizen|/home/owner/share/tmp/sdk_tools/archive-root-*) ;; *) echo 'Invalid staging path' >&2; exit 1;; esac
P=com.samsung.tv.bixby-promotion
test -s "$D/Probe.dll"
test -s "$D/operation-and-sources-before.txt"
test -s "$D/preferences-before.txt"
test -s "$D/installed-home.sha256"
test -s "$S/restore-home-route.sh"
sha256sum -c "$D/installed-home.sha256"
original=$(sed -n 's/^home_result=0 home=//p' "$D/operation-and-sources-before.txt")
test "$original" = com.samsung.tv.csfs
current=$(/usr/bin/dotnet "$D/Probe.dll" | sed -n 's/^home_result=0 home=//p')
test "$current" = "$original"
test "$(vconftool get db/appfw/home_appid)" = "$(sed -n '2p' "$D/preferences-before.txt")"
test "$(vconftool get db/appfw/startup_appid)" = "$(sed -n '4p' "$D/preferences-before.txt")"
test ! -e "$D/restore-home-route.sh"
cp "$S/restore-home-route.sh" "$D/restore-home-route.sh"
chmod 700 "$D/restore-home-route.sh"
trap '/bin/cat "$D/restore-home-route.sh" | /bin/sh -s -- "$name"' EXIT
/usr/bin/dotnet "$D/Probe.dll" set-home "$P"
vconftool set -f -t string db/appfw/home_appid "$P"
vconftool set -f -t string db/appfw/startup_appid "$P"
test "$(/usr/bin/dotnet "$D/Probe.dll" | sed -n 's/^home_result=0 home=//p')" = "$P"
test "$(vconftool get db/appfw/home_appid)" = "db/appfw/home_appid, value = $P (String)"
test "$(vconftool get db/appfw/startup_appid)" = "db/appfw/startup_appid, value = $P (String)"
trap - EXIT
echo 'Home and startup now target Quiet Home. Restart only after this session has cleaned up.'
