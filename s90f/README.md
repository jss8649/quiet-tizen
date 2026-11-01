# Quiet Home on the S90F

This folder is the sanitized source and operating record for the live Quiet
Home setup on one Samsung `QN55S90FAFXZA`, firmware `T-RSMFAKUC-0090-1301.0`.
It covers the launcher build, the AT-HUB boot hook, the remote key rebinds and
the recovery steps. Read [AGENTS.md](AGENTS.md) before changing the TV.

## What is here

| Path | Contents |
|---|---|
| [AGENTS.md](AGENTS.md) | The full agent handoff: state, boot chain, fixes, recovery and pitfalls |
| [launcher/](launcher/) | Decompiled and patched Quiet Home source, portable project and build script |
| [remote/](remote/) | `remote-proxy` input interceptor and `uinput-injector` test tool |
| [boot/](boot/) | AT-HUB launch, gawk wrapper and restore script |
| [tools/](tools/) | Root probe, DLL deploy, install and recovery helpers, launcher verification and boot check |
| [evidence/](evidence/) | Sanitized hashes and verified results |

## Current result

- Quiet Home is `com.samsung.tv.AICompanionUI`, assembly hash
  `d8c93de9...`, and rebuilds byte-identical from `launcher/`.
- Prime opens Spotify, YouTube opens Samsung's own YouTube app, TV Plus opens
  Jellyfin and Netflix stays Netflix. All four were verified after a full unplug.
- The AT-HUB hook starts the remote proxy and forces an early Home resume. Its
  old TizenTube SMACK lines were removed on 2026-11-01 when TizenTube was
  uninstalled.
- The menu appears about 11 to 12 seconds after the Samsung logo on a hard
  boot. Standby wake is immediate.

## Quick start

The build needs the TV's four private Tizen reference assemblies in
`.local/tv-framework/` and the .NET 6 SDK. They are not committed.

```sh
s90f/launcher/build.sh
```

Deployment and recovery commands are in [AGENTS.md](AGENTS.md). The tested
deploy helper expects the tools copied into the ignored
`.local/s90f-candidate/` layout described there.

## What is not in this folder

The fireplace video, the startup still, publisher app icons, the weather
coordinates, Tizen framework assemblies, logs, screenshots, raw session JSON
and database snapshots are local-only or private. Their paths and hashes are
recorded in [AGENTS.md](AGENTS.md) and
[launcher/assets/README.md](launcher/assets/README.md). The public fork keeps
only sanitized source, configuration and documentation.
