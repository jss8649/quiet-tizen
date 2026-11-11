#!/bin/sh
# Sync rebuilt quiet-home resources (catalog + artwork). Replaces only our subtree.
set -eu
test "$(id -u)" = 0
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
S=/home/owner/share/tmp/sdk_tools/quiet-tizen
test -s "$S/package.tar.gz"
test -s "$A/bin/AICompanionUI.dll" # launcher already installed
rm -rf "$S/unpacked"
mkdir "$S/unpacked"
tar -xzf "$S/package.tar.gz" -C "$S/unpacked"
test -s "$S/unpacked/quiet-home/apps.json"
app_launcher -u 5001 -k com.samsung.tv.AICompanionUI || true
rm -rf "$A/res/quiet-home"
cp -R "$S/unpacked/quiet-home" "$A/res/"
find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
find "$A/res/quiet-home" -exec chown 201:0 {} \;
find "$A/res/quiet-home" -exec chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO {} \;
app_launcher -u 5001 -s com.samsung.tv.AICompanionUI
echo 'Resources synced and launcher restarted.'
