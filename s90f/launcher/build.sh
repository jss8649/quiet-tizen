#!/usr/bin/env bash
# Build the S90F Quiet Home assembly and stage the update package.
# Run from anywhere; paths are resolved from this file.
set -Eeuo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"

dotnet=${DOTNET:-$HOME/.local/share/dotnet6/dotnet}
framework=${TV_FRAMEWORK_DIR:-$repo/.local/tv-framework}
out=$repo/.local/build/S90F
stage=$repo/.local/package-dll
res=$stage/quiet-home

for assembly in Tizen.NUI.dll Tizen.Applications.Common.dll Tizen.System.dll Tizen.dll; do
    if [ ! -s "$framework/$assembly" ]; then
        echo "Missing TV framework reference: $framework/$assembly" >&2
        echo "Pull the four assemblies from the TV; do not commit them. See s90f/AGENTS.md." >&2
        exit 1
    fi
done

"$dotnet" build "$repo/s90f/launcher/AICompanionUI.csproj" -c Release \
    -o "$out" --nologo -p:TV_FRAMEWORK_DIR="$framework"
test -s "$out/AICompanionUI.dll"

mkdir -p "$stage" "$res"
cp "$out/AICompanionUI.dll" "$stage/AICompanionUI.dll"
cp "$repo/s90f/launcher/apps.json" "$res/apps.json"
cp "$repo/s90f/launcher/assets/fireplace.json" "$res/fireplace.json"
cp "$repo/s90f/launcher/assets/video-mode.txt" "$res/video-mode.txt"
cp "$repo/s90f/launcher/assets/extra/"*.svg "$res/"

for media in fireplace.mp4 home-background.jpg; do
    if [ ! -s "$res/$media" ]; then
        echo "Note: $res/$media is a local-only asset and is absent." >&2
        echo "The update tar will not replace it, but the TV must already have it." >&2
    fi
done

tar -czf "$repo/.local/package-dll.tar.gz" -C "$stage" .
sha256sum "$stage/AICompanionUI.dll" "$repo/.local/package-dll.tar.gz"
echo
echo "Before deploying, set the installed-hash constant in the"
echo "update-launcher-dll block of s90f/tools/root_probe.py to the DLL hash above."
