# S90F live Quiet Home: agent handoff

This folder records the exact, owner-authorized setup running on one Samsung
`QN55S90FAFXZA` (S90F). It is a maintenance record for a live TV, not a generic
installer. Read this file before changing anything.

## Read this first

- **Exact target:** model `QN55S90FAFXZA`, firmware `T-RSMFAKUC-0090-1301.0`,
  build `T-RSMFAKUC-0090-REL-202607141953`, Tizen 9.0.0, kernel 5.4.261,
  32-bit ARM userspace. If any of these differ, stop. Do not reuse this
  profile on another model or firmware.
- **The TV is the source of truth.** Verify the current state before acting.
  A hash, path or selector in this folder is an observation from the verified
  build, not a universal constant.
- **Public fork hygiene.** This folder is sanitized for a public fork. Raw
  device addresses, logs, session JSON, database snapshots, the personal
  still photo, weather coordinates, publisher app icons, the fireplace video
  and Samsung framework assemblies stay in the ignored `.local/` tree. See
  [Public fork hygiene](#public-fork-hygiene).
- **Hard limits:** do not flash firmware, replace the bootloader, remove
  partition contents, alter `/etc/passwd` or replace Samsung's SDB
  verification key. UID 0 does not defeat SMACK, UEP or secure boot. No
  custom OS path was established for this model.
- **Preserve:** HDMI, display, audio, networking, Bluetooth, package and app
  management, accessibility and the owner's streaming apps. Never globally
  disable `org.tizen.menu`. Bixby Promotion is repurposed and must stay
  enabled.
- **The remote interceptor is an owner-approved always-on root daemon.** It is
  an explicit exception to the repository's usual no-hidden-daemon rule. It
  only reads local input devices, forwards them and launches two local apps.

## Verified state on 2026-10-27

- Quiet Home is installed as `com.samsung.tv.AICompanionUI`. The installed
  assembly hash is
  `d8c93de9021fb2843c40a25b6f29718711fe34b7eb5834acf31998e6ed97e6ac`.
  The source in `launcher/` rebuilds byte-identical to that hash with the
  portable project file.
- `db/appfw/home_appid` is `com.samsung.tv.AICompanionUI`.
- CP key slots: slot 1 `3201907018807` (Netflix), slot 2 `3201606009684`
  (Spotify), slot 3 `111299001912` (YouTube store app).
- Physical buttons: Prime opens Spotify, YouTube opens Samsung's own YouTube
  app, TV Plus opens Jellyfin, Netflix opens Netflix.
- The AT-HUB boot hook runs the original parseinfo, sets NTP timeservers,
  writes both TizenTube SMACK rules, starts the remote proxy and starts the
  early Home activation.
- A full unplug was verified: both SMACK rules re-applied, the proxy grabbed
  the input devices, the activation loop logged `activated at try 1`, Home
  resumed immediately after `OnCreate`, and all four buttons worked.
- A cold boot after the activation fix showed the menu about 11 to 12 seconds
  after the Samsung logo. Standby wake is immediate. The old 40 second delay
  was the system postponing `OnResume`, not weather or network setup.

## Boot chain

```text
AT-HUB.service
  -> /opt/etc/parseinfo.sh (gawk wrapper)
     -> cat /opt/usr/share/quiet-smack-boot/launch | /bin/bash
        -> run the preserved original parseinfo
        -> set ConnMan NTP timeservers
        -> write both TizenTube SMACK rules to load2
        -> start the transient quiet-remote-proxy unit
        -> start the transient quiet-home-activate unit
```

The wrapper replaces Samsung's parseinfo with a gawk shebang that reads the
launch script through stdin. UEP blocks executing an unsigned script by
path, including `bash -n` on the launch file, but it does not block a signed
interpreter reading the script from stdin.

The launch exits without acting if the build, the AT-HUB unit hash or the
preserved original parseinfo hash changes. Those checks are deliberate:
firmware drift means the profile must be re-inspected, not forced.

### Early Home activation

The launcher is created by the system at boot but was not resumed until about
47 seconds, so the underlay fireplace played while the menu stayed invisible.
The activation unit calls:

```sh
/usr/bin/app_launcher -u 5001 -s com.samsung.tv.AICompanionUI
```

every 2 seconds, up to 10 tries, and stops once
`/tmp/quiet-home-state.txt` exists plus one extra call. It logs to
`/opt/usr/share/quiet-smack-boot/activate.log`. On the verified boot it
stopped at try 1 and `OnResume` ran one second after `OnCreate`.

Do not extend this loop blindly. It is bounded so it cannot pull the TV back
to Home while the owner is opening another app.

## Files on the TV

| Path | Purpose |
|---|---|
| `/opt/etc/parseinfo.sh` | gawk wrapper, installed over Samsung's parseinfo |
| `/opt/usr/share/quiet-smack-boot/original` | preserved Samsung parseinfo, not in the repo |
| `/opt/usr/share/quiet-smack-boot/launch` | boot payload: original, NTP, SMACK rules, proxy, activation |
| `/opt/usr/share/quiet-smack-boot/wrapper` | source of the gawk wrapper |
| `/opt/usr/share/quiet-smack-boot/restore.sh` | restores `original` and removes the payload |
| `/opt/usr/share/quiet-smack-boot/runs.log` | per-boot evidence and rule return codes |
| `/opt/usr/share/quiet-smack-boot/activate.log` | activation attempts |
| `/opt/usr/share/quiet-smack-boot/remote-proxy/` | remote proxy DLL and runtime files |
| `/opt/usr/share/quiet-smack-boot/remote-proxy.log` | proxy startup and launch evidence |
| `/opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.dll` | installed launcher |
| `/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/` | launcher resources |
| `/tmp/quiet-home-video.txt` | launcher startup, video, lifecycle and key log |
| `/tmp/quiet-home-state.txt` | current launcher state |
| `/tmp/quiet-home-weather.txt` | weather cache and fetch log |
| `/opt/usr/share/quiet-tizen-backups/` | per-deploy DLL and resource backups |

The `runs.log`, activation log, proxy log, state files and backups are
private. Do not paste them into a public issue or commit.

## Launcher source and build

The installed launcher is a decompiled and heavily patched Samsung
`AICompanionUI` assembly, not the generalized `launcher/src` from the U8000F
case study. Its source is `launcher/QuietHome.cs` with `AppLibrary.cs` and
`LibraryApp.cs`. The patches cover the fireplace underlay, app library,
settings page, clock and weather widget, startup visibility and lifecycle
logging. This is a local build for the owner's TV, not a redistributable app.

### Framework references

Build against the TV's own `Tizen.NUI.dll`, `Tizen.Applications.Common.dll`,
`Tizen.System.dll` and `Tizen.dll`, placed in `.local/tv-framework/`. They are
proprietary and are not committed. The project uses `Private=false`, so they
are not copied into the output.

### Build

```sh
s90f/launcher/build.sh
```

The script builds to `.local/build/S90F/AICompanionUI.dll`, stages
`.local/package-dll/` and creates `.local/package-dll.tar.gz`. The tar has the
DLL at its root and resources under `quiet-home/`. `apps.json`,
`fireplace.json`, `video-mode.txt` and the Lucide SVGs are refreshed; the
fireplace video and the startup still are local-only assets and are left
alone if absent.

The portable project reproduces the live hash
`715edef76d5915194019375ab5f700353a828a7b2de10e6d421a778cbbbbdac3` with the
same source and framework references. If a new build produces a different
hash, that is expected after a source change; update the hash constant and
keep the old backup.

### Deploy

The tested deploy tool expects this ignored working layout:

```sh
mkdir -p .local/s90f-candidate
cp s90f/tools/* .local/s90f-candidate/
python3 tools/build.py payloads
```

The install, catalog, icon, backdrop, keymap and restore helpers in
`tools/` are the historical install path, kept so a fresh rebuild or a
recovery can follow the same steps. The keymap edits were reverted and are
not part of the live setup; the CP slots and the proxy handle the keys now.
Routine launcher updates use only `update-dll.sh`.

Then, with the TV reachable and Developer Mode still enabled:

```sh
PYTHONPATH=vendor python3 .local/s90f-candidate/root_probe.py \
  --host "$TV_IP" --firmware T-RSMFAKUC-0090-1301.0 \
  --callback-host "$HOST_IP" \
  --update-launcher-dll quiet-home-s90f-YYYYMMDD-name
```

`update-dll.sh` verifies the installed DLL hash against the constant in the
`update-launcher-dll` block of `root_probe.py`. Set that constant to the
currently installed hash **before** deploying a new one. Never force past a
hash mismatch; inspect the installed file and backups instead.

The handler kills the app, copies the files, then kills it a second time
after the copy. The Home slot auto-restarts the killed app from the old
inode while the copy is in progress; the second kill is what makes the new
DLL the running one. Do not remove it.

### Launcher resources

Committed here: `apps.json`, `fireplace.json`, `video-mode.txt`, the weather
example and the eight Lucide SVGs. Reused from `launcher/assets/`: Quiet
Inter fonts, placeholder cards, Free My TV symbols and the other SVGs.

Not committed, because they are local-only, third-party or personal:

- `fireplace.mp4` (23,626,429 bytes,
  `fcc7c23c792557262748abe6b3d424a5ef720e6f671460bfa4678ea310567574`)
  in `.local/package-dll/quiet-home/`. It is the ambient video and its
  license/provenance is not recorded here.
- `home-background.jpg` (207,895 bytes,
  `2c22ac800535a298c36bd0ed207b24d1a92194264413e10aa6f8685bdcd6c80a`)
  in the same directory. It is a still extracted from the video.
- `weather.json`, which contains the owner's coordinates. Use
  `weather.json.example` and set the real values on the TV only.
- Publisher app icons under `app-icons/`. They remain in the ignored
  `launcher/assets/app-icons/` and `.local/tv-app-icons/`.
- `button-glass.svg`, `icon-apps.svg`, `icon-hdmi.svg` and
  `icon-settings.svg`, which exist in the live resource directory. They were
  not copied into this folder because the TV was unreachable at commit time.
  Pull them before a fresh reinstall; the live launcher already has them.

## Startup behavior that must not regress

These fixes were made after the owner reported a black launcher, a missing
page and a delayed fireplace. They are order-dependent.

1. The static still (`home-background.jpg`) is added before the video. It is
   a fireplace frame, so the splash matches the video.
2. Video creation is deferred about 3 seconds through a **field-held**
   `videoStartTimer`. A local `Timer` was garbage collected before it fired.
   Any new timer must be stored in a field.
3. The window background stays opaque until the video is created. Setting it
   transparent at the start left the window black before the underlay plane
   existed.
4. The video and the 50 percent dim view are added, then lowered with
   `LowerToBottom()`. The page is rebuilt immediately before `Play()`.
5. `Play()` can block the UI thread for tens of seconds on a cold boot.
   Nothing that the user needs to see may be built after `Play()`. The page
   is already on screen; the render thread keeps drawing while the call
   blocks.
6. The page is also rebuilt by keys and app controls. A keypress that raises
   a tile is not a fix for a hidden page; the z-order and the pre-`Play`
   rebuild are the real fixes.
7. The clock label is set from `DateTime.Now` and updated every second. It
   does not wait for weather.
8. Weather is fetched on a worker thread, not on the UI thread. The first
   fetch is deferred 15 seconds after startup; cached values and
   `Retrieving weather...` or `Refreshing weather...` status text are shown
   meanwhile. Weather was not the cause of the 40 second menu delay.
9. `OnResume` raises and activates the window, replays the video and restarts
   the clock. `OnPause` pauses the video and stops the clock.
10. Startup is complete in about 3 seconds on the verified build; the menu
    timing after boot is dominated by when the system resumes the app.
11. The video watchdog calls `Play()` every 5 minutes while the app is resumed,
    the backdrop exists and the fireplace timer has not expired. It exists
    because the media pipeline can wedge at 0 percent decode while
    `muse-server` still holds `fireplace.mp4` open; only a `Play()` or an app
    restart clears it. It stops calling after three calls that each block for
    5 seconds or more, so a permanently broken pipeline cannot turn into a
    repeating freeze.
12. `OnResume` logs `onresume t base|raise|play|source|settings` in
    milliseconds. Use those to locate a slow resume instead of guessing. On
    the observed build a resume after a long idle can take about 20 seconds
    while a resume in quick succession takes under one second; that tracks
    memory pressure and swap, so check `MemAvailable` and `SwapFree` first.

Diagnostic evidence is written to `/tmp/quiet-home-video.txt`. Useful markers:
`oncreate start`, `oncreate page`, `created`, `onresume start/done`,
`repaint before play`, `play begin`, `play returned`.

## Button map and input proxy

The dedicated remote keys are handled by `tvctx-manager` CP keys. The app
IDs are stored in vconf `db/appfw/cp_key_appid1..3` and accept **Samsung
store IDs only**. Replacing slot 3 with a sideloaded app ID does nothing.
Slot 2 is the Prime Video slot; it now contains Spotify's store ID.

| Key | Path | Result |
|---|---|---|
| Prime Video | CP slot 2 | Spotify |
| Netflix | CP slot 1 | Netflix |
| YouTube | remote proxy consumes kernel keycode 529 | `9Ur5IzDKqV.TizenYouTube` |
| Samsung TV Plus | remote proxy consumes kernel keycode 560 | `rTn6ClEurC.Jellyfin` |

### YouTube: stock app only

TizenTube (`xvvl3S1TT1`) was uninstalled on 2026-11-01, and its SMACK lines
were removed from the boot launch the same day. YouTube opens Samsung's own
app (`9Ur5IzDKqV.TizenYouTube`) from both the catalog and the remote proxy.
There is no in app SponsorBlock, no DeArrow and no ad blocking; the owner chose
stock over a custom client, so do not reintroduce one without being asked.

An iSponsorBlockTV trial was set up on the homelab and then removed at the
owner's request, including the container, the image and the data directory.

The removed package was copied to
`/opt/usr/share/quiet-tizen-backups/tizentube-2.1.3/app`. That copy is not
installable as is; restoring TizenTube means rebuilding it and signing with a
Partner certificate.

### Memory trim (persistent, applied 2026-11-01)

The TV has 1.9 GB of RAM and a 1.24 GB zram swap. After five days of uptime
swap was about 93 percent full. The owner's rule for this work: every change
must survive a reboot on its own, so nothing here relies on a manual cleanup.

Three mechanisms, all self restoring:

1. **Service stop markers.** Vendor units carry a negated
   `ConditionPathExists`. Creating the file makes systemd refuse to start the
   unit forever. In place: `/opt/usr/share/systemd/system/slive-provider-daemon`
   for TV Plus and `/opt/usr/share/systemd/system/bms` for its BMS service.
   Verified with `systemctl start`, which leaves `ConditionResult=no` and
   `ActiveState=inactive`. Remove the file to undo.
2. **Runtime masks reapplied at boot.** `contents-recognition-service`,
   `org.tizen.tv.sp-kpi`, `data-service` and `ipa` have no stop-file condition
   and their unit files are not writable, so the boot launch runs
   `systemctl mask --runtime --now` on all four every boot. Look for the
   `mask:` lines in `runs.log`.
3. **Preload flags.** `db/was/preload_by_country` is false and the cached copy
   in `/opt/dbspace/.webappservice.db` `WASConfigTable` `RESERVED_18`
   `$.rsp.preloadByCountry` is false. Samsung catalog refreshes have restored
   these before, so recheck after a firmware or catalog update.

Closing preloaded apps with `app_launcher -u 5001 -r` does **not** work on this
build: most return "not available for the user 5001", and the ones that accept
the request are running again seconds later. Do not rely on it and do not build
a periodic killer around it.

The zram device is the swap: `/sys/block/zram0/mm_stat` reports compressed size
and real RAM used. A full swap is not by itself a fault; check
`MemAvailable` and whether anything actually stalls.

The proxy is `/opt/usr/share/quiet-smack-boot/remote-proxy/remote-proxy.dll`.
It creates a uinput device named `Smart Control`, grabs `/dev/input/event3`
(Smart Control), event6, event28 and event29 (Smart Control 2016) and event13
(Remote-Input Keyboard), forwards every event and consumes only 529 and 560.
It launches apps with:

```sh
/usr/bin/app_launcher --user 5001 -s <app-id>
```

The uinput device name matters: `Smart Control` is accepted by keymanager;
other names were not. The output device is excluded from the grab list.

Kernel keycodes observed in `/usr/share/X11/xkb/tizen_key_layout.txt.tv`:
Amazon 221, Netflix 226, YouTube 529, TV Plus 560. The xkb code is the
kernel code plus 8. The injector at `remote/uinput-injector/` can inject a
key for testing:

```sh
/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/uinput-injector/uinput-injector.dll 529
```

If the proxy dies, YouTube opens the stock Cobalt app and TV Plus shows the
disabled dialog. That is the expected fallback, not a probe failure. Verify
the proxy with `systemctl is-active quiet-remote-proxy.service`, the reader
lines in `remote-proxy.log`, and an injector test while watching
`vconftool get memory/appfw/current_fullscreen_appid`.

## Debug and verification

Run root scripts one at a time. Keep each below the 30 second command budget.
The callback ports 40028 and 40029 can sit in TIME_WAIT; the helper retries,
and a full power cycle resets a wedged SDB daemon.

Useful checks:

```sh
sha256sum /opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.dll
cat /tmp/quiet-home-state.txt
tail -30 /tmp/quiet-home-video.txt
tail -20 /tmp/quiet-home-weather.txt
systemctl is-active quiet-remote-proxy.service
tail -20 /opt/usr/share/quiet-smack-boot/remote-proxy.log
tail -20 /opt/usr/share/quiet-smack-boot/activate.log
vconftool get db/appfw/home_appid
vconftool get db/appfw/cp_key_appid1
vconftool get db/appfw/cp_key_appid2
vconftool get db/appfw/cp_key_appid3
```

The repo copy of the boot check is `tools/full-boot-check.sh`. It checks the
boot log, both SMACK rules, the proxy, the activation log, the launcher hash,
the selectors and the time.

`build_ms` in the state file measures scene construction, not input to photon
latency. A process disappearing once is not proof of persistence. Test a full
unplug and a standby wake separately. Physical button presses are the only
acceptable proof for the four rebinds.

## Recovery

### Stop the remote proxy and activation

```sh
systemctl stop quiet-remote-proxy.service
systemctl stop quiet-home-activate.service
```

The transient units do not survive a reboot. To stop them permanently,
remove the `# Quiet remote key proxy` and `# Quiet Home early activation`
blocks from the launch, or run the full restore below.

### Restore the AT-HUB boot hook

```sh
/opt/usr/share/quiet-smack-boot/restore.sh
```

This copies the preserved original parseinfo back with owner, mode and label,
removes the payload directory and starts AT-HUB. It also removes the proxy
files, so stop the proxy first if it is still running.

### Restore the launcher

Every deploy keeps the previous DLL and any replaced resources under
`/opt/usr/share/quiet-tizen-backups/<name>/`. To roll back, copy
`AICompanionUI.dll.before` back, restore the `orig/` resource files listed in
`files.txt`, then set the app's owner, mode and SMACK label and relaunch. The
update script does this automatically on failure; do not delete the first
backup to make a retry succeed.

### Restore Home and CP selectors

Read the original values from the saved snapshot or backup before changing
anything. The live values are Home `com.samsung.tv.AICompanionUI` and the
three CP store IDs above. Do not assume the stock Home app ID; it was not
recorded in this folder and must come from the owner's snapshot.

### Registry recovery

A direct `sqlite3` read of `/opt/dbspace/.pkgmgr_parser.db` once truncated the
live registry to zero bytes. The recovery used a `.backup` snapshot, let
Tizen rebuild what it could, and merged missing rows field by field with a
drift check. The merged snapshot and the missing list are under
`/opt/usr/share/quiet-tizen-backups/smack-persist/`. Any write to the live
registry must zero the `.pkgmgr_parser.db-journal` header before and after;
otherwise vdfs can roll the edit back when the next client opens the file.
Never replace the live registry with an old database wholesale.

### Clock and NTP

After an unplug the kernel clock can reset to 1970 and the RTC to 2001.
`date -s` returns EFAULT and `hwclock -w` returns EINVAL. The boot launch sets
ConnMan timeservers, which fixes it. If the clock is wrong and TLS fails,
check the `runs.log` NTP line and:

```sh
gdbus call --system --dest net.connman --object-path / \
  --method net.connman.Clock.SetProperty Timeservers \
  "<['pool.ntp.org', 'time.google.com']>"
```

## Public fork hygiene

Committed in `s90f/`: source, project file, build script, configs, Lucide
SVGs, boot payloads, deploy tools, this handoff and a sanitized evidence file.

Not committed in `s90f/`: device IP addresses, host callback addresses,
weather coordinates, the personal still, the fireplace video, publisher app
icons, Tizen framework assemblies, screenshots, raw logs, session JSON,
database snapshots, account identifiers or credentials. The ignored
`.local/` tree keeps them for the owner.

If this folder is copied into a private repository, the local-only assets can
be restored from the paths and hashes above. Do not make the public fork
private in place; a fork's visibility cannot be changed.

## Known pitfalls

- Do not run `bash -n` on the launch file; UEP rejects it as an unsigned
  script. The gawk wrapper is the supported path.
- Do not rely on runtime systemd masks. They do not survive restart.
- Do not assume app preload settings persist; the vendor can overwrite them.
- A local `Timer` without a field reference can be collected before it fires.
- Do not put UI work after `Play()`.
- Do not treat a keypress that reveals the page as the fix; fix the z-order
  and the pre-`Play` rebuild.
- Do not clear streaming app data, log users out, remove credentials or
  disable updates as a generic speed fix.
- Do not globally disable `org.tizen.menu`; advanced settings and Bluetooth
  pairing still depend on it.
- Do not reboot or enter standby inside the temporary root session; let its
  cleanup checks finish.
- A failed script may have completed earlier filesystem operations. Inspect
  before retrying. Never overwrite the first backup.
- The public folder deliberately contains no media or proprietary binaries;
  absence in git is not absence on the TV.

## Open items

- Pull `button-glass.svg`, `icon-apps.svg`, `icon-hdmi.svg` and
  `icon-settings.svg` from the live resource directory when the TV is
  reachable, then add them under `launcher/assets/extra/`.
- The boot files here are the live content reconstructed from the TV. They
  were installed incrementally and were not replayed from this folder. Test
  a reinstall on a spare boot only if it becomes necessary.
- No decrypted traffic audit of this TV was performed. Do not claim every
  privacy path is eliminated.
