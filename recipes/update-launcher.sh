#!/bin/sh
# Hot-swap the launcher dll only (iteration workflow after install-launcher.sh).
# Container layout is already in place; this refreshes the binary and relaunches.
set -eu
test "$(id -u)" = 0
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
S=/home/owner/share/tmp/sdk_tools/quiet-tizen
D=/opt/usr/share/quiet-tizen-backups/home-01
test -s "$S/AICompanionUI.dll"
test -s "$A/res/quiet-home/apps.json" # proves install-launcher.sh ran first
app_launcher -u 5001 -k com.samsung.tv.AICompanionUI || true
cp "$S/AICompanionUI.dll" "$A/bin/AICompanionUI.dll"
chown 201:0 "$A/bin/AICompanionUI.dll"
chmod 644 "$A/bin/AICompanionUI.dll"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$A/bin/AICompanionUI.dll"
sha256sum "$A/bin/AICompanionUI.dll" > "$D/installed-home.sha256"
app_launcher -u 5001 -s com.samsung.tv.AICompanionUI
echo 'Launcher dll swapped and relaunched.'
