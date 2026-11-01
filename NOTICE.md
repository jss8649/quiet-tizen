# Attribution and distribution

Quiet Home is a native Tizen .NET/NUI implementation. Its layout measurements,
palette, dock proportions and focus treatment adapt
[Free My TV](https://github.com/simbasjungles/free-my-tv/tree/73409804e5085e720dccea9ab95078a515cae098),
commit `73409804e5085e720dccea9ab95078a515cae098`, copyright 2026 FreeMyTV
contributors, under the MIT license in `licenses/FreeMyTV-MIT.txt`.
The Android APK is not used.

The bundled Quiet Inter fonts are static derivatives of Inter, copyright
2016 The Inter Project Authors, renamed after conversion. Medium: weight 500,
optical size 14; Semibold: weight 600, optical size 14; Display: weight 600,
optical size 32. See `licenses/Inter-OFL.txt`. These font files retain the
SIL Open Font License; the repository's MIT license does not replace it.

The Material Symbols PNGs come through Free My TV and retain Apache 2.0:
`licenses/Material-Symbols-Apache-2.txt`. Console illustrations, gradient
cards and text-only app placeholders were produced for this launcher.

The Settings tile icons are from [Lucide](https://lucide.dev) (`lucide-static`
0.469.0), ISC license, with portions from Feather under MIT. See
`licenses/Lucide-ISC.txt`.

The source subset in `vendor/samsung_tv_root/` and `vendor/payload-source/`
comes from [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root/tree/4ad2c4d3b0d0e0da4b5b7ebe4a787e94596f416b),
commit `4ad2c4d3b0d0e0da4b5b7ebe4a787e94596f416b`, under the
Unlicense in `licenses/samsung-tv-root-Unlicense.txt`. The local runtime
fallback is described in [provenance](docs/provenance.md).

No Samsung SDB executable, firmware, SDK/reference assembly, stock app
binary, account database, private backup or proprietary media is distributed.

The S90F maintenance source in `s90f/launcher/` is a locally decompiled and
patched derivative of Samsung's AICompanionUI, prepared for the owner's exact
TV. It is included as a case-study maintenance record, not as a
redistributable application, and it is not relicensed by this project's MIT
license. The fireplace video, the startup still, the Tizen framework
assemblies, the weather coordinates and the publisher app icons remain
local-only and are not distributed.

Publisher streaming-app artwork is not bundled. `launcher/artwork-sources.json`
records optional sources and transformations; `tools/fetch_artwork.py` downloads
selected artwork into ignored local files. Those assets and associated
trademarks remain subject to their owners' terms and are not relicensed by
this project. Source availability does not imply permission for every reuse.
The repository and its contributors are not affiliated with Samsung, Sony,
Nintendo, Microsoft, Amazon or any streaming service.
