#!/bin/sh
# Restore the catalog snapshot and remove only the three installed artwork files.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.bixby-promotion
R=$A/res/quiet-home
test -s "$D/apps-before.json"
test -s "$D/apps-before.sha256"
test -s "$D/launcher-assembly.sha256"
test -s "$D/installed-artwork.sha256"
sha256sum -c "$D/apps-before.sha256"
sha256sum -c "$D/launcher-assembly.sha256"
sha256sum -c "$D/installed-artwork.sha256"
test "$(find "$R/app-icons" -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 3
test "$(find "$R/app-icons" -mindepth 1 -maxdepth 1 | wc -l)" -eq 3
app_launcher -u 5001 -k com.samsung.tv.bixby-promotion || true
cp "$D/apps-before.json" "$R/apps.json.new"
chown 201:0 "$R/apps.json.new"
chmod 644 "$R/apps.json.new"
chsmack -a User::Pkg::com.samsung.tv.bixby-promotion::RO "$R/apps.json.new"
mv "$R/apps.json.new" "$R/apps.json"
rm "$R/app-icons/netflix.svg" "$R/app-icons/youtube.jpg" "$R/app-icons/prime-video.svg"
rmdir "$R/app-icons"
test "$(sha256sum "$R/apps.json" | cut -d ' ' -f 1)" = "$(sha256sum "$D/apps-before.json" | cut -d ' ' -f 1)"
app_launcher -u 5001 -s com.samsung.tv.bixby-promotion
echo 'Original placeholder catalog restored.'
