#!/bin/sh
# Restore only the three Home/startup selectors, preserving the installed preview.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
P=com.samsung.tv.bixby-promotion
test -s "$D/Probe.dll"
test -s "$D/operation-and-sources-before.txt"
test -s "$D/preferences-before.txt"
original=$(sed -n 's/^home_result=0 home=//p' "$D/operation-and-sources-before.txt")
test "$original" = com.samsung.tv.csfs
saved_home=$(sed -n '2p' "$D/preferences-before.txt")
saved_startup=$(sed -n '4p' "$D/preferences-before.txt")
test "$saved_home" = 'db/appfw/home_appid, value = com.samsung.tv.csfs (String)'
test "$saved_startup" = 'db/appfw/startup_appid, value = com.samsung.tv.csfs (String)'
current=$(/usr/bin/dotnet "$D/Probe.dll" | sed -n 's/^home_result=0 home=//p')
case "$current" in com.samsung.tv.csfs|com.samsung.tv.bixby-promotion) ;; *) echo 'Home operation drifted' >&2; exit 1;; esac
home=$(vconftool get db/appfw/home_appid)
startup=$(vconftool get db/appfw/startup_appid)
case "$home" in "$saved_home"|"db/appfw/home_appid, value = $P (String)") ;; *) echo 'Home preference drifted' >&2; exit 1;; esac
case "$startup" in "$saved_startup"|"db/appfw/startup_appid, value = $P (String)") ;; *) echo 'Startup preference drifted' >&2; exit 1;; esac
if [ "$current" = "$P" ]; then /usr/bin/dotnet "$D/Probe.dll" set-home "$original"; fi
if [ "$home" != "$saved_home" ]; then vconftool set -f -t string db/appfw/home_appid "$original"; fi
if [ "$startup" != "$saved_startup" ]; then vconftool set -f -t string db/appfw/startup_appid "$original"; fi
test "$(/usr/bin/dotnet "$D/Probe.dll" | sed -n 's/^home_result=0 home=//p')" = "$original"
test "$(vconftool get db/appfw/home_appid)" = "$saved_home"
test "$(vconftool get db/appfw/startup_appid)" = "$saved_startup"
echo 'Original Home/startup selectors restored; Quiet Home preview remains installed.'
