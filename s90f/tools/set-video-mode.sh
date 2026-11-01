#!/bin/sh
set -eu
mode=${1:?mode required}
case "$mode" in underlay|texture|off) ;; *) exit 2;; esac
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
APP=com.samsung.tv.AICompanionUI
R=$A/res/quiet-home
app_launcher -u 5001 -k "$APP" || true
rm -f /tmp/quiet-home-video.txt
printf '%s\n' "$mode" > "$R/video-mode.txt"
chown 201:0 "$R/video-mode.txt"; chmod 644 "$R/video-mode.txt"
chsmack -a User::Pkg::com.samsung.tv.AICompanionUI::RO "$R/video-mode.txt"
app_launcher -u 5001 -s "$APP"
echo "video mode set to $mode"
