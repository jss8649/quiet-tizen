#!/bin/sh
set -eu

name=${1:?Unique backup name required}
stage=${2:?Unique staging directory required}
package_hash=${3:?Expected package hash required}
current_hash=${4:?Expected installed launcher hash required}
new_hash=${5:?Expected new launcher hash required}
case "$name" in quiet-home-s90f-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/quiet-tizen-icons-*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
APP=com.samsung.tv.AICompanionUI
R=$A/res/quiet-home
P="$stage/unpacked"
mutating=0

fix() {
    chown 201:0 "$1"
    chmod "$2" "$1"
    chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$1"
}

rollback() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$mutating" -eq 1 ]; then
        cp "$D/AICompanionUI.dll.before" "$A/bin/AICompanionUI.dll"
        fix "$A/bin/AICompanionUI.dll" 755
        cp "$D/apps.json.before" "$R/apps.json"
        fix "$R/apps.json" 644
        rm -f "$R/fireplace.mp4" "$R/fireplace.mp4.new"
        app_launcher -u 5001 -s "$APP" || true
    fi
    rm -rf "$stage"
    exit "$status"
}
trap rollback EXIT HUP INT TERM

test ! -e "$D"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$current_hash"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test -s "$stage/package-backdrop.tar.gz"
test "$(sha256sum "$stage/package-backdrop.tar.gz" | cut -d ' ' -f 1)" = "$package_hash"
avail=$(df -k /opt/usr | awk 'NR==2{print $4}')
test "$avail" -gt 200000
mkdir -m 700 "$D"
tar -czf "$D/AICompanionUI-before-backdrop.tar.gz" -C /opt/usr/apps com.samsung.tv.AICompanionUI
cp "$A/bin/AICompanionUI.dll" "$D/AICompanionUI.dll.before"
cp "$R/apps.json" "$D/apps.json.before"
chmod 600 "$D/AICompanionUI.dll.before" "$D/apps.json.before"
{ vconftool get db/appfw/home_appid; vconftool get db/appfw/startup_appid; } > "$D/routing-before.txt"

mkdir "$P"
tar -xzf "$stage/package-backdrop.tar.gz" -C "$P"
test "$(sha256sum "$P/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
test -s "$P/quiet-home/apps.json"
test -s "$P/quiet-home/fireplace.mp4"
for app in org.tizen.netflix-app 9Ur5IzDKqV.TizenYouTube rTn6ClEurC.Jellyfin RtArchTzn0.RetroArch rJeHak5zRg.Spotify; do
    grep -q "\"Id\": \"$app\"" "$P/quiet-home/apps.json"
done
test -s "$R/home-background.jpg"
test -s "$R/app-icons/live-tv.svg"

echo "Backed up to $D"
mutating=1
app_launcher -u 5001 -k "$APP" || true
cp "$P/quiet-home/fireplace.mp4" "$R/fireplace.mp4.new"
fix "$R/fireplace.mp4.new" 644
mv "$R/fireplace.mp4.new" "$R/fireplace.mp4"
cp "$P/quiet-home/apps.json" "$R/apps.json.new"
fix "$R/apps.json.new" 644
mv "$R/apps.json.new" "$R/apps.json"
cp "$P/AICompanionUI.dll" "$A/bin/AICompanionUI.dll.new"
fix "$A/bin/AICompanionUI.dll.new" 755
mv "$A/bin/AICompanionUI.dll.new" "$A/bin/AICompanionUI.dll"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
app_launcher -u 5001 -s "$APP"
mutating=0
echo "Backdrop installed. Routing:"
vconftool get db/appfw/home_appid
vconftool get db/appfw/startup_appid
