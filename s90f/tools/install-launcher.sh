#!/bin/sh
set -eu

name=${1:?Backup phase name required}
stage=${2:?Temporary staging directory required}
expected_package_hash=${3:?Expected package hash required}
expected_original_hash=${4:?Expected original app hash required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 2;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/quiet-tizen-install-*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
P="$stage/unpacked"

test -s "$D/AICompanionUI-original.tar.gz"
test -s "$stage/package-s90f.tar.gz"
test "$(sha256sum "$stage/package-s90f.tar.gz" | cut -d ' ' -f 1)" = "$expected_package_hash"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$expected_original_hash"
test ! -d "$A/res/quiet-home"
mkdir "$P"
tar -xzf "$stage/package-s90f.tar.gz" -C "$P"
test -s "$P/AICompanionUI.dll"
test -s "$P/quiet-home/apps.json"
test -s "$P/quiet-home/free-background.svg"
test -s "$D/.pkgmgr_parser.db"
test -s "$D/.app-context.db"
test -s "$D/.webappservice.db"

app_launcher -u 5001 -k com.samsung.tv.AICompanionUI || true
if [ -d "$A/bin/.native_image" ]; then
    mv "$A/bin/.native_image" "$D/AICompanionUI-native-image"
fi
cp "$P/AICompanionUI.dll" "$A/bin/AICompanionUI.dll"
chown 201:0 "$A/bin/AICompanionUI.dll"
chmod 755 "$A/bin/AICompanionUI.dll"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$A/bin/AICompanionUI.dll"
cp -R "$P/quiet-home" "$A/res/quiet-home"
find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
find "$A/res/quiet-home" -exec chown 201:0 {} \;
find "$A/res/quiet-home" -exec chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO {} \;
sha256sum "$A/bin/AICompanionUI.dll" > "$D/installed-home.sha256"
echo "$(date -u +%FT%TZ) Quiet Home installed as the AI Companion UI; Home routing unchanged." > "$D/install-phase.txt"
app_launcher -u 5001 -s com.samsung.tv.AICompanionUI
echo "Quiet Home installed and launch requested: $A"
echo "Backup: $D; Home/startup selectors remain unchanged."
