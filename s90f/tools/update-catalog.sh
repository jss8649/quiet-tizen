#!/bin/sh
set -eu

name=${1:?Unique backup name required}
stage=${2:?Unique staging directory required}
package_hash=${3:?Expected package hash required}
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
    chmod 644 "$1"
    chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$1"
}

rollback() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$mutating" -eq 1 ]; then
        cp "$D/apps.json.before" "$R/apps.json"
        fix "$R/apps.json"
        app_launcher -u 5001 -s "$APP" || true
    fi
    rm -rf "$stage"
    exit "$status"
}
trap rollback EXIT HUP INT TERM

test ! -e "$D"
test -s "$stage/package-s90f.tar.gz"
test "$(sha256sum "$stage/package-s90f.tar.gz" | cut -d ' ' -f 1)" = "$package_hash"
mkdir -m 700 "$D"
tar -czf "$D/AICompanionUI-before-catalog-update.tar.gz" -C /opt/usr/apps com.samsung.tv.AICompanionUI
cp "$R/apps.json" "$D/apps.json.before"
chmod 600 "$D/apps.json.before"
echo "startup before: $(vconftool get db/appfw/startup_appid)" > "$D/routing-before.txt"
vconftool get db/appfw/home_appid >> "$D/routing-before.txt"

mkdir "$P"
tar -xzf "$stage/package-s90f.tar.gz" -C "$P"
test -s "$P/quiet-home/apps.json"
for app in org.tizen.netflix-app 9Ur5IzDKqV.TizenYouTube rTn6ClEurC.Jellyfin RtArchTzn0.RetroArch rJeHak5zRg.Spotify; do
    grep -q "\"Id\": \"$app\"" "$P/quiet-home/apps.json"
done

mutating=1
cp "$P/quiet-home/apps.json" "$R/apps.json.new"
fix "$R/apps.json.new"
mv "$R/apps.json.new" "$R/apps.json"
grep -q 9Ur5IzDKqV.TizenYouTube "$R/apps.json"
app_launcher -u 5001 -k "$APP" || true
app_launcher -u 5001 -s "$APP"
mutating=0
echo "Catalog updated. DLL and routing untouched."
vconftool get db/appfw/home_appid
vconftool get db/appfw/startup_appid
echo "Rollback: $D"
