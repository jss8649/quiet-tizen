#!/usr/bin/env python3
"""Generate reviewed apply/restore SQL from YOUR fresh, consistent registry snapshot."""
import argparse
import json
from pathlib import Path
import re
import shlex
import sqlite3
import os
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("app_disable", "app_onboot", "app_autorestart")
DISABLED = ("true", "false", "false")
DB = "/opt/dbspace/.pkgmgr_parser.db"


def literal(value):
    if value is None:
        return "NULL"
    if value not in ("true", "false"):
        raise ValueError(f"Unexpected registry boolean representation: {value!r}")
    return "'" + value + "'"


def validate_id(app_id):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", app_id):
        raise ValueError("Invalid application ID.")
    return "'" + app_id + "'"


def read_rows(database, ids):
    # Read only. A caller must use SQLite's .backup, never copy a live WAL database.
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("Snapshot integrity check failed.")
        rows = []
        for app_id in ids:
            validate_id(app_id)
            found = conn.execute(
                "SELECT app_disable,app_onboot,app_autorestart FROM package_app_info WHERE app_id=?",
                (app_id,),
            ).fetchall()
            if len(found) != 1:
                raise ValueError(f"{app_id}: expected one row, found {len(found)}. Review this model's inventory.")
            for value in found[0]:
                literal(value)
            rows.append((app_id, tuple(found[0])))
        return rows


def make_sql(rows, restore=False):
    # Guard every observed field before changing anything. SQLite rolls back the
    # transaction if a guard fails and the sqlite3 -bail connection closes.
    lines = ["BEGIN IMMEDIATE;", "CREATE TEMP TABLE quiet_guard(ok INTEGER CHECK(ok=1));"]
    for app_id, original in rows:
        expected = DISABLED if restore else original
        conditions = " AND ".join(f"{key} IS {literal(val)}" for key, val in zip(FIELDS, expected))
        lines.append(f"INSERT INTO quiet_guard SELECT count(*)=1 FROM package_app_info "
                     f"WHERE app_id={validate_id(app_id)} AND {conditions};")
    for app_id, original in rows:
        values = original if restore else DISABLED
        assignments = ",".join(f"{key}={literal(val)}" for key, val in zip(FIELDS, values))
        lines.append(f"UPDATE package_app_info SET {assignments} WHERE app_id={validate_id(app_id)};")
    lines += ["DROP TABLE quiet_guard;", "COMMIT;"]
    return "\n".join(lines) + "\n"


def make_shell(sql):
    return f"""#!/bin/sh
# Generated from the operator's snapshot. Run through tools/tv.py exec --script.
set -eu
test "$(id -u)" = 0
test "$(sqlite3 -readonly {DB} 'PRAGMA quick_check;')" = ok
sqlite3 -bail {DB} <<'QUIET_SQL'
{sql}QUIET_SQL
test "$(sqlite3 -readonly {DB} 'PRAGMA quick_check;')" = ok
echo 'Registry transaction complete. This does not terminate already-running processes.'
"""


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--groups", nargs="+", required=True)
    p.add_argument("--output", type=Path, required=True, help="New directory below .local/")
    p.add_argument("--profile", type=Path, default=ROOT / "profiles/un75u8000ffxza-1300.9.json")
    args = p.parse_args()
    out = args.output.resolve()
    if (ROOT / ".local").resolve() not in out.parents:
        p.error("Plans contain private rollback state; write them below this checkout's .local/.")
    if out.exists():
        p.error("Output directory already exists; preserve previous rollback records.")
    profile = json.loads(args.profile.read_text())
    ids = []
    for group in args.groups:
        if group not in profile["groups"]:
            p.error(f"Unknown group: {group}")
        ids += profile["groups"][group]["app_ids"]
    if len(ids) != len(set(ids)):
        p.error("Groups contain duplicate IDs.")
    rows = read_rows(args.snapshot, ids)
    out.mkdir(parents=True, mode=0o700)
    for action in ("apply", "restore"):
        sql = make_sql(rows, restore=action == "restore")
        (out / f"{action}.sql").write_text(sql, encoding="utf-8", newline="\n")
        (out / f"{action}.sh").write_text(make_shell(sql), encoding="utf-8", newline="\n")
    manifest = {"model": profile["model"], "firmware": profile["firmware"], "groups": args.groups,
                "apps": [{"app_id": app, **dict(zip(FIELDS, vals))} for app, vals in rows]}
    (out / "before.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Generated {len(rows)} targeted changes and inverse operations in {out.relative_to(ROOT)}.")
    print("Review apply.sql and restore.sql. Preserve the snapshot and an on-TV copy of the restore script.")
    print("These plans only edit registry flags; markers, running apps and preferences are separate phases.")


if __name__ == "__main__":
    main()
