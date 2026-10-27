# Reversible cleanup

Prefer disabling specific components over deleting system packages. A package
can contain several app IDs; disabling an app record is not the same as
uninstalling its package. The tested workaround changes three registry fields:
`app_disable`, `app_onboot` and `app_autorestart`. Normal package activation
commands did not reliably report or retain the intended state on this build.

Do not remove display, HDMI, audio, network, Bluetooth, app-manager or
accessibility services. Keep `org.tizen.menu` available for advanced settings
and Bluetooth pairing. Also keep the Bixby Promotion container enabled once
it hosts Quiet Home.

## Select a group

The [profile](../profiles/un75u8000ffxza-1300.9.json) splits the observed targets:

| Group | Intended effect | Tradeoff |
|---|---|---|
| `advertising` | Disable identified ACR, viewing-analysis, promotion and advertising app records | Recommendations and advertising features change; not a complete network privacy guarantee |
| `voice` | Remove voice assistants, voice UI, wake-word engines and utterance suggestions | Voice control stops working |
| `context` | Disable AI/context suggestions and content-grab helpers | Related smart features stop working |
| `smart-extras` | Reduce SmartThings, health, gaming-hub and ambience helpers | Some integrations become unavailable |
| `light-shell` | Disable native sidebar and browser | Requires a working Quiet Home/settings bridge first |
| `tv-plus` | Disable Samsung TV Plus startup/app | TV Plus is unavailable until restored; a remote TV Plus button can then hang the TV for about 30 s ([remote buttons](10-remote-buttons.md)) |

The first four groups total 51 app IDs from the original cleanup. The
sidebar/browser add two; the later TV Plus change adds one. This is not a
count of 54 independent trackers. Several are ordinary optional features.

The original owner separately uninstalled ESPN, Sling, Fubo, AMC+, Instagram,
Phynd, Weekend Games, YouTube TV, Peacock and Angel Studios. Those were
personal app choices, not a universal blacklist. Inventory and ask which
subscriptions/apps another owner wants to retain.

## Snapshot, generate, inspect, apply

Start with one group. Use a **new snapshot name for each phase**, so later
restoration does not accidentally erase an earlier desired change.

```sh
tv exec --script recipes/snapshot.sh --arg advertising-01
tv pull /opt/usr/share/quiet-tizen-backups/advertising-01/.pkgmgr_parser.db .local/advertising-01-registry.db
python3 tools/plan_cleanup.py \
  --snapshot .local/advertising-01-registry.db \
  --groups advertising \
  --output .local/plans/advertising-01
```

Inspect `apply.sql`, `restore.sql` and `before.json`. The planner requires one
matching row per selected app and recognized boolean representations.
It refuses missing/duplicate records and generates guards against state drift.
An update to another field/app is preserved. A change to a selected field
causes the plan to stop instead of silently overwriting it.

Save the generated restore script on the TV **before** applying:

```sh
tv push .local/plans/advertising-01/restore.sh advertising-01-restore.sh
tv exec --command 'cp /home/owner/share/tmp/sdk_tools/quiet-tizen/advertising-01-restore.sh /opt/usr/share/quiet-tizen-backups/advertising-01/restore-registry.sh'
tv exec --script .local/plans/advertising-01/apply.sh
```

This updates only the registry flags. It does not terminate existing
processes, set preferences or install service stop conditions.

## Prevent selected services from starting

The vendor units on this build have stop-file conditions. Use the profile's
exact unit/marker pair and inspect it first. For example:

```sh
tv exec --script recipes/stop-marker.sh \
  --arg apply --arg pisa-service.service --arg pisa-service --arg advertising-01
tv exec --script recipes/stop-marker.sh \
  --arg apply --arg canalysis-service.service --arg canalysis-daemon --arg advertising-01
tv exec --command 'systemctl stop adagent-service.service'
```

The script verifies the exact negated `ConditionPathExists`, saves whether
the marker already existed and whether the unit was active, then stops it.
It refuses to overwrite that record. Do the same only for selected voice,
context or smart-extra units listed in the profile.

Four other services were masked **only for the running boot**:

```sh
tv exec --command 'systemctl mask --runtime --now ipa.service contents-recognition-service.service org.tizen.tv.sp-kpi.service data-service.service'
```

These concern predictive app preload, recognition, performance reporting and
logging. Inspect their units and decide if they belong in the owner's setup.
Record existing mask/enabled/active states before using the command. Their
firmware-backed definitions were not writable, so no persistent masking was
attempted. A later restart can bring them back.

## Preferences and the web-app preload cache

The profile records the six preferences changed in the case study. Save
the actual old values from `preferences-before.txt` and prepare the inverse
`vconftool set -f -t TYPE KEY OLD_VALUE` commands first.

For the selected features, apply the corresponding entries, for example:

```sh
tv exec --command 'vconftool set -f -t string db/was/preload_by_country false'
tv exec --command 'vconftool set -f -t bool db/menu/autorun_tv_plus 0'
```

Voice preferences are `db/menu/voice/voice_activated` (bool),
`db/menu/voice/wakeupless_status` (int),
`db/si_service/voice_recog_enable` (bool), and
`db/multi-assistant/prelaunch_mode` (bool), all set to `0` in the voice-free
setup. Do not change them if voice features are retained.

For the cached preload preference, inspect the schema and **only** the relevant
JSON field; the larger record may contain device details:

```sql
SELECT name,json_type(value,'$.rsp.preloadByCountry'),
       json_extract(value,'$.rsp.preloadByCountry')
FROM WASConfigTable
WHERE name='RESERVED_18' AND json_valid(value);
```

On this firmware it was a JSON string `"true"`, not a JSON boolean. After
backing up `.webappservice.db`, a reviewed transaction can use:

```sql
BEGIN IMMEDIATE;
CREATE TEMP TABLE guard(ok INTEGER CHECK(ok=1));
INSERT INTO guard SELECT count(*)=1 FROM WASConfigTable
WHERE name='RESERVED_18' AND json_valid(value)
AND json_type(value,'$.rsp.preloadByCountry')='text'
AND json_extract(value,'$.rsp.preloadByCountry')='true';
UPDATE WASConfigTable
SET value=json_set(value,'$.rsp.preloadByCountry','false')
WHERE name='RESERVED_18';
COMMIT;
```

Run SQL with `sqlite3 -bail`, in a short reviewed script. If the value is
already false, no change is needed. Rollback should restore only this JSON
field, preserving the rest of the record. Do not copy the old WAS database
over the live one.

**Samsung catalog refreshes restored both cached and live preload flags in
later testing.** Recheck them after restart/update. Do not describe this as
a permanent fix or silently add a background enforcement loop.

## Verify the result

Read the affected registry rows, unit `ActiveState`/`ConditionResult`,
preference values and actual processes. Test HDMI, volume, mute, remote,
controller, network and chosen streaming apps. Then perform a full restart
after the root session has ended and check again.

The user confirmed picture, Home and remote operation after an early restart.
No controlled native-settings latency benchmark was obtained. Lightweight
quick settings bypass frequent trips through Samsung's larger settings UI;
they do not make every advanced settings screen instantaneous.
