#!/bin/sh
set -u
A=/opt/usr/apps/com.samsung.tv.AICompanionUI
R=$A/res/quiet-home
echo "=== DLL ==="
sha256sum "$A/bin/AICompanionUI.dll" 2>&1
echo "=== STATE ==="
cat /tmp/quiet-home-state.txt 2>&1
echo "=== VIDEO LOG ==="
tail -30 /tmp/quiet-home-video.txt 2>&1
echo "=== WEATHER LOG ==="
tail -20 /tmp/quiet-home-weather.txt 2>&1
echo "=== PROC ==="
ps -ef 2>/dev/null | grep AICompanionUI | grep -v grep | cut -c1-160
echo "=== VIDEO MODE ==="
cat "$R/video-mode.txt" 2>&1
echo VERIFY_LAUNCHER_DONE
