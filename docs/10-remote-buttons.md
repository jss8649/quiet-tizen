# Remote app buttons: findings from two other models

These are findings from remapping the dedicated streaming buttons on two
Samsung remotes so they select HDMI inputs instead of opening apps. They come
from TVs outside this repository's profile, and no implementation is included.
Treat them as a map of where to look on your own TV, not as a tested recipe.

| Model | Firmware | Remote |
|---|---|---|
| QN77S90FAFXZA | T-RSMFAKUC-0090-1301.0 | Smart Control (four app buttons) |
| QN65S90CAFXZA | T-PTMCAKUC-0090-2220.4 | Smart Control (four app buttons) |

## What the buttons send

Captured from raw evdev on the remote's input device and decoded with
`/usr/share/X11/xkb/tizen_key_layout.txt`:

| Position | S90F key | S90C key | Code |
|---|---|---|---|
| Top | `XF86KeyTVPlus` | `XF86KeyTVPlus` | 560 |
| Rightmost | `XF86Amazon` | `XF86Amazon` | 221 |
| Leftmost | `XF86Netflix` | `XF86Netflix` | 226 |
| Bottom | `XF86KeyYouTube` | `XF86Disney` | 529 / 626 |

Both layouts contain all five names; the Bottom button differs by remote.
Capture the keys on your own TV and check the printed labels instead of
assuming. These are not `XF86App1`-`3`, whose `key_filter` rows belong to
`com.samsung.tv.hotkey-service` and a different remote.

## Who launches the apps

The app launch does not come from `key_filter` or `hotkey-service`.
Disabling `com.samsung.tv.hotkey-service` did not stop the buttons, and the
registry has no streaming-app routes for these keys. The only stock rows are
`org.tizen.function-osd` `pause` rows.

A Netflix process started by the Leftmost button named `tvctx-manager` as its
`__AUL_CALLER_APPID__`, with `callerid=com.samsung.netflix.key`.
`libapp-context-manager.so` contains `cp-key.cc`, `CPKey::HandleKey`,
`cp_app_init_keymap` and a hardcoded association of `XF86Netflix`,
`XF86Amazon` and `XF86KeyYouTube` with Netflix, AmazonInstantVideo and
YouTube. `XF86KeyTVPlus` has a separate handler. Do not disable
`tvctx-manager`; it also manages Home, settings and app transitions.

## Disabling the target app does not disable the button

The button still asks for its app after the app is disabled, and that
launch hangs:

- With the `tv-plus` cleanup group applied, pressing Top froze the remote
  for about 30 seconds, Home included.
- With Netflix and the Cobalt apps disabled, Leftmost and Rightmost showed
  endless loaders.
- With Prime Video disabled, Rightmost fell back to YouTube on the S90F.

The 30-second lockout looked like an HDMI-CEC problem at first, because it
followed an input switch. Most of those lockouts were probably the hung
TV Plus launch. If you apply `tv-plus`, expect this from a remote with a
TV Plus button.

## Routes that did not help

Adding a `key_filter` launch route that copies the native
`XF86DiscretHDMIn` rows does switch inputs, but the vendor launch still
happens alongside it. `override='true'` passed the key on to the vendor
handler as well, so the input and the app fought on each press. Disabling the
function-osd `pause` rows and setting `memory/applite/HDMICEC_consume_keys`
to false changed nothing.

## What worked: an exclusive key grab

`libapp-context-manager-common.so` skips keys that another client holds
exclusively. A resident app that takes an exclusive grab on the four keys
receives them instead, and the original apps do not open.

- The generic path, `ecore_wl2_window_keygrab_set` with mode 4, returned
  false for `XF86Netflix`.
- The TV path works: `Tizen.TV.Application.Window.KeyGrabUtilVd`, backed by
  `/usr/lib/libvd-win-util.so` (`KeyRouter_Util_Initialize`,
  `KeyRouter_Reset_Grab_KeyList`, `KeyRouter_Add_Key_To_KeyList(name, 4)`,
  `KeyRouter_Grab_Set_KeyList(window, 1)`). Stock function-osd uses it with
  NUI's native window handle. It resolves names through the vendor layout.
- The app needs `http://tizen.org/privilege/keygrab`. QuickLaunch declares
  it; the Bixby Promotion container that Quiet Home uses does not. No
  privilege or security policy needs to change if the listener lives in
  QuickLaunch.
- A return value of 1 only means the request was accepted. Confirm delivery
  with a physical press.

The listener requested the grabs, ignored held repeats, called the same
`connect_source()` as the Home HDMI cards and raised `tv-viewer`. Pressing the
button for the input already showing skipped `connect_source()`. On both
TVs the owner confirmed every mapped button, repeat selection, Home, volume
and Settings, with no app launches and no lockout.

This conflicts with the public settings bridge: the listener has to stay
running after `launch_type=preload` requests, because the grab ends with its
process. Samsung's existing `com.samsung.tv.quicklaunch.service` already
preloads QuickLaunch at boot on both models (it is wanted by
`multi-user.target` even though `systemctl is-enabled` reports disabled),
so no startup change was needed.

## Limits

- Until the listener is running after boot, and whenever it dies, the
  buttons open their original apps. There is no watchdog.
- On the S90C, after a full OS restart, the buttons worked once the picture
  appeared. On the S90F, only a remote Power-button cycle was tested, and the
  kernel kept running through it. Standby/wake and firmware updates are
  untested on both.
- Re-running the public settings-bridge install replaces the listener.
- Source IDs (Shield 13, PC 14, console 16 here) belong to those TVs.
  Discover yours.
