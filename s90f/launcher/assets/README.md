# Launcher resources

The live launcher reads its resources from
`/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home/`. This folder
contains the small, redistributable configuration and Lucide icons. The
media, publisher artwork and personal configuration stay in `.local/`.

## Committed

| File | Purpose |
|---|---|
| `fireplace.json` | Home/fire volume, fade time and hold time |
| `video-mode.txt` | `underlay` on this TV |
| `extra/lucide-*.svg` | Settings and quick-control icons, ISC license |
| `../apps.json` | Live app catalog: Jellyfin, YouTube, RetroArch, Spotify, Netflix |
| `weather.json.example` | Shape of the weather configuration; replace the coordinates on the TV only |

The fonts are reused from `launcher/assets/fonts/` in the main repository.
The remaining SVGs, placeholder cards and Free My TV symbols are reused from
`launcher/assets/` and remain under their recorded licenses.

## Local-only

| File | Size | SHA-256 | Where |
|---|---|---|---|
| `fireplace.mp4` | 23,626,429 | `fcc7c23c792557262748abe6b3d424a5ef720e6f671460bfa4678ea310567574` | `.local/package-dll/quiet-home/` |
| `home-background.jpg` | 207,895 | `2c22ac800535a298c36bd0ed207b24d1a92194264413e10aa6f8685bdcd6c80a` | `.local/package-dll/quiet-home/` |
| `weather.json` | 87 | not recorded here | live TV resource directory |
| `app-icons/*` | publisher art | not recorded here | `launcher/assets/app-icons/`, `.local/tv-app-icons/` |

The startup still is a frame extracted from `fireplace.mp4`; it is the
splash that covers video initialization. The video and still are kept out of
the public fork because their provenance and redistribution terms are not
recorded.

`weather.json` contains the owner's coordinates. Do not commit it. Use the
example file and set the real location through the deploy helper or directly
on the TV.

## Missing from this copy

These live resource files were not copied because the TV was unreachable at
commit time. Pull them before a fresh reinstall:

- `button-glass.svg`
- `icon-apps.svg`
- `icon-hdmi.svg`
- `icon-settings.svg`

The live launcher already has them, so this does not affect the running TV.
