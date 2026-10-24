#!/bin/sh
# Save the current Quiet Home catalog before adding local publisher artwork.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.bixby-promotion
R=$A/res/quiet-home
umask 077
test ! -e "$D"
test -s "$A/bin/BixbyPromotion.dll"
test -s "$R/apps.json"
test ! -e "$R/app-icons"
mkdir "$D"
cp "$R/apps.json" "$D/apps-before.json"
sha256sum "$D/apps-before.json" > "$D/apps-before.sha256"
sha256sum "$A/bin/BixbyPromotion.dll" > "$D/launcher-assembly.sha256"
stat -c '%u:%g|%a' "$R/apps.json" > "$D/catalog-metadata-before.txt"
sha256sum -c "$D/apps-before.sha256"
echo 'Artwork catalog snapshot saved; no launcher files changed.'
