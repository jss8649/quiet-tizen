# S90F remote input helpers

Both helpers target .NET 6 and use only the base class library and P/Invoke.
They are built from source, not copied from the TV.

## remote-proxy

The always-on interceptor approved by the owner. It creates a uinput device
named `Smart Control`, grabs the live Smart Control and Remote-Input
keyboards, forwards every event and consumes only kernel keycode 529
(YouTube, launches `9Ur5IzDKqV.TizenYouTube`) and 560 (TV Plus, launches
Jellyfin). Apps are started with `/usr/bin/app_launcher --user 5001 -s`.

Deployed files: `remote-proxy.dll`, `remote-proxy.deps.json` and
`remote-proxy.runtimeconfig.json` in
`/opt/usr/share/quiet-smack-boot/remote-proxy/`. The AT-HUB launch starts it
as a transient `quiet-remote-proxy` unit with `Restart=always`.

Stop it with:

```sh
systemctl stop quiet-remote-proxy.service
```

If it is not running, YouTube opens the stock Cobalt app and TV Plus opens
the disabled dialog.

## uinput-injector

A test tool. It injects one kernel keycode through `/dev/uinput` so the real
CP handlers can be exercised without a physical press. Kernel codes observed
on this TV: Amazon 221, Netflix 226, YouTube 529, TV Plus 560. The xkb code
is the kernel code plus 8.

Deployed path: `/home/owner/share/tmp/sdk_tools/uinput-injector/`. Run it as
root from a root session:

```sh
/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/uinput-injector/uinput-injector.dll 529
```

Verify the result with
`vconftool get memory/appfw/current_fullscreen_appid`.

## Build

```sh
s90f/remote/build.sh
```

Outputs go to `.local/build/`. The binary DLLs are intentionally not
committed; rebuild them from this source.
