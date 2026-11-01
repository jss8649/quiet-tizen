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
P="$stage/unpacked"
mutating=0

rollback() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$mutating" -eq 1 ]; then
        if [ -s "$D/AICompanionUI.dll-before-update" ]; then
            cp "$D/AICompanionUI.dll-before-update" "$A/bin/AICompanionUI.dll"
            chown 201:0 "$A/bin/AICompanionUI.dll"
            chmod 755 "$A/bin/AICompanionUI.dll"
            chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$A/bin/AICompanionUI.dll"
        fi
        if [ -d "$D/quiet-home-before-update" ]; then
            rm -rf "$A/res/quiet-home"
            cp -R "$D/quiet-home-before-update" "$A/res/quiet-home"
            find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
            find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
            find "$A/res/quiet-home" -exec chown 201:0 {} \;
            find "$A/res/quiet-home" -exec chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO {} \;
        fi
        if [ -s "$D/installed-home.sha256-before-update" ]; then
            cp "$D/installed-home.sha256-before-update" "$D/installed-home.sha256"
        fi
        app_launcher -u 5001 -s "$APP" || true
    fi
    rm -rf "$stage"
    exit "$status"
}
trap rollback EXIT HUP INT TERM

test ! -e "$D"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$current_hash"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test "$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test -s "$stage/package-s90f.tar.gz"
test "$(sha256sum "$stage/package-s90f.tar.gz" | cut -d ' ' -f 1)" = "$package_hash"
mkdir -m 700 "$D"
tar -czf "$D/AICompanionUI-before-icons-update.tar.gz" -C /opt/usr/apps com.samsung.tv.AICompanionUI
cp "$A/bin/AICompanionUI.dll" "$D/AICompanionUI.dll-before-update"
printf '%s  %s\n' "$current_hash" "$A/bin/AICompanionUI.dll" > "$D/installed-home.sha256-before-update"
cp -a "$A/res/quiet-home" "$D/quiet-home-before-update"
chmod 600 "$D/AICompanionUI.dll-before-update" "$D/installed-home.sha256-before-update"

mkdir "$P"
tar -xzf "$stage/package-s90f.tar.gz" -C "$P"
test -s "$P/AICompanionUI.dll"
test -s "$P/quiet-home/apps.json"
test -s "$P/quiet-home/home-background.jpg"
test "$(sha256sum "$P/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
for f in netflix.png youtube.png jellyfin.png retroarch.png spotify.png live-tv.svg; do
    test -s "$P/quiet-home/app-icons/$f"
done
for app in org.tizen.netflix-app 9Ur5IzDKqV.TizenYouTube rTn6ClEurC.Jellyfin RtArchTzn0.RetroArch rJeHak5zRg.Spotify org.tizen.tv-viewer; do
    grep -q "\"Id\": \"$app\"" "$P/quiet-home/apps.json"
done

echo "Quiet Home current files backed up under $D"
mutating=1
app_launcher -u 5001 -k "$APP" || true
cp "$P/AICompanionUI.dll" "$A/bin/AICompanionUI.dll.new"
chown 201:0 "$A/bin/AICompanionUI.dll.new"
chmod 755 "$A/bin/AICompanionUI.dll.new"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$A/bin/AICompanionUI.dll.new"
mv "$A/bin/AICompanionUI.dll.new" "$A/bin/AICompanionUI.dll"
mv "$A/res/quiet-home" "$D/quiet-home-live-before-update"
cp -R "$P/quiet-home" "$A/res/quiet-home"
find "$A/res/quiet-home" -type d -exec chmod 755 {} \;
find "$A/res/quiet-home" -type f -exec chmod 644 {} \;
find "$A/res/quiet-home" -exec chown 201:0 {} \;
find "$A/res/quiet-home" -exec chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO {} \;
sha256sum "$A/bin/AICompanionUI.dll" > "$D/installed-home.sha256"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$new_hash"
test -s "$A/res/quiet-home/app-icons/netflix.png"
test -s "$A/res/quiet-home/app-icons/live-tv.svg"
app_launcher -u 5001 -s "$APP"
test "$(vconftool get db/appfw/home_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
test "$(vconftool get db/appfw/startup_appid | sed -n 's/^.*value = \(.*\) (String)$/\1/p')" = "$APP"
mutating=0
echo "Quiet Home updated and relaunched. Home and startup routing remain on $APP."
echo "Rollback snapshot: $D/AICompanionUI-before-icons-update.tar.gz"
