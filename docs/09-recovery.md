# Recovery and rollback

Keep the computer's Developer Mode authorization working until the modified
TV has passed full boot, standby/wake, HDMI, sound and remote tests.
Retain the first backups privately. Do not factory-reset first: that can
remove useful recovery state without restoring all modified application files.

The recipes are phased, not one atomic installer. A failed command can leave
earlier changes in place. Inspect what completed before retrying. Never delete
or overwrite the first original backup to make an installer run again.

## Restore cleanup flags

Use the inverse plan generated from this TV's snapshot:

```sh
tv exec --script .local/plans/advertising-01/restore.sh
```

Or use its saved on-TV copy through the shell:

```sh
tv exec --command 'cat /opt/usr/share/quiet-tizen-backups/advertising-01/restore-registry.sh | /bin/sh'
```

Only the selected three registry fields are restored. If a drift guard fails,
inspect the current rows and original `before.json`; reconcile the difference
instead of removing the guard or overwriting the whole database.

For each stop marker changed in that phase, restore it after the registry:

```sh
tv exec --script recipes/stop-marker.sh \
  --arg restore --arg pisa-service.service --arg pisa-service --arg advertising-01
```

The recipe restores marker presence and restarts a unit only if it was active
before. Restore preferences to the saved values and restore only the WAS
JSON field that changed. Unmask a runtime unit only if this procedure added
that mask; preserve pre-existing masks. A full reboot clears runtime masks.

## Restore Samsung settings routing

First restore the `light-shell` registry plan so the sidebar/browser are
available again. Then restore the bridge using its own snapshot:

```sh
tv exec --script recipes/restore-settings-bridge.sh --arg shell-01
```

It restores the two selected routing fields from the saved semantic rows and
the original QuickLaunch assembly/cache. If a vendor update changed the
current routes, the guard stops for inspection.

## Restore Samsung Home

Read the original main-operation app, Home preference and startup preference
from `operation-and-sources-before.txt` and `preferences-before.txt`.
Pass those three **actual recorded IDs**, in that order:

```sh
tv exec --script recipes/restore-launcher.sh \
  --arg home-01 \
  --arg ORIGINAL_MAIN_OPERATION_ID \
  --arg ORIGINAL_HOME_ID \
  --arg ORIGINAL_STARTUP_ID
```

Replace the uppercase placeholders. All three happened to be
`com.samsung.tv.csfs` on the documented TV; do not assume that on another one.
If Quiet Home was installed into another profile's container, append the same
container app ID and entry DLL that `install-launcher.sh` received.

This returns routing to the saved handlers, restores the host package's
original assembly/cache and restores its selected registry flags.
Extra Quiet Home resources are left inert for inspection/recovery; they are
not a running background service. Removing them is optional after successful
restoration.

Allow temporary root cleanup to finish, then restart and test picture,
sound, HDMI, Home, settings and remote. Restore only the optional cleanup
groups the owner wants back; restoring Home does not require turning every
advertising/voice feature on.

## If the UI is blank or a button opens the wrong page

If SDB still works, inspect `/tmp/quiet-home-state.txt`, the installed assembly
hash, resource paths, owner/SMACK labels, `.native_image` cache and the three
Home selectors. An old cached native assembly can run even after replacing
the DLL. Revert the relevant phase rather than changing unrelated firmware
services.

If root no longer works after an update, do not attempt another model's
kernel exploit or flash an unverified image. Re-establish the exact model/
firmware/capability evidence and use an appropriate recovery method for it.
This project does not provide a hardware-level unbrick procedure.
