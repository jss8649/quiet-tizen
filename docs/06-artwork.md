# App library and crisp artwork

The launcher opens existing installed apps. A catalog entry does not download
an app, create a subscription or install an Android APK.

The example catalog includes Netflix, YouTube, Prime Video, HBO Max, Disney+,
Hulu, Spotify, Apple TV, Tubi, Amazon Luna and Xbox. App IDs vary across regions,
releases and packages. Match IDs against the current TV's metadata, then
test each shortcut.

## Optional SponsorBlock YouTube client

The example YouTube entry opens Samsung's stock YouTube app, which does not
include SponsorBlock. To use SponsorBlock, install the separate
[TizenTube app](https://github.com/reisxd/TizenTube) using its official
instructions, then point the YouTube entry in `apps.local.json` to the app ID
shown in the TV's installed-app inventory. Keep the stock YouTube entry as a
separate shortcut if you want both clients.

Quiet Home only launches the selected app; SponsorBlock segment lookup,
skipping and any timeline markers belong to TizenTube. Configure SponsorBlock
in TizenTube's own settings. Markers can only appear where the selected video
has community-submitted segments and the TV can reach SponsorBlock's service.
Quiet Tizen does not bundle TizenTube or its code.

Copy `launcher/assets/apps.json` to the ignored
`launcher/assets/apps.local.json` to customize it. Entries contain a name,
native app ID, local asset path, fit mode, background and source dimensions.
Optional normalized `Crop` values are `[x,y,width,height]`. Paths must stay
within the resource directory. The “Get more apps” utility tile draws a
centered plus symbol; its regular caption remains below the card.

## Optional publisher artwork

The public repository ships text-only placeholders. Official/publisher
artwork is fetched locally rather than redistributed under our code license:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install Pillow
.venv/bin/python tools/fetch_artwork.py --all
# Or select individual apps:
.venv/bin/python tools/fetch_artwork.py --app 'Prime Video' --app Xbox
python3 tools/build.py launcher --framework .local/tv-framework
```

Review the source manifest before downloading. Downloads are written to
ignored `launcher/assets/app-icons/`, the updated catalog goes to
`apps.local.json`, and source/output hashes go to `.local/artwork-receipts.json`.
The downloader preserves locally edited app IDs. It validates raster
dimensions, reads only the chosen ZIP member, and rejects active/external
SVG content. If a publisher URL expires or changes shape, the affected
entry keeps its previous artwork and the command reports a failure.

Sources are documented per asset in
[artwork-sources.json](../launcher/artwork-sources.json):

- Netflix, Hulu and Spotify: publisher vector artwork.
- Prime Video: Amazon's 2024 vector wordmark, mirrored by Wikimedia Commons.
  The path geometry is retained, with explicit dimensions and a white fill.
- YouTube and Disney+: large publisher/brand artwork.
- HBO Max, Apple TV and Tubi: publisher-provided 1024-pixel App Store artwork.
- Luna: Amazon artwork.
- Xbox: Microsoft's exact green translucent logo from its 2560×1440 wallpaper.
  This is high-resolution raster artwork, **not a claimed public vector**.

The Xbox card uses a normalized viewport to frame the logo. Its decode
dimensions account for that crop, so the renderer does not first shrink the
whole wallpaper to a tiny card and then enlarge the crop. Similar care was
needed to fix the earlier pixelated Prime Video and Xbox cards.

## Avoid the “snap in” effect

Keep app images on the TV, not behind live remote URLs. Quiet Home preloads
and retains the actual grid/dock `ImageView` instances, then reparents them
when changing pages. Preloading bytes alone is insufficient if a new image
view later discards/redecodes the texture.

The cache lasts for the launcher process lifetime. A restart still reloads
resources; this is not a permanent GPU cache. Large catalogs increase
retained memory, so keep only useful entries and use suitable source sizes.
The current-state file reports pending/ready counts to help diagnose missing
or unsupported resources.

After adding artwork, rebuild and redeploy the resources using the same
backup-first approach. Source changes need an assembly rebuild; catalog and
asset changes alone do not. Stop the launcher before replacing resources,
preserve ownership/SMACK labels, and restart it to reload the catalog.
