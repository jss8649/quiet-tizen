#!/bin/sh
# SNAPSHOT_NAME ORIGINAL_MAIN_OPERATION_APP ORIGINAL_HOME_APP ORIGINAL_STARTUP_APP
#   [CONTAINER_APP_ID ENTRY_DLL]: the same container and DLL that install-launcher.sh received.
# Read all three original IDs from that TV's saved records; do not guess them.
set -eu
test "$(id -u)" = 0
name=${1:?}; operation=${2:?}; home=${3:?}; startup=${4:?}
container=${5:-com.samsung.tv.bixby-promotion}
dll=${6:-BixbyPromotion.dll}
case "$name" in ''|*[!A-Za-z0-9_-]*) exit 1;; esac
for value in "$operation" "$home" "$startup" "$container" "$dll"; do
    case "$value" in ''|*[!A-Za-z0-9_.-]*) exit 1;; esac
done
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/$container
original=$D/${container##*.}-original
label=User::Pkg::$container::RO
test -s "$D/Probe.dll"
test -s "$original/bin/$dll"
test -s "$D/.pkgmgr_parser.db"
sha256sum -c "$D/installed-home.sha256"
# One registry row for the container, live and in the snapshot, before changing anything.
for db in /opt/dbspace/.pkgmgr_parser.db "$D/.pkgmgr_parser.db"; do
    test "$(sqlite3 -readonly "$db" "SELECT count(*) FROM package_app_info WHERE app_id='$container';")" = 1
done
/usr/bin/dotnet "$D/Probe.dll" set-home "$operation"
vconftool set -f -t string db/appfw/home_appid "$home"
vconftool set -f -t string db/appfw/startup_appid "$startup"
app_launcher -u 5001 -k "$container" || true
cp -a "$original/bin/$dll" "$A/bin/$dll"
chsmack -a "$label" "$A/bin/$dll"
if [ -d "$D/home-native-image" ]; then
    test ! -e "$A/bin/.native_image"
    cp -a "$D/home-native-image" "$A/bin/.native_image"
fi
sqlite3 -bail /opt/dbspace/.pkgmgr_parser.db <<SQL
ATTACH '$D/.pkgmgr_parser.db' AS before;
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM before.package_app_info WHERE app_id='$container';
INSERT INTO guard SELECT count(*)=1 FROM package_app_info WHERE app_id='$container';
UPDATE package_app_info SET
app_disable=(SELECT app_disable FROM before.package_app_info WHERE app_id='$container'),
app_onboot=(SELECT app_onboot FROM before.package_app_info WHERE app_id='$container'),
app_autorestart=(SELECT app_autorestart FROM before.package_app_info WHERE app_id='$container')
WHERE app_id='$container';
DROP TABLE guard;
COMMIT;
SQL
app_launcher -u 5001 -s "$home"
echo 'Original launcher routing and assembly restored. Extra Quiet Home resources remain inert for recovery.'
