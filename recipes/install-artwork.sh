#!/bin/sh
# Replace only Quiet Home's app catalog and add three locally fetched logos.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.bixby-promotion
R=$A/res/quiet-home
S=${2:-/home/owner/share/tmp/sdk_tools/quiet-tizen}
case "$S" in /home/owner/share/tmp/sdk_tools/quiet-tizen|/home/owner/share/tmp/sdk_tools/archive-root-*) ;; *) exit 1;; esac
test -s "$D/apps-before.json"
test -s "$D/apps-before.sha256"
test -s "$D/launcher-assembly.sha256"
test -s "$S/artwork-apps.json"
test -s "$S/artwork-netflix.svg"
test -s "$S/artwork-youtube.jpg"
test -s "$S/artwork-prime-video.svg"
test -s "$S/restore-artwork.sh"
test ! -e "$D/installed-artwork.sha256"
test ! -e "$D/restore-artwork.sh"
test ! -e "$R/app-icons"
sha256sum -c "$D/apps-before.sha256"
sha256sum -c "$D/launcher-assembly.sha256"
test "$(sha256sum "$R/apps.json" | cut -d ' ' -f 1)" = "$(sha256sum "$D/apps-before.json" | cut -d ' ' -f 1)"
umask 077
cp "$S/restore-artwork.sh" "$D/restore-artwork.sh"
chmod 700 "$D/restore-artwork.sh"
{
  printf '%s  %s\n' "$(sha256sum "$S/artwork-apps.json" | cut -d ' ' -f 1)" "$R/apps.json"
  printf '%s  %s\n' "$(sha256sum "$S/artwork-netflix.svg" | cut -d ' ' -f 1)" "$R/app-icons/netflix.svg"
  printf '%s  %s\n' "$(sha256sum "$S/artwork-youtube.jpg" | cut -d ' ' -f 1)" "$R/app-icons/youtube.jpg"
  printf '%s  %s\n' "$(sha256sum "$S/artwork-prime-video.svg" | cut -d ' ' -f 1)" "$R/app-icons/prime-video.svg"
} > "$D/installed-artwork.sha256"
app_launcher -u 5001 -k com.samsung.tv.bixby-promotion || true
mkdir "$R/app-icons"
cp "$S/artwork-netflix.svg" "$R/app-icons/netflix.svg"
cp "$S/artwork-youtube.jpg" "$R/app-icons/youtube.jpg"
cp "$S/artwork-prime-video.svg" "$R/app-icons/prime-video.svg"
cp "$S/artwork-apps.json" "$R/apps.json.new"
chown 201:0 "$R/app-icons" "$R/app-icons/"* "$R/apps.json.new"
chmod 755 "$R/app-icons"
chmod 644 "$R/app-icons/"* "$R/apps.json.new"
for p in "$R/app-icons" "$R/app-icons/"* "$R/apps.json.new"; do
  chsmack -a User::Pkg::com.samsung.tv.bixby-promotion::RO "$p"
done
mv "$R/apps.json.new" "$R/apps.json"
sha256sum -c "$D/installed-artwork.sha256"
app_launcher -u 5001 -s com.samsung.tv.bixby-promotion
echo 'Local Netflix, YouTube, and Prime Video artwork installed.'
