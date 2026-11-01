#!/bin/sh
set -eu

name=${1:?Backup name required}
stage=${2:?Unique staging directory required}
package_hash=${3:?Expected package hash required}
current_hash=${4:?Current launcher hash required}
new_hash=${5:?New launcher hash required}
case "$name" in quiet-home-s90f-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/quiet-tizen-update-*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
APP=com.samsung.tv.AICompanionUI
P="$stage/unpacked"
trap 'rm -rf "$stage"' EXIT HUP INT TERM

test -s "$D/AICompanionUI-original.tar.gz"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$current_hash"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test "$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = org.tizen.tv-viewer
test -s "$stage/package-s90f.tar.gz"
test "$(sha256sum "$stage/package-s90f.tar.gz" | cut -d ' ' -f 1)" = "$package_hash"
test ! -e "$D/quiet-home-before-startup.tar.gz"
test ! -e "$D/routing-before-startup.txt"

tar -czf "$D/quiet-home-before-startup.tar.gz" -C /opt/usr/apps com.samsung.tv.AICompanionUI
test -s "$D/quiet-home-before-startup.tar.gz"
{
    vconftool get db/appfw/home_appid
    vconftool get db/appfw/startup_appid
} > "$D/routing-before-startup.txt"
chmod 600 "$D/routing-before-startup.txt"

mkdir "$P"
tar -xzf "$stage/package-s90f.tar.gz" -C "$P"
test -s "$P/AICompanionUI.dll"
test -s "$P/quiet-home/apps.json"
grep -q '"Name": "Live TV"' "$P/quiet-home/apps.json"
grep -q '"Id": "org.tizen.tv-viewer"' "$P/quiet-home/apps.json"
test "$(sha256sum "$P/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
test "$(sha256sum "$P/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$current_hash"

app_launcher -u 5001 -k "$APP" || true
cp "$P/AICompanionUI.dll" "$A/bin/AICompanionUI.dll.new"
chown 201:0 "$A/bin/AICompanionUI.dll.new"
chmod 755 "$A/bin/AICompanionUI.dll.new"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$A/bin/AICompanionUI.dll.new"
mv "$A/bin/AICompanionUI.dll.new" "$A/bin/AICompanionUI.dll"
mv "$A/res/quiet-home" "$D/quiet-home-before-startup-assets"
cp -R "$P/quiet-home" "$A/res/quiet-home"
find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
find "$A/res/quiet-home" -exec chown 201:0 {} \;
find "$A/res/quiet-home" -exec chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO {} \;
sha256sum "$A/bin/AICompanionUI.dll" > "$D/installed-home.sha256"

app_launcher -u 5001 -s "$APP"
vconftool set -f -t string db/appfw/startup_appid "$APP"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test "$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
echo "Updated Quiet Home with a Live TV shortcut and verified the package."
echo "Home and startup now target $APP. Previous launcher snapshot: $D/quiet-home-before-startup.tar.gz"
echo "Original Samsung app and baseline registry backup remain at $D."
