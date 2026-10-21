#!/bin/sh
# Install only. Home/startup routing is changed AFTER manual launch is verified.
# SNAPSHOT_NAME [CONTAINER_APP_ID ENTRY_DLL]: both from the profile's "launcher" block;
# the defaults are the U8000F's. Stage .local/package.tar.gz as quiet-tizen/package.tar.gz first.
set -eu
test "$(id -u)" = 0
name=${1:?Snapshot name required}
container=${2:-com.samsung.tv.bixby-promotion}
dll=${3:-BixbyPromotion.dll}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
for value in "$container" "$dll"; do
    case "$value" in ''|*[!A-Za-z0-9_.-]*) exit 1;; esac
done
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/$container
original=$D/${container##*.}-original
label=User::Pkg::$container::RO
S=/home/owner/share/tmp/sdk_tools/quiet-tizen
test -s "$D/.pkgmgr_parser.db"
test -s "$S/package.tar.gz"
test -s "$A/bin/$dll"
test "$(stat -c %u:%g "$A/bin/$dll")" = 201:0
test ! -e "$original"
test ! -e "$A/res/quiet-home" # First install only; do not silently overwrite an existing custom launcher.
test ! -e "$S/unpacked"
# One registry row for the container, live and in the snapshot, before touching the package.
for db in /opt/dbspace/.pkgmgr_parser.db "$D/.pkgmgr_parser.db"; do
    test "$(sqlite3 -readonly "$db" "SELECT count(*) FROM package_app_info WHERE app_id='$container';")" = 1
done
# The archive is generated from our local build, not downloaded from an unknown party.
mkdir "$S/unpacked"
tar -xzf "$S/package.tar.gz" -C "$S/unpacked"
test -s "$S/unpacked/$dll"
test -s "$S/unpacked/Probe.dll"
test -s "$S/unpacked/quiet-home/apps.json"
cp -a "$A" "$original"
cp "$S/unpacked/Probe.dll" "$D/Probe.dll"
/usr/bin/dotnet "$D/Probe.dll" > "$D/operation-and-sources-before.txt"
app_launcher -u 5001 -k "$container" || true
if [ -d "$A/bin/.native_image" ]; then mv "$A/bin/.native_image" "$D/home-native-image"; fi
cp "$S/unpacked/$dll" "$A/bin/$dll"
cp -R "$S/unpacked/quiet-home" "$A/res/"
chown 201:0 "$A/bin/$dll"
chmod 644 "$A/bin/$dll"
chsmack -a "$label" "$A/bin/$dll"
sha256sum "$A/bin/$dll" > "$D/installed-home.sha256"
find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
find "$A/res/quiet-home" -exec chown 201:0 {} \;
find "$A/res/quiet-home" -exec chsmack -a "$label" {} \;
sqlite3 -bail /opt/dbspace/.pkgmgr_parser.db <<SQL
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM package_app_info WHERE app_id='$container';
UPDATE package_app_info SET app_disable='false',app_onboot='false',app_autorestart='false' WHERE app_id='$container';
DROP TABLE guard;
COMMIT;
SQL
app_launcher -u 5001 -s "$container"
echo 'Installed and launch requested. Verify the visible UI, remote, sound, apps and HDMI before changing Home routing.'
echo "Original package and operation/source record: $D"
