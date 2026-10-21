# Build and install Quiet Home

Quiet Home is a native NUI/.NET application, with Home/startup and remote-key
routing adjusted to make it act as the launcher. It does not replace the
kernel or the whole Tizen shell. Samsung's settings, app framework and media
stack remain available underneath.

The design follows Free My TV: light background, wide feature card, two
portrait cards, colorful tiles, rounded controls and a translucent dock.
All UI text here is English. See [attribution](../NOTICE.md).

## Obtain matching private framework references

Build against the TV's own compatible `Tizen.NUI.dll`,
`Tizen.Applications.Common.dll`, `Tizen.System.dll` and `Tizen.dll`.
The shipped project files use `Private=false`, so those references are not
copied into the app package.

Find the paths on the target:

```sh
tv exec --command 'find /usr/share/dotnet.tizen -name Tizen.NUI.dll -o -name Tizen.Applications.Common.dll -o -name Tizen.System.dll -o -name Tizen.dll'
```

Inspect the results and pull the four matching runtime assemblies individually
with `tv pull REMOTE_PATH .local/tv-framework/NAME.dll`. Do not use a random
desktop/mobile SDK version just because it has a file with the same name.
Do not commit the resulting assemblies.

```sh
python3 tools/build.py launcher --framework .local/tv-framework
```

This builds `BixbyPromotion.dll`, `QuickLaunch.dll` and `Probe.dll`, then
assembles `.local/package/`. For another documented model, add its profile, for
example `--profile profiles/qe65s95fauxru-1301.0.json`; the profile's
`launcher` block names the host package and the entry assembly to build.
Public source cards are neutral text placeholders;
[optional publisher artwork](06-artwork.md) can be fetched before rebuilding.

## Adapt inputs and apps

The original UI uses HDMI 2 as the wide PlayStation 5 card, HDMI 3 as the
Switch card, and HDMI 1 as the third card. Source IDs 14, 15 and 13 were observed
on the tested TV. They are example wiring, not auto-discovery.

Upload and run Probe to inspect sources and the current main-operation handler:

```sh
tv push .local/build/Probe/Probe.dll Probe.dll
tv exec --command '/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/quiet-tizen/Probe.dll'
```

Edit labels, source actions, `RefreshSource`, `SourceIndex` and the default
`lastSource` in `launcher/src/Home.cs` to match the actual devices. The library
is read from `apps.json`; verify all app IDs against the TV. See
[app configuration](06-artwork.md). Rebuild after source changes.

## Install without changing Home yet

On the U8000F the native-app container is **`com.samsung.tv.bixby-promotion`**.
Its `BixbyPromotion.dll` is replaced with our assembly, while the package's
existing identity, metadata and framework integration are retained. This
replaces Bixby Promotion's function. It is not a store-signed standalone TPK.

Inspect the installed package, its owner/labels, original entry assembly and
current registry flags first. This release's recipe requires the observed
owner `201:0`. If the layout differs, stop and adapt the profile.

```sh
tv exec --script recipes/snapshot.sh --arg home-01
tar -czf .local/package.tar.gz -C .local/package .
tv push .local/package.tar.gz package.tar.gz
tv exec --script recipes/install-launcher.sh --arg home-01
```

Another profile can name a different host in its `launcher` block. The
QE65S95F profile uses `com.samsung.tv.adplayer` and `AdPlayer.dll`, because
Bixby Promotion is not installed there. Append both values to the last
command above, so it becomes:

```sh
tv exec --script recipes/install-launcher.sh --arg home-01 \
  --arg com.samsung.tv.adplayer --arg AdPlayer.dll
```

Append them later to `restore-launcher.sh` as well, and use that app ID in the
Home and startup commands. The settings-bridge recipes still target Bixby
Promotion only.

The recipe backs up the original package before replacing the assembly,
moves the cached native image out of the execution path, installs resources,
applies the package's observed SMACK label and requests a manual launch.
It does not change Home/startup.

The new release recipes are a generalized form of the operations used on the
original TV. Filesystem steps are not a single atomic transaction. If a step
fails, inspect the saved state and use recovery; do not rerun by deleting
the original backup. The snapshot and backup folder is
`/opt/usr/share/quiet-tizen-backups/home-01`.

Verify visibly:

- All pages render; the D-pad, Select and Back behave correctly.
- HDMI cards switch the intended input, with picture and audio.
- Volume/mute and applicable quick settings work.
- Native Advanced and Network settings still open.
- Chosen app shortcuts launch the correct installed apps.
- The Controllers shortcut reaches the Bluetooth device list.

The `build_ms` value in `/tmp/quiet-home-state.txt` measures scene construction,
not input-to-photon latency or complete rendering time.

## Make it open on Home and startup

Save the **three original values** privately first: the main-operation Home
handler printed by Probe, `db/appfw/home_appid`, and
`db/appfw/startup_appid`. They all happened to be `com.samsung.tv.csfs` on the
case-study device; restoration must use the actual saved values.

Only after the visible verification above:

```sh
tv exec --command '/usr/bin/dotnet /opt/usr/share/quiet-tizen-backups/home-01/Probe.dll set-home com.samsung.tv.bixby-promotion'
tv exec --command 'vconftool set -f -t string db/appfw/home_appid com.samsung.tv.bixby-promotion; vconftool set -f -t string db/appfw/startup_appid com.samsung.tv.bixby-promotion'
```

Read all three selectors back. Let temporary root cleanup finish, then
restart with the remote. Check full boot, the Home button, standby/wake
and return from a streaming app separately. Automatic startup was verified
on the original TV; an OS update can change routing.

## Replace the slow settings/sidebar path

The quick settings page handles volume, mute, brightness, Game Mode and
sleep timer with native APIs. Availability is checked for the current input.
Advanced settings, network setup and Bluetooth pairing still use Samsung's
native menu on demand.

The small QuickLaunch bridge exits on vendor `launch_type=preload` requests.
For interactive requests it opens Quiet Home's settings page and exits.
It does not keep a second heavy settings process running.

After quick settings work, take a new snapshot and install the bridge:

```sh
tv exec --script recipes/snapshot.sh --arg shell-01
tv exec --script recipes/install-settings-bridge.sh --arg shell-01
```

This replaces `/opt/usr/apps/com.samsung.tv.quicklaunch/bin/QuickLaunch.dll`
and updates two `key_filter` rules:

| Rule owner / key | New destination |
|---|---|
| `com.samsung.tv.quicklaunch` / `XF86More` | Quiet Home, `quiet_page:settings` |
| `org.tizen.menu` / `XF86SysMenu` | Quiet Home, `quiet_page:settings` |

The recipe selects semantic keys and checks the saved values. It does not
copy another TV's row numbers. It notifies
`memory/appfw/app_context_db_change` after the transaction.

Test both settings buttons, then generate/apply the **`light-shell`** cleanup
group from the `shell-01` registry snapshot. That disables the native sidebar
and browser. Keep the QuickLaunch bridge and `org.tizen.menu` enabled.

Retain rollback files and remove only the known staged files after verification:

```sh
tv exec --command 'rm -f /home/owner/share/tmp/sdk_tools/quiet-tizen/package.tar.gz /home/owner/share/tmp/sdk_tools/quiet-tizen/Probe.dll; rm -rf /home/owner/share/tmp/sdk_tools/quiet-tizen/unpacked'
```

## Performance choices in the launcher

App art is local. Real `ImageView` objects are created ahead of use and moved
between the hidden cache parent and visible cards. `ReleasePolicy=Destroyed`
keeps decoded textures alive while those views live. The cache is bounded
by catalog size and the grid/dock variants, not an ever-growing screenshot
cache. Image loading is asynchronous, so a first launch still needs loading
time; subsequent page visits avoid recreating image views.

The clock updates every 30 seconds and stops while the launcher is paused.
There is no always-running controller-poll loop. The 180 ms repeat filter
applies inside Quiet Home only; changing it cannot fix input lag inside Netflix.
Local diagnostic files retain only current launcher state and are overwritten;
the launcher has no telemetry/network client.
