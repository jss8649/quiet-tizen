# AT-HUB boot payload

The boot hook starts the remote key proxy and activates Home early at every
boot. The TizenTube SMACK lines it used to write were removed on 2026-11-01
when TizenTube was uninstalled. It runs from
`AT-HUB.service` through a gawk shebang wrapper installed over
`/opt/etc/parseinfo.sh`.

## Files

| File | Installed path | Purpose |
|---|---|---|
| `wrapper` | `/opt/etc/parseinfo.sh` | gawk one-liner that pipes `launch` into bash |
| `launch` | `/opt/usr/share/quiet-smack-boot/launch` | runs the original parseinfo, NTP, SMACK rules, proxy and activation |
| `restore.sh` | `/opt/usr/share/quiet-smack-boot/restore.sh` | restores the preserved original and removes the payload |

The live TV also has `/opt/usr/share/quiet-smack-boot/original`, the preserved
Samsung parseinfo. It is not committed. `restore.sh` copies it back with its
original owner, mode and SMACK label.

## Guards

The launch reads `/etc/os-release` and checks the build ID, the AT-HUB unit
hash and the preserved original hash before doing anything. A mismatch writes
a line to `runs.log` and exits. This is intentional: firmware or unit drift
means the profile must be inspected again, not forced.

The gawk wrapper exists because UEP rejects unsigned scripts executed by path
and rejects `bash -n` on the launch file. A signed interpreter reading the
script from stdin is the validated path.

## Install and restore

The live payload was installed incrementally; these files are the resulting
content, not a replayed installer. Do not reinstall unless the payload is
missing or being rebuilt deliberately.

Restore to stock:

```sh
systemctl stop quiet-remote-proxy.service
systemctl stop quiet-home-activate.service
/opt/usr/share/quiet-smack-boot/restore.sh
```

`restore.sh` restores the original parseinfo and removes
`/opt/usr/share/quiet-smack-boot/`. The proxy and activation units are
transient and disappear at reboot. The launcher and its selectors are
separate and are not changed by this restore.

The proxy and activation blocks in `launch` are bounded. The activation loop
stops after ten tries or as soon as the launcher state file exists, so it
cannot keep pulling the TV back to Home.
