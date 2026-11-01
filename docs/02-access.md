# Developer Mode and temporary root

## Prepare the computer

Use Python 3.12+, OpenSSL, Samsung's SDB and the .NET 6 SDK. Install SDB through
[Tizen Studio](https://developer.tizen.org/development/tizen-studio/download).
The repository intentionally does not redistribute Samsung's executable.
Set `SDB` to the absolute path of your installation. The commands below use a
macOS/Linux shell; adapt the shell syntax if using Windows.

```sh
export SDB=/absolute/path/to/tizen-studio/tools/sdb
export TV_IP=192.0.2.50
# Replace the example IP above. Read this string on YOUR TV; do not guess it.
export TV_FIRMWARE='T-KSU2EFAKUC-0090-1300.9'
tv() { python3 tools/tv.py --host "$TV_IP" --firmware "$TV_FIRMWARE" "$@"; }
python3 tools/build.py payloads
```

`192.0.2.50` is a documentation address, not a real target. The firmware
argument records what the operator verified on screen. The helper separately
checks the model reported by SDB and rejects other model/firmware combinations.

## Enable Developer Mode on the TV

On the tested TV: open Smart Hub → Apps, focus App Settings, and enter
`12345` using the remote's number input. Turn Developer Mode on, enter the
computer's LAN IP as Host PC IP, and restart the TV. The exact screen and
number-entry method vary by remote and firmware.

Samsung documents the general workflow in
[TV Device](https://developer.samsung.com/smarttv/develop/getting-started/using-sdk/tv-device.html).
The computer and TV must be able to reach each other on the local network.
Guest-network isolation or a VPN can break the return connection.

```sh
"$SDB" connect "$TV_IP:26101"
"$SDB" devices
tv doctor
tv root-check
```

`doctor` checks the SDB foothold, runtime, file capabilities and tar support.
It does not obtain root or establish compatibility for every private API.
`root-check` builds on that route, executes `id`, and requires an authenticated
UID/EUID 0 callback plus successful staging/system-file cleanup.

On this retail firmware, `sdb shell` returning `closed` is expected. The
upstream tool uses the package-installer foothold and archive launcher instead.
Do not respond by replacing passwd or Samsung's verification key.

## What the access route does

The vendored source is a pinned subset of
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root/tree/4ad2c4d3b0d0e0da4b5b7ebe4a787e94596f416b).
It uses the SDK foothold, capability-bearing Samsung dotnet host, a private
mount namespace and signed-archive launcher to run a temporary authenticated
root agent. Our local runtime check handles the U8000F host's unsupported
`--list-runtimes` option by checking the resolved CLR files.

Root remains constrained by Samsung's security mechanisms. This work did not
unlock secure boot, flash another OS, disable every execution restriction or
install a permanent TV-side root service. Do not use the upstream QN90B/QN90F
kernel exploit commands as substitutes for this U8000F route.

## Commands, files and cleanup

```sh
tv exec --command 'id'
tv exec --script recipes/status.sh
tv push .local/package.tar.gz package.tar.gz
tv pull /absolute/path/on/tv .local/private-copy
```

`push` is restricted to the SDK staging directory and verifies SHA-256.
It leaves the staged file until explicitly removed. `pull` validates a
compressed transfer and saves only under `.local/`. Its limit is 760,000
compressed bytes and 32 MiB uncompressed, to stay within the upstream command
output limit. Larger snapshots must be split or transferred with a separately
reviewed tool; truncated output is never accepted.

`exec --script` runs a reviewed script through the shell with optional repeated
`--arg VALUE` positional arguments. There is a 30-second command budget; keep
phases short. Logs are private and can contain device details. Do not attach
raw session JSON to public issues.

Use one SDB/root operation at a time. If route detection selects the wrong
interface, pass `--callback-host COMPUTER_LAN_IP` **before** the subcommand.
After reboot, a stale SDB server may need:

```sh
"$SDB" kill-server
"$SDB" start-server
"$SDB" connect "$TV_IP:26101"
```

Let each root session finish its cleanup before restarting or powering down.
If interrupted, inspect the specific `archive-root-*` staging path reported
by the helper. Verify the target and remove only that abandoned session's
files. Never broad-delete the SDK tools directory.

## S90F live profile

The `QN55S90FAFXZA` live setup uses the same archive-root route with the
S90F-specific helper `s90f/tools/root_probe.py`. It checks the exact model and
firmware, pins the callback ports, retries TIME_WAIT binds and runs bounded
root scripts. The tested working layout, deploy commands and recovery are in
[`s90f/AGENTS.md`](../s90f/AGENTS.md). Do not reuse the S90F boot payload or
selectors on another model.
