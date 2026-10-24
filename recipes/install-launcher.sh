#!/bin/sh
# Install only. Home/startup routing is changed AFTER manual launch is verified.
# Input: snapshot name. Stage .local/package.tar.gz as quiet-tizen/package.tar.gz first.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.bixby-promotion
S=/home/owner/share/tmp/sdk_tools/quiet-tizen
S=${2:-$S}
case "$S" in /home/owner/share/tmp/sdk_tools/quiet-tizen|/home/owner/share/tmp/sdk_tools/archive-root-*) ;; *) echo 'Invalid staging path' >&2; exit 1;; esac
test -s "$D/.pkgmgr_parser.db"
test -s "$S/package.tar.gz"
test -s "$A/bin/BixbyPromotion.dll"
test "$(stat -c %u:%g "$A/bin/BixbyPromotion.dll")" = 201:0
test -s "$D/bixby-promotion-original/bin/BixbyPromotion.dll"
test -s "$D/original-assembly.sha256"
sha256sum -c "$D/original-assembly.sha256"
before=$(sqlite3 -readonly -separator '|' "$D/.pkgmgr_parser.db" "SELECT app_disable,app_onboot,app_autorestart FROM package_app_info WHERE app_id='com.samsung.tv.bixby-promotion';")
current=$(sqlite3 -readonly -separator '|' /opt/dbspace/.pkgmgr_parser.db "SELECT app_disable,app_onboot,app_autorestart FROM package_app_info WHERE app_id='com.samsung.tv.bixby-promotion';")
test -n "$before"
test "$before" = "$current" || { echo 'Launcher registry flags changed since snapshot' >&2; exit 1; }
test ! -e "$A/res/quiet-home" # First install only; do not silently overwrite an existing custom launcher.
test ! -e "$S/unpacked"
# The archive is generated from our local build, not downloaded from an unknown party.
mkdir "$S/unpacked"
tar -xzf "$S/package.tar.gz" -C "$S/unpacked"
test -s "$S/unpacked/BixbyPromotion.dll"
test -s "$S/unpacked/Probe.dll"
test -s "$S/unpacked/quiet-home/apps.json"
test -s "$S/unpacked/quiet-home/home-layout.json"
test -s "$S/restore-preview.sh"
cp "$S/unpacked/Probe.dll" "$D/Probe.dll"
cp "$S/restore-preview.sh" "$D/restore-preview.sh"
chmod 700 "$D/restore-preview.sh"
/usr/bin/dotnet "$D/Probe.dll" > "$D/operation-and-sources-before.txt"
digest=$(sha256sum "$S/unpacked/BixbyPromotion.dll" | cut -d ' ' -f 1)
printf '%s  %s\n' "$digest" "$A/bin/BixbyPromotion.dll" > "$D/installed-home.sha256"
app_launcher -u 5001 -k com.samsung.tv.bixby-promotion || true
if [ -d "$A/bin/.native_image" ]; then mv "$A/bin/.native_image" "$D/home-native-image"; fi
cp "$S/unpacked/BixbyPromotion.dll" "$A/bin/BixbyPromotion.dll"
cp -R "$S/unpacked/quiet-home" "$A/res/"
chown 201:0 "$A/bin/BixbyPromotion.dll"
chmod 755 "$A/bin/BixbyPromotion.dll"
chsmack -a User::Pkg::com.samsung.tv.bixby-promotion::RO "$A/bin/BixbyPromotion.dll"
sha256sum -c "$D/installed-home.sha256"
find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
find "$A/res/quiet-home" -exec chown 201:0 {} \;
find "$A/res/quiet-home" -exec chsmack -a User::Pkg::com.samsung.tv.bixby-promotion::RO {} \;
if [ "$current" != 'false|false|false' ]; then
sqlite3 -bail /opt/dbspace/.pkgmgr_parser.db <<'SQL'
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM package_app_info WHERE app_id='com.samsung.tv.bixby-promotion';
UPDATE package_app_info SET app_disable='false',app_onboot='false',app_autorestart='false' WHERE app_id='com.samsung.tv.bixby-promotion';
DROP TABLE guard;
COMMIT;
SQL
fi
app_launcher -u 5001 -s com.samsung.tv.bixby-promotion
echo 'Installed and launch requested. Verify the visible UI, remote, sound, apps and HDMI before changing Home routing.'
echo "Original package and operation/source record: $D"
