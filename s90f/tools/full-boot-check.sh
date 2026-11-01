#!/bin/sh
D=/opt/usr/share/quiet-smack-boot
echo "=== BOOT ==="
date
cat /proc/sys/kernel/random/boot_id
tail -20 "$D/runs.log"
echo "=== YOUTUBE ROUTING ==="
grep -c '9Ur5IzDKqV.TizenYouTube' /opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/apps.json 2>&1
ls -d /opt/usr/apps/9Ur5IzDKqV 2>&1
ls -d /opt/usr/apps/xvvl3S1TT1 2>&1
echo "=== PROXY ==="
systemctl is-active quiet-remote-proxy.service 2>&1
ps -ef 2>/dev/null | grep remote-proxy | grep -v grep | cut -c1-120
tail -4 "$D/remote-proxy.log" 2>&1
echo "=== ACTIVATE ==="
tail -6 "$D/activate.log" 2>&1
echo "=== LAUNCHER ==="
sha256sum /opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.dll
tail -18 /tmp/quiet-home-video.txt 2>&1
head -5 /tmp/quiet-home-state.txt 2>&1
echo "=== SELECTORS ==="
vconftool get db/appfw/home_appid 2>&1
vconftool get db/appfw/cp_key_appid1 2>&1
vconftool get db/appfw/cp_key_appid2 2>&1
vconftool get db/appfw/cp_key_appid3 2>&1
echo "=== HOOK ==="
head -c 100 /opt/etc/parseinfo.sh 2>&1; echo
tail -7 "$D/launch"
echo FULL_BOOT_CHECK_DONE
