#!/usr/bin/env bash
# Build the two managed .NET 6 helpers used by the S90F setup.
set -Eeuo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
dotnet=${DOTNET:-$HOME/.local/share/dotnet6/dotnet}

"$dotnet" build "$repo/s90f/remote/remote-proxy/remote-proxy.csproj" \
    -c Release -o "$repo/.local/build/remote-proxy" --nologo
"$dotnet" build "$repo/s90f/remote/uinput-injector/uinput-injector.csproj" \
    -c Release -o "$repo/.local/build/uinput-injector" --nologo

echo "remote-proxy:      .local/build/remote-proxy/"
echo "uinput-injector:   .local/build/uinput-injector/"
echo "Deploy the proxy files to /opt/usr/share/quiet-smack-boot/remote-proxy/"
echo "and the injector to /home/owner/share/tmp/sdk_tools/uinput-injector/."
