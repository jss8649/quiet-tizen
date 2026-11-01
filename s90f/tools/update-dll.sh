#!/bin/sh
set -eu

name=${1:?Unique backup name required}
stage=${2:?Unique staging directory required}
package_hash=${3:?Expected package hash required}
current_hash=${4:?Expected installed launcher hash required}
new_hash=${5:?Expected new launcher hash required}
case "$name" in quiet-home-s90f-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/quiet-tizen-icons-*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
APP=com.samsung.tv.AICompanionUI
R=$A/res/quiet-home
P="$stage/unpacked"
S=/opt/usr/share/quiet-tizen-state
mutating=0

fix() {
    chown 201:0 "$1"
    chmod "$2" "$1"
    chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$1"
}

rollback() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$mutating" -eq 1 ]; then
        cp "$D/AICompanionUI.dll.before" "$A/bin/AICompanionUI.dll"
        fix "$A/bin/AICompanionUI.dll" 755
        while read -r f; do
            if [ -f "$D/orig/$f" ]; then cp "$D/orig/$f" "$R/$f"; fix "$R/$f" 644; else rm -f "$R/$f"; fi
        done < "$D/files.txt"
        app_launcher -u 5001 -s "$APP" || true
    fi
    rm -rf "$stage"
    exit "$status"
}
trap rollback EXIT HUP INT TERM

test ! -e "$D"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$current_hash"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test -s "$stage/package-dll.tar.gz"
test "$(sha256sum "$stage/package-dll.tar.gz" | cut -d ' ' -f 1)" = "$package_hash"
mkdir "$stage/unpacked"
tar -xzf "$stage/package-dll.tar.gz" -C "$P"
test "$(sha256sum "$P/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
test -s "$R/fireplace.mp4"
mkdir -m 700 "$D" "$D/orig"
cp "$A/bin/AICompanionUI.dll" "$D/AICompanionUI.dll.before"
chmod 600 "$D/AICompanionUI.dll.before"
ls "$P/quiet-home" > "$D/files.txt"
while read -r f; do
    case "$f" in */*|"") exit 2;; esac
    if [ -f "$R/$f" ]; then cp "$R/$f" "$D/orig/$f"; fi
done < "$D/files.txt"

mutating=1
app_launcher -u 5001 -k "$APP" || true
rm -f /tmp/quiet-home-video.txt /tmp/quiet-home-weather.txt
while read -r f; do
    cp "$P/quiet-home/$f" "$R/$f.new"
    fix "$R/$f.new" 644
    mv "$R/$f.new" "$R/$f"
done < "$D/files.txt"
cp "$P/AICompanionUI.dll" "$A/bin/AICompanionUI.dll.new"
fix "$A/bin/AICompanionUI.dll.new" 755
mv "$A/bin/AICompanionUI.dll.new" "$A/bin/AICompanionUI.dll"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
app_launcher -u 5001 -k "$APP" || true
sleep 1
mkdir -p "$S"
chown 5001:100 "$S"; chmod 755 "$S"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI "$S"
touch "$S/last-app.txt"
chown 5001:100 "$S/last-app.txt"; chmod 644 "$S/last-app.txt"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI "$S/last-app.txt"
app_launcher -u 5001 -s "$APP"
mutating=0
echo "Launcher updated; files: $(tr '\n' ' ' < "$D/files.txt")"
