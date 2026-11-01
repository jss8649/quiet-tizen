#!/bin/sh
set -eu

name=${1:?Backup name required}
stage=${2:?Unique temporary staging path required}
expected_hash=${3:?Expected installed assembly hash required}
case "$name" in quiet-home-s90f-[A-Za-z0-9_-]*) ;; *) exit 2;; esac
case "$stage" in /home/owner/share/tmp/sdk_tools/quiet-tizen-install-*) ;; *) exit 2;; esac
D=/opt/usr/share/quiet-tizen-backups/$name
A=/opt/usr/apps/com.samsung.tv.AICompanionUI

test -s "$D/AICompanionUI-original.tar.gz"
test -s "$D/.pkgmgr_parser.db"
test "$(sha256sum "$A/bin/AICompanionUI.dll" | cut -d ' ' -f 1)" = "$expected_hash"
test -s "$A/res/quiet-home/apps.json"
test -s "$A/res/quiet-home/free-background.svg"
test -s "$D/installed-home.sha256"
grep -q 'Quiet Home installed as the AI Companion UI' "$D/install-phase.txt"

app_launcher -u 5001 -s com.samsung.tv.AICompanionUI
rm -rf "$stage"
test ! -e "$stage"
echo "Quiet Home verified and launch requested: $A"
echo "Recovery backup: $D; Home and startup selectors remain unchanged."
echo "Temporary upload stage removed: $stage"
