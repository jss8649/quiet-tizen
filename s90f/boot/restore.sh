#!/bin/sh
set -u
D=/opt/usr/share/quiet-smack-boot
ORIG=/opt/etc/parseinfo.sh
TMP=/opt/etc/.quiet-smack-restore.$$
mkdir -m 700 "$TMP" || exit 1
cp --preserve=all "$D/original" "$TMP/parseinfo.sh" || exit 1
mv -f "$TMP/parseinfo.sh" "$ORIG" || exit 1
rmdir "$TMP" 2>/dev/null
rm -rf "$D"
systemctl start AT-HUB.service || true
echo restored
