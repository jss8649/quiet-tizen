#!/usr/bin/env python3
"""Profile-specific TV diagnostics and access. See docs/02-access.md."""
import argparse
import asyncio
import base64
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
from samsung_tv_root.archive_root import probe, _capture
from samsung_tv_root.sdb import SdbClient, find_sdb
from device_profiles import DEFAULT_PROFILE_PATH, load_profile, check_profile_identity, require_operation
from diagnostics import collect_diagnostics
from root_inventory import BACKUP_FILES, FRAMEWORK_FILES, ROOT_INVENTORY_COMMANDS

PROFILE = load_profile()
STAGE = "/home/owner/share/tmp/sdk_tools/quiet-tizen"
ARTWORK_BACKUP_FILES = ("apps-before.json", "apps-before.sha256", "launcher-assembly.sha256")
ARTWORK_ASSETS = (
    ("Netflix", "org.tizen.netflix-app", "app-icons/netflix.svg", "artwork-netflix.svg"),
    ("YouTube", "com.samsung.tv.cobalt-yt", "app-icons/youtube.jpg", "artwork-youtube.jpg"),
    ("Prime Video", "org.tizen.primevideo", "app-icons/prime-video.svg", "artwork-prime-video.svg"),
)


def private_path(path):
    path = Path(path).expanduser().resolve()
    private = (ROOT / ".local").resolve()
    if path == private or private not in path.parents:
        raise ValueError("Private files must be inside this checkout's .local/ directory.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def save_private(path, data):
    path = private_path(path)
    path.write_bytes(data)
    path.chmod(0o600)


def observed_model(client):
    client.connect()
    client.require_device()
    rows = [line.split() for line in client.run(("devices",), check=True).stdout.splitlines()]
    rows = [row for row in rows if row and row[0] == client.serial]
    if len(rows) != 1 or len(rows[0]) < 3:
        raise ValueError("Cannot identify the explicitly selected device from SDB.")
    return rows[0][-1]


def check_identity(model, firmware, profile=None):
    check_profile_identity(PROFILE if profile is None else profile, model, firmware)


def pull_command(remote):
    if not remote.startswith("/") or "\0" in remote or "\n" in remote:
        raise ValueError("Use an absolute, single-line TV file path.")
    # The upstream command channel captures at most 1 MiB per stream.
    # A compressed transfer is bounded before emitting any base64.
    return f"""set -eu
test -f {shlex.quote(remote)}
test "$(stat -c %s {shlex.quote(remote)})" -le 33554432
t=$(mktemp /run/quiet-tizen-pull.XXXXXX)
trap 'rm -f "$t"' EXIT HUP INT TERM
gzip -c {shlex.quote(remote)} > "$t"
test "$(wc -c < "$t")" -le 760000 || {{ echo 'File too large; split a snapshot into smaller files first.' >&2; exit 1; }}
sha256sum {shlex.quote(remote)} | cut -d ' ' -f 1
base64 "$t"
"""


def decode_pull(stdout):
    digest, encoded = stdout.split("\n", 1)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Missing transfer digest.")
    compressed = base64.b64decode("".join(encoded.split()), validate=True)
    data = gzip.decompress(compressed)
    if len(data) > 33554432 or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Transfer size or digest mismatch; file was not saved.")
    return data


def normalized_script_bytes(path):
    """Normalize Windows checkout line endings before piping a shell script to the TV."""
    script = Path(path).read_bytes().replace(b"\r\n", b"\n")
    if b"\r" in script or len(script) > 45000:
        raise ValueError("Script has unsupported line endings or exceeds the command limit.")
    return script


def encoded_script(path):
    return base64.b64encode(normalized_script_bytes(path)).decode()


def verify_package_archive(archive_path):
    """Refuse a stale or unexpected preview package before touching the TV."""
    package_dir = ROOT / ".local/package"
    required = ("BixbyPromotion.dll", "Probe.dll", "quiet-home/apps.json",
                "quiet-home/home-layout.json")
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            if (member.name.startswith("/") or ".." in PurePosixPath(member.name).parts
                    or not (member.isfile() or member.isdir())):
                raise ValueError("Preview package contains an unsafe archive entry.")
        for name in required:
            local = package_dir / name
            if not local.is_file():
                raise ValueError(f"Missing built preview file: {name}")
            try:
                member = archive.getmember("./" + name)
            except KeyError as error:
                raise ValueError(f"Preview archive lacks {name}") from error
            stream = archive.extractfile(member)
            if stream is None or hashlib.sha256(stream.read()).digest() != hashlib.sha256(local.read_bytes()).digest():
                raise ValueError(f"Preview archive differs from current build: {name}")


def verify_artwork_inputs():
    """The fixed update may contain only the owner's three chosen app logos."""
    catalog = json.loads((ROOT / "launcher/assets/apps.local.json").read_text(encoding="utf-8"))
    if len(catalog) != 4 or catalog[-1].get("Name") != "Get more apps":
        raise ValueError("Artwork catalog differs from the selected four entries.")
    receipts = json.loads((ROOT / ".local/artwork-receipts.json").read_text(encoding="utf-8"))
    staged = [("artwork-apps.json", ROOT / "launcher/assets/apps.local.json")]
    for app, expected in zip(catalog[:3], ARTWORK_ASSETS):
        name, app_id, asset, staged_name = expected
        if (app.get("Name"), app.get("Id"), app.get("Asset")) != (name, app_id, asset):
            raise ValueError(f"Artwork catalog entry changed: {name}")
        path = ROOT / "launcher/assets" / asset
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipts[name]["asset_sha256"]:
            raise ValueError(f"Artwork hash differs from the local fetch receipt: {name}")
        staged.append((staged_name, path))
    return tuple(staged)


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="The owner's TV IPv4 address; never auto-discovered")
    parser.add_argument("--profile", type=Path, help="Exact model/firmware profile JSON; default is the U8000F case study")
    parser.add_argument("--firmware", help="Operator-verified version from the TV's About screen")
    parser.add_argument("--sdb", help="Path to Samsung's separately installed SDB")
    parser.add_argument("--callback-host", help="This computer's LAN IPv4 if route detection is wrong")
    sub = parser.add_subparsers(dest="action", required=True)
    doctor = sub.add_parser("doctor", help="Collect fixed non-root compatibility observations")
    doctor.add_argument("--report", type=Path, help="Save a diagnostic JSON report below .local/")
    sub.add_parser("root-check", help="Temporarily obtain root and run id; no configuration changes")
    sub.add_parser("inventory", help="Save fixed read-only root inventory under .local/")
    sub.add_parser("framework-pull", help="Copy four fixed TV framework references privately")
    sub.add_parser("source-probe", help="Run the built read-only source and Home probe")
    snapshot = sub.add_parser("snapshot", help="Save fixed SQLite and launcher backups on the TV")
    snapshot.add_argument("name", help="Unique backup phase name")
    backup_pull = sub.add_parser("backup-pull", help="Copy fixed TV backup files into .local/")
    backup_pull.add_argument("name", help="Existing backup phase name")
    preview_install = sub.add_parser("preview-install", help="Install Quiet Home for visible testing without Home routing")
    preview_install.add_argument("name", help="Verified backup phase name")
    preview_launch = sub.add_parser("preview-launch", help="Launch the installed preview again for visible testing")
    preview_launch.add_argument("name", help="Verified backup phase name")
    preview_restore = sub.add_parser("preview-restore", help="Restore the original launcher after preview")
    preview_restore.add_argument("name", help="Verified backup phase name")
    home_route = sub.add_parser("home-route", help="Assign the visibly tested Quiet Home to Home/startup")
    home_route.add_argument("name", help="Verified backup phase name")
    home_restore = sub.add_parser("home-restore", help="Restore original Home/startup selectors")
    home_restore.add_argument("name", help="Verified backup phase name")
    artwork_snapshot = sub.add_parser("artwork-snapshot", help="Back up the current Quiet Home app catalog")
    artwork_snapshot.add_argument("name", help="New artwork backup phase name")
    artwork_pull = sub.add_parser("artwork-backup-pull", help="Copy the current app catalog backup privately")
    artwork_pull.add_argument("name", help="Existing artwork backup phase name")
    artwork_install = sub.add_parser("artwork-install", help="Install three local app logos and catalog")
    artwork_install.add_argument("name", help="Verified artwork backup phase name")
    artwork_restore = sub.add_parser("artwork-restore", help="Restore the placeholder app catalog")
    artwork_restore.add_argument("name", help="Verified artwork backup phase name")
    run = sub.add_parser("exec", help="Execute one reviewed command or short script using temporary root")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--command")
    source.add_argument("--script", type=Path)
    run.add_argument("--arg", action="append", default=[], help="Positional argument passed to --script")
    pull = sub.add_parser("pull", help="Read and verify one bounded file into ignored .local/")
    pull.add_argument("remote")
    pull.add_argument("local", type=Path)
    push = sub.add_parser("push", help="Upload one file to the SDK staging directory, not to system paths")
    push.add_argument("local", type=Path)
    push.add_argument("name", help="Simple staging filename")
    args = parser.parse_args(argv)
    profile = load_profile(args.profile or DEFAULT_PROFILE_PATH)
    # Reject unsupported operations before locating SDB or connecting to the TV.
    require_operation(profile, args.action)
    if args.action != "doctor" or args.profile is not None:
        check_identity(profile["model"], args.firmware, profile)
    if args.action in ("snapshot", "backup-pull", "preview-install", "preview-launch", "preview-restore",
                       "home-route", "home-restore", "artwork-snapshot", "artwork-backup-pull",
                       "artwork-install", "artwork-restore") and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.name):
        raise ValueError("Use a simple backup phase name without directory components.")
    if args.action == "source-probe" and not (ROOT / ".local/build/Probe/Probe.dll").is_file():
        raise ValueError("Build the read-only Probe.dll locally before source-probe.")
    if args.action == "doctor" and args.report:
        private_path(args.report)
    if args.action == "framework-pull":
        destinations = {name: private_path(ROOT / ".local/tv-framework" / name)
                        for name in FRAMEWORK_FILES}
        if any(destination.exists() for destination in destinations.values()):
            raise ValueError("A framework reference already exists; preserve and inspect it before retrying.")
    if args.action == "backup-pull":
        destinations = {name: private_path(ROOT / ".local/backups" / args.name / name)
                        for name in BACKUP_FILES}
        if any(destination.exists() for destination in destinations.values()):
            raise ValueError("A backup file already exists locally; preserve and inspect it before retrying.")
    if args.action == "artwork-backup-pull":
        destinations = [private_path(ROOT / ".local/backups" / args.name / name)
                        for name in ARTWORK_BACKUP_FILES]
        if any(path.exists() for path in destinations):
            raise ValueError("An artwork backup already exists locally; preserve it before retrying.")
    if args.action in ("artwork-install", "artwork-restore"):
        backup_dir = ROOT / ".local/backups" / args.name
        if not all((backup_dir / name).is_file() for name in ARTWORK_BACKUP_FILES):
            raise ValueError("Copy the artwork catalog backup before changing resources.")
        digest = (backup_dir / "apps-before.sha256").read_text().split()[0]
        if hashlib.sha256((backup_dir / "apps-before.json").read_bytes()).hexdigest() != digest:
            raise ValueError("Artwork backup catalog digest mismatch.")
    if args.action == "artwork-install":
        artwork_staged = verify_artwork_inputs()
    if args.action in ("preview-install", "preview-launch", "preview-restore", "home-route", "home-restore"):
        backup_dir = ROOT / ".local/backups" / args.name
        if not all((backup_dir / name).is_file() for name in BACKUP_FILES):
            raise ValueError("Copy and verify the fixed backup files before launcher preview.")
    if args.action == "preview-install":
        archive_path = ROOT / ".local/package-preview.tar.gz"
        if not archive_path.is_file():
            raise ValueError("Build and archive the private launcher package before preview.")
        verify_package_archive(archive_path)
    ipaddress.IPv4Address(args.host)
    if args.callback_host:
        ipaddress.IPv4Address(args.callback_host)
    if args.sdb:
        os.environ["SDB"] = str(Path(args.sdb).expanduser().resolve())
    transport = profile.get("diagnostic_transport", {})
    max_inline_bytes = transport.get("max_inline_bytes", 510)
    client = SdbClient(find_sdb(), args.host, timeout=15,
                       max_appinstall_bytes=max_inline_bytes)
    model = observed_model(client)
    print("SDB model:", model)
    if args.action != "doctor" or args.profile is not None:
        check_identity(model, args.firmware, profile)
    if args.action == "doctor":
        report = collect_diagnostics(client, profile, model, args.firmware, args.callback_host)
        print("Profile status:", profile["support_status"])
        print("Archive prerequisites:", report["archive_prerequisites"])
        for name, result in report["checks"].items():
            print(f"  {name}: {result['status']}" +
                  (f" ({result['reason']})" if "reason" in result else ""))
        if args.report:
            save_private(args.report, (json.dumps(report, indent=2) + "\n").encode())
            print(f"Diagnostic report: {args.report.resolve().relative_to(ROOT)}")
        else:
            print(json.dumps(report, indent=2))
        print("Diagnostic observations only. Root, launcher and cleanup have not been tested by this command.")
        return 0 if report["archive_prerequisites"] == "observed_not_root_proof" else 2
    if args.action == "preview-launch":
        # This fixed app request is permitted to the SDK user. It avoids a root
        # session each time a visible app test returns to the original Home.
        response = client.capture("app_launcher -u 5001 -s com.samsung.tv.bixby-promotion",
                                  callback_host=args.callback_host, timeout=15)
        if "[exit:0]" not in response.output:
            raise RuntimeError("Preview launch request failed; inspect the TV before retrying.")
        print("Quiet Home preview launch requested. Home/startup routing is unchanged.")
        return
    if args.action == "push":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", args.name):
            raise ValueError("Use a simple staging filename without directory components.")
        if not args.local.is_file():
            raise ValueError("Upload source must be a file.")
        _capture(client, f"mkdir -p {STAGE}")
        remote = PurePosixPath(STAGE) / args.name
        client.push(args.local.resolve(), remote)
        digest = hashlib.sha256(args.local.read_bytes()).hexdigest()
        actual = _capture(client, f"sha256sum {shlex.quote(str(remote))}").split()[0]
        if digest != actual:
            raise ValueError("Uploaded file digest mismatch.")
        print(f"Verified staging file: {remote}. Remove it after deployment.")
        return
    if args.action == "root-check":
        commands = ("id",)
    elif args.action == "inventory":
        commands = tuple(command for _, command in ROOT_INVENTORY_COMMANDS)
    elif args.action == "framework-pull":
        commands = ()
    elif args.action == "source-probe":
        commands = ()
    elif args.action == "snapshot":
        encoded = encoded_script(ROOT / "recipes/snapshot.sh")
        commands = (f"printf '%s' {shlex.quote(encoded)} | base64 -d | /bin/sh -s -- {shlex.quote(args.name)}",)
    elif args.action == "artwork-snapshot":
        encoded = encoded_script(ROOT / "recipes/snapshot-artwork.sh")
        commands = (f"printf '%s' {shlex.quote(encoded)} | base64 -d | /bin/sh -s -- {shlex.quote(args.name)}",)
    elif args.action in ("backup-pull", "artwork-backup-pull"):
        commands = ()
    elif args.action in ("preview-install", "preview-restore", "home-route", "home-restore",
                         "artwork-install", "artwork-restore"):
        commands = ()
    elif args.action == "pull":
        private_path(args.local)
        commands = (pull_command(args.remote),)
    elif args.script:
        encoded = encoded_script(args.script)
        commands = (f"printf '%s' {shlex.quote(encoded)} | base64 -d | /bin/sh -s -- "
                    + shlex.join(args.arg),)
    else:
        if args.arg:
            raise ValueError("--arg requires --script.")
        commands = (args.command,)
    result = asyncio.run(probe(
        args.host, model=model, callback_host=args.callback_host,
        payloads=ROOT / ".local/build/payloads", commands=commands, command_timeout=30,
        max_appinstall_bytes=max_inline_bytes,
        read_files=(tuple(FRAMEWORK_FILES.items()) if args.action == "framework-pull"
                    else tuple((local, f"/opt/usr/share/quiet-tizen-backups/{args.name}/{remote}")
                               for local, remote in BACKUP_FILES.items())
                    if args.action == "backup-pull" else
                    tuple((name, f"/opt/usr/share/quiet-tizen-backups/{args.name}/{name}")
                          for name in ARTWORK_BACKUP_FILES)
                    if args.action == "artwork-backup-pull" else ()),
        output_dir=(ROOT / ".local/tv-framework" if args.action == "framework-pull"
                    else ROOT / ".local/backups" / args.name
                    if args.action in ("backup-pull", "artwork-backup-pull")
                    else None),
        staged_files=(("Probe.dll", ROOT / ".local/build/Probe/Probe.dll"),)
                     if args.action == "source-probe" else
                     (("package.tar.gz", ROOT / ".local/package-preview.tar.gz"),
                      ("install-launcher.sh", normalized_script_bytes(ROOT / "recipes/install-launcher.sh")),
                      ("restore-preview.sh", normalized_script_bytes(ROOT / "recipes/restore-preview.sh")))
                     if args.action == "preview-install" else
                     (("restore-preview.sh", normalized_script_bytes(ROOT / "recipes/restore-preview.sh")),)
                     if args.action == "preview-restore" else
                     (("route-home.sh", normalized_script_bytes(ROOT / "recipes/route-home.sh")),
                      ("restore-home-route.sh", normalized_script_bytes(ROOT / "recipes/restore-home-route.sh")))
                     if args.action == "home-route" else
                     (("restore-home-route.sh", normalized_script_bytes(ROOT / "recipes/restore-home-route.sh")),)
                     if args.action == "home-restore" else
                     (*artwork_staged,
                      ("install-artwork.sh", normalized_script_bytes(ROOT / "recipes/install-artwork.sh")),
                      ("restore-artwork.sh", normalized_script_bytes(ROOT / "recipes/restore-artwork.sh")))
                     if args.action == "artwork-install" else
                     (("restore-artwork.sh", normalized_script_bytes(ROOT / "recipes/restore-artwork.sh")),)
                     if args.action == "artwork-restore" else (),
        run_staged=("Probe.dll",) if args.action == "source-probe" else (),
        run_staged_shell=(("install-launcher.sh", args.name) if args.action == "preview-install"
                          else ("restore-preview.sh", args.name) if args.action == "preview-restore"
                          else ("route-home.sh", args.name) if args.action == "home-route"
                          else ("restore-home-route.sh", args.name) if args.action == "home-restore"
                          else ("install-artwork.sh", args.name) if args.action == "artwork-install"
                          else ("restore-artwork.sh", args.name) if args.action == "artwork-restore"
                          else None),
    ))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    log = ROOT / ".local/sessions" / f"{stamp}.json"
    save_private(log, (json.dumps(result, indent=2) + "\n").encode())
    if result.get("uid") != 0 or result.get("euid") != 0:
        raise ValueError("The callback did not prove UID/EUID 0.")
    if not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
        raise ValueError("Root session cleanup checks failed; inspect the private session log.")
    for index, response in enumerate(result.get("commands", [])):
        if response["exit_code"] or response["timed_out"]:
            raise RuntimeError(f"Command {index + 1} failed ({response['exit_code']}, "
                               f"timeout={response['timed_out']}). Private log: {log.relative_to(ROOT)}")
    if args.action == "inventory":
        print(f"Fixed read-only inventory saved privately: {log.relative_to(ROOT)}")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action == "framework-pull":
        if len(result.get("private_files", [])) != len(FRAMEWORK_FILES):
            raise ValueError("Framework transfer evidence is incomplete; inspect the private session log.")
        print("Four checksum-verified framework references saved under .local/tv-framework/.")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action == "backup-pull":
        if len(result.get("private_files", [])) != len(BACKUP_FILES):
            raise ValueError("Backup transfer evidence is incomplete; inspect the private session log.")
        print(f"Checksum-verified backup files saved privately: .local/backups/{args.name}/")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action == "artwork-backup-pull":
        if len(result.get("private_files", [])) != len(ARTWORK_BACKUP_FILES):
            raise ValueError("Artwork backup transfer evidence is incomplete; inspect the private session log.")
        print(f"Checksum-verified artwork backup saved privately: .local/backups/{args.name}/")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action == "snapshot":
        print(f"Fixed TV backup phase saved: {args.name}. Private session: {log.relative_to(ROOT)}")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action == "artwork-snapshot":
        print(f"Fixed artwork catalog snapshot saved on TV: {args.name}. Private session: {log.relative_to(ROOT)}")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action in ("preview-install", "preview-restore", "home-route", "home-restore",
                       "artwork-install", "artwork-restore"):
        print(f"{args.action} completed. Inspect the TV and private session: {log.relative_to(ROOT)}")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    if args.action == "source-probe":
        print(f"Read-only Home/source probe saved privately: {log.relative_to(ROOT)}")
        print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")
        return
    response = result["commands"][0]
    if response["stderr"]:
        print(response["stderr"], file=sys.stderr, end="")
    if args.action == "pull":
        save_private(args.local, decode_pull(response["stdout"]))
        print("Verified file saved inside .local/.")
    else:
        print(response["stdout"], end="")
    print("UID/EUID 0 verified; root staging cleaned; passwd and SDB key hashes unchanged.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        print(f"Stopped: {error}", file=sys.stderr)
        sys.exit(1)
