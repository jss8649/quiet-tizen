#!/usr/bin/env python3
"""Owner-authorized temporary archive-root candidate probe for one S90F."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import secrets
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import tv as quiet_tv  # noqa: E402

import samsung_tv_root.archive_root as archive_root  # noqa: E402
from samsung_tv_root.sdb import SdbClient, SdbError, find_sdb  # noqa: E402


EXPECTED_MODEL = "QN55S90FAFXZA"
EXPECTED_FIRMWARE = "T-RSMFAKUC-0090-1301.0"
PAYLOADS = REPO / ".local/build/payloads"
PREFLIGHT_PORT = 40028
ROOT_CALLBACK_PORT = 40029


def pin_callback_ports(callback_host: str | None) -> None:
    original_capture = SdbClient.capture

    def fixed_capture(
        self,
        command,
        *,
        callback_host=None,
        bind_host=None,
        port=0,
        timeout=30.0,
        on_listening=None,
    ):
        host = callback_host or fixed_callback_host or None
        bind = bind_host or fixed_callback_host or None
        for attempt in range(4):
            try:
                return original_capture(
                    self,
                    command,
                    callback_host=host,
                    bind_host=bind,
                    port=PREFLIGHT_PORT,
                    timeout=timeout,
                    on_listening=on_listening,
                )
            except SdbError as exc:
                if "Address already in use" not in str(exc) or attempt == 3:
                    raise
                time.sleep(30)

    fixed_callback_host = callback_host
    SdbClient.capture = fixed_capture

    original_archive_capture = archive_root._capture
    fallback_runtime_command = (
        'd=$(readlink -f /usr/share/dotnet.tizen/netcoreapp) && '
        'test -f "$d/libcoreclr.so" && '
        'test -f "$d/System.Private.CoreLib.dll" && '
        'printf "Microsoft.NETCore.App %s [%s]\\n" "${d##*/}" "$d"'
    )
    compact_runtime_command = (
        'd=$(readlink -f /usr/share/dotnet.tizen/netcoreapp); '
        '[ -f "$d/libcoreclr.so" ] && '
        '[ -f "$d/System.Private.CoreLib.dll" ] && '
        'echo "${d##*/}"'
    )

    def compact_runtime_capture(client, command, timeout=15.0):
        if command == fallback_runtime_command:
            versions = original_archive_capture(
                client, compact_runtime_command, timeout
            ).splitlines()
            return "\n".join(
                f"Microsoft.NETCore.App {version} "
                f"[/usr/share/dotnet.tizen/netcoreapp/{version}]"
                for version in versions
            )
        return original_archive_capture(client, command, timeout)

    archive_root._capture = compact_runtime_capture

    original_server = archive_root.RootAgentServer

    class FixedPortRootAgentServer(original_server):
        def __init__(
            self,
            bind_host,
            port,
            expected_peer,
            secret,
            *,
            require_root=True,
        ):
            super().__init__(
                bind_host,
                ROOT_CALLBACK_PORT,
                expected_peer,
                secret,
                require_root=require_root,
            )

    archive_root.RootAgentServer = FixedPortRootAgentServer


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def root_script_command(script_path: Path, arguments: tuple[str, ...]) -> str:
    encoded = base64.b64encode(script_path.read_bytes()).decode("ascii")
    return (
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | /bin/sh -s -- "
        + shlex.join(arguments)
    )


def authenticated_root_command(
    host: str, model: str, callback_host: str | None, command: str,
    log_path: Path, timeout: float = 90,
) -> dict[str, object]:
    result = asyncio.run(archive_root.probe(
        host, model=model, callback_host=callback_host, payloads=PAYLOADS,
        commands=(command,), command_timeout=timeout,
    ))
    quiet_tv.save_private(log_path, (json.dumps(result, indent=2) + "\n").encode())
    if result.get("uid") != 0 or result.get("euid") != 0:
        raise SystemExit(f"UID/EUID 0 was not verified; inspect {log_path}.")
    if not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
        raise SystemExit(f"System hash or root staging cleanup failed; inspect {log_path}.")
    response = result.get("commands", [{}])[0]
    if response.get("exit_code") != 0 or response.get("timed_out"):
        raise SystemExit(f"Root command failed; inspect {log_path}.")
    return result


def install_launcher(
    client: SdbClient, model: str, callback_host: str | None,
    resume_backup: str | None = None,
) -> None:
    package = REPO / ".local/package-s90f.tar.gz"
    local_probe = REPO / ".local/build/Probe/Probe.dll"
    backup_script = REPO / ".local/s90f-candidate/backup-install-target.sh"
    install_script = REPO / ".local/s90f-candidate/install-launcher.sh"
    if not all(path.is_file() for path in (package, local_probe, backup_script, install_script)):
        raise SystemExit("Build the S90F launcher package and Probe.dll first.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = resume_backup or f"quiet-home-s90f-{stamp}"
    if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", backup_name):
        raise SystemExit("Invalid S90F backup name.")
    stage_dir = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-install-{secrets.token_hex(6)}"
    remote_package = PurePosixPath(stage_dir) / "package-s90f.tar.gz"
    remote_probe = PurePosixPath(stage_dir) / "Probe.dll"
    remote_bundle = PurePosixPath(stage_dir) / "recovery-bundle.tar.gz"
    local_backup = REPO / ".local/backups/S90F" / f"{backup_name}-recovery-bundle.tar.gz"
    if local_backup.exists():
        raise SystemExit(f"Refusing to overwrite local recovery backup {local_backup}.")

    parent = client.capture("mkdir -p /home/owner/share/tmp/sdk_tools", timeout=15)
    if "[exit:0]" not in parent.output:
        raise SystemExit("Could not prepare the temporary SDK staging parent.")
    created = client.capture(f"mkdir {shlex.quote(stage_dir)}", timeout=15)
    if "[exit:0]" not in created.output:
        raise SystemExit("Could not exclusively create the deployment staging directory.")

    package_hash = file_sha256(package)
    try:
        client.push(package, remote_package)
        client.push(local_probe, remote_probe)
        if resume_backup:
            backup_dir = f"/opt/usr/share/quiet-tizen-backups/{backup_name}"
            create_command = (
                "set -eu; "
                f"test -s {shlex.quote(backup_dir + '/AICompanionUI-original.tar.gz')}; "
                f"test -s {shlex.quote(backup_dir + '/.pkgmgr_parser.db')}; "
                f"test -s {shlex.quote(backup_dir + '/.app-context.db')}; "
                f"test -s {shlex.quote(backup_dir + '/.webappservice.db')}; "
                f"tar -czf {shlex.quote(str(remote_bundle))} -C /opt/usr/share/quiet-tizen-backups {shlex.quote(backup_name)}; "
                f"chmod 644 {shlex.quote(str(remote_bundle))}; "
                f"stat -c '%s' {shlex.quote(str(remote_bundle))}; "
                f"sha256sum {shlex.quote(str(remote_bundle))}"
            )
            transfer_log = REPO / ".local/sessions" / f"s90f-launcher-transfer-{stamp}.json"
            metadata = authenticated_root_command(
                client.tv_host, model, callback_host, create_command, transfer_log
            )["commands"][0]["stdout"].splitlines()
            try:
                archive_size = int(metadata[-2])
                expected_backup_hash = metadata[-1].split()[0]
            except (IndexError, ValueError):
                raise SystemExit(f"Recovery archive metadata missing; inspect {transfer_log}.")
            chunk_bytes = 240_000
            chunk_commands = tuple(
                f"dd if={shlex.quote(str(remote_bundle))} bs={chunk_bytes} skip={index} count=1 2>/dev/null | base64 -w0"
                for index in range((archive_size + chunk_bytes - 1) // chunk_bytes)
            )
            chunks_log = REPO / ".local/sessions" / f"s90f-launcher-transfer-chunks-{stamp}.json"
            chunks_result = asyncio.run(archive_root.probe(
                client.tv_host, model=model, callback_host=callback_host,
                payloads=PAYLOADS, commands=chunk_commands, command_timeout=90,
            ))
            quiet_tv.save_private(chunks_log, (json.dumps(chunks_result, indent=2) + "\n").encode())
            if (chunks_result.get("uid") != 0 or chunks_result.get("euid") != 0
                    or not chunks_result.get("system_files_unchanged")
                    or not chunks_result.get("staging_cleaned")):
                raise SystemExit(f"Chunk transfer session verification failed; inspect {chunks_log}.")
            responses = chunks_result.get("commands", [])
            if len(responses) != len(chunk_commands) or any(
                item.get("exit_code") != 0 or item.get("timed_out") for item in responses
            ):
                raise SystemExit(f"Recovery chunk command failed; inspect {chunks_log}.")
            quiet_tv.private_path(local_backup)
            with local_backup.open("xb") as destination:
                for item in responses:
                    destination.write(base64.b64decode(item["stdout"], validate=True))
            local_backup.chmod(0o600)
            if local_backup.stat().st_size != archive_size or file_sha256(local_backup) != expected_backup_hash:
                local_backup.unlink(missing_ok=True)
                raise SystemExit(f"Transferred recovery bundle failed size/hash verification: {local_backup}.")
            print("Verified recovery bundle:", local_backup)
            print("Private transfer sessions:", transfer_log, chunks_log)
        else:
            backup_command = root_script_command(
                backup_script, (backup_name, stage_dir, package_hash)
            )
            backup_log = REPO / ".local/sessions" / f"s90f-launcher-backup-{stamp}.json"
            backup_result = authenticated_root_command(
                client.tv_host, model, callback_host, backup_command, backup_log
            )
            backup_output = backup_result["commands"][0]["stdout"]
            match = re.search(r"(?m)^([0-9a-f]{64})\s+", backup_output)
            if not match:
                raise SystemExit(f"Backup digest missing; inspect {backup_log}.")
            expected_backup_hash = match.group(1)

            quiet_tv.private_path(local_backup)
            client.timeout = 180
            client.pull(remote_bundle, local_backup)
            local_backup.chmod(0o600)
            if file_sha256(local_backup) != expected_backup_hash:
                raise SystemExit(f"Downloaded recovery bundle digest mismatch: {local_backup}.")

        install_command = root_script_command(
            install_script,
            (backup_name, stage_dir, package_hash,
             "fe1cb14b2a0d5994662c6856cee7c4ebe87e6d2b276ada0e080f5160f15b4b5c"),
        )
        install_log = REPO / ".local/sessions" / f"s90f-launcher-install-{stamp}.json"
        installed = authenticated_root_command(
            client.tv_host, model, callback_host, install_command, install_log
        )
        print(installed["commands"][0]["stdout"], end="")
        print("Verified recovery bundle:", local_backup)
        print("Private root session:", install_log)
        print("Home and startup selectors were not changed.")
    finally:
        cleanup = client.capture(f"rm -rf {shlex.quote(stage_dir)}", timeout=15)
        if "[exit:0]" not in cleanup.output:
            print(f"Warning: inspect temporary upload staging at {stage_dir}.", file=sys.stderr)


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Explicit TV IPv4 address")
    parser.add_argument(
        "--firmware", required=True,
        help="Firmware manually rechecked on About This TV; must match the candidate",
    )
    parser.add_argument(
        "--callback-host",
        help="Optional host LAN IPv4 if automatic callback-route detection is wrong",
    )
    parser.add_argument(
        "--preflight-only", action="store_true",
        help="Check SDB model and archive-route prerequisites without acquiring root",
    )
    parser.add_argument(
        "--runtime-inventory-only", action="store_true",
        help="Read-only inventory of likely .NET runtime paths; never attempts root",
    )
    parser.add_argument(
        "--device-inventory", action="store_true",
        help="Read-only inventory of app records, routing preferences and framework paths",
    )
    parser.add_argument(
        "--network-diagnostics", action="store_true",
        help="Read-only TV IP, route, DNS, hosts-file and outbound HTTPS diagnostics",
    )
    parser.add_argument(
        "--app-icon-inventory", action="store_true",
        help="Read-only inventory of icon declarations and image candidates for the installed launcher apps",
    )
    parser.add_argument(
        "--pull-app-icons", action="store_true",
        help="Pull the exact installed icons for the five dock apps and built-in TV source into private .local/ storage",
    )
    parser.add_argument(
        "--pull-frameworks", action="store_true",
        help="Pull the four matching Tizen framework references into ignored .local/",
    )
    parser.add_argument(
        "--probe-home-state", action="store_true",
        help="Temporarily run the built read-only Home/source Probe, then remove it",
    )
    parser.add_argument(
        "--install-preflight-only", action="store_true",
        help="Read-only check of the install container and app registry; never installs",
    )
    parser.add_argument(
        "--install-launcher", action="store_true",
        help="Back up the S90F app/registries locally and on TV, install Quiet Home, then launch it; Home routing is unchanged",
    )
    parser.add_argument(
        "--resume-install-launcher", metavar="BACKUP_NAME",
        help="Resume a previously backed-up install by transferring its existing TV recovery snapshot, without taking a new snapshot",
    )
    parser.add_argument(
        "--finish-install-launcher", metavar="BACKUP_NAME:STAGE",
        help="Verify an already copied Quiet Home installation, request launch, and remove its unique leftover upload stage",
    )
    parser.add_argument(
        "--set-home-launcher", metavar="BACKUP_NAME",
        help="After visible launcher approval, route the Home operation and Home preference to Quiet Home while preserving startup routing",
    )
    parser.add_argument(
        "--update-launcher-and-startup", metavar="BACKUP_NAME",
        help="Add the Live TV shortcut, back up the current launcher, update it, and set Quiet Home as the startup app",
    )
    parser.add_argument(
        "--update-launcher-icons", metavar="BACKUP_NAME",
        help="Back up the installed Quiet Home build, update its app/input pages and verified icons, and relaunch it without changing Home/startup routing",
    )
    parser.add_argument(
        "--update-launcher-catalog", metavar="BACKUP_NAME",
        help="Catalog-only update: replace apps.json and add one icon; DLL and Home/startup routing are untouched",
    )
    parser.add_argument(
        "--pull-launcher-files", action="store_true",
        help="Read-only: copy the installed launcher DLL, apps.json and a file listing into .local/installed-s90f/",
    )
    parser.add_argument(
        "--update-launcher-backdrop", metavar="BACKUP_NAME",
        help="Install the video backdrop build: new DLL, apps.json and fireplace.mp4, with rollback; Home/startup routing untouched",
    )
    parser.add_argument(
        "--diagnose-launcher", action="store_true",
        help="Read-only: launcher state file, video file perms/labels, running process, recent video/player log lines",
    )
    parser.add_argument(
        "--fix-tizentube-smack", action="store_true",
        help="Add runtime SMACK rules between TizenTube's package and cobalt so cobalt can reach the proxy. Runtime-only; see --install-smack-persist for boot persistence.",
    )
    parser.add_argument(
        "--install-smack-persist", action="store_true",
        help="Install a persistent boot hook that writes the TizenTube<->cobalt SMACK rules on every boot. Wraps the iot-hub-control hub-init.sh (preserving its behavior).",
    )
    parser.add_argument(
        "--uninstall-smack-persist", action="store_true",
        help="Remove the persistent SMACK boot hook, restoring the original iot-hub-control hub-init.sh.",
    )
    parser.add_argument(
        "--boot-hook-recon", action="store_true",
        help="Read-only audit of boot-time exec surfaces, UEP scope, PATH and service labels.",
    )
    parser.add_argument(
        "--boot-hook-test", action="store_true",
        help="Write temporary UEP-scope probes under /opt/data and the iot-hub app dir, run them, then remove them.",
    )
    parser.add_argument(
        "--run-root-script", nargs="+", metavar="PATH [ARG ...]",
        help="Owner-authorized: pipe a local shell script to /bin/sh as root on the TV (no persistence).",
    )
    parser.add_argument(
        "--update-launcher-dll", metavar="BACKUP_NAME",
        help="Install the DLL in .local/package-dll with its video-mode file; guarded, with rollback",
    )
    parser.add_argument(
        "--set-video-mode", choices=("underlay", "texture", "off"),
        help="Write the backdrop video mode file and relaunch Quiet Home",
    )
    parser.add_argument(
        "--set-weather", nargs=4, metavar=("LAT", "LON", "PLACE", "UNITS"),
        help="Write weather.json for the Quiet Home widget (city level coordinates)",
    )
    parser.add_argument(
        "--keymap-add", nargs=3, metavar=("BACKUP_NAME", "KEY", "APP_ID"),
        help="Back up the key_filter database and add one launch row for KEY (exact-row rollback saved)",
    )
    parser.add_argument(
        "--keymap-remove", nargs=2, metavar=("KEY", "APP_ID"),
        help="Remove exactly the row added by --keymap-add",
    )
    parser.add_argument(
        "--keymap-disable", nargs=2, metavar=("BACKUP_NAME", "KEY"),
        help="Back up the full key_filter database, then delete every row matching KEY (full-db rollback saved)",
    )
    parser.add_argument(
        "--keymap-restore-key", metavar="BACKUP_NAME",
        help="Restore the full key_filter database saved by --keymap-disable",
    )
    parser.add_argument(
        "--launcher-update-inventory", metavar="BACKUP_NAME",
        help="Read-only inspection of a launcher update's TV backup, installed hashes, and routing",
    )
    parser.add_argument(
        "--restore-ai-companion", metavar="BACKUP_NAME",
        help="Restore the original AI Companion app and Home selectors from a named TV/local backup",
    )
    args = parser.parse_args()

    if args.firmware != EXPECTED_FIRMWARE:
        raise SystemExit(f"Stopped: this candidate is only for {EXPECTED_FIRMWARE}.")

    client = SdbClient(find_sdb(), args.host, timeout=15)
    model = quiet_tv.observed_model(client)
    print("SDB model:", model)
    if model != EXPECTED_MODEL:
        raise SystemExit(f"Stopped: expected exact SDB model {EXPECTED_MODEL}.")

    pin_callback_ports(args.callback_host)
    if args.restore_ai_companion:
        if args.preflight_only or args.device_inventory or args.pull_frameworks or args.probe_home_state or args.install_preflight_only or args.install_launcher:
            raise SystemExit("Use --restore-ai-companion by itself.")
        name = args.restore_ai_companion
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        local_backup = REPO / ".local/backups/S90F" / f"{name}-recovery-bundle.tar.gz"
        if not local_backup.is_file():
            raise SystemExit(f"The verified local recovery bundle is missing: {local_backup}")
        restore_script = REPO / ".local/s90f-candidate/restore-ai-companion.sh"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-restore-{stamp}.json"
        restored = authenticated_root_command(
            args.host, model, args.callback_host,
            root_script_command(restore_script, (name,)), log,
        )
        print(restored["commands"][0]["stdout"], end="")
        print("Private root session:", log)
        return

    if args.runtime_inventory_only:
        for command in (
            "ls -la /usr/share/dotnet.tizen",
            "ls -la /usr/share/dotnet.tizen/netcoreapp",
            "ls -la /usr/share/dotnet/shared/Microsoft.NETCore.App/6.0.9",
            "find /usr/share/dotnet -maxdepth 7 \\( -name libcoreclr.so -o -name System.Private.CoreLib.dll \\) -print",
        ):
            result = client.capture(command, timeout=15)
            print(f"$ {command}")
            print(result.output.strip())
        print("Read-only runtime inventory complete; no root attempt was made.")
        return

    if args.install_launcher:
        if args.preflight_only or args.device_inventory or args.pull_frameworks or args.probe_home_state or args.install_preflight_only:
            raise SystemExit("Use --install-launcher by itself.")
        assessment = archive_root._check_target(client)
        print("Archive-route runtime:", assessment.runtime)
        print("Archive-route capabilities:")
        print(assessment.capabilities)
        install_launcher(client, model, args.callback_host)
        return

    if args.resume_install_launcher:
        if args.preflight_only or args.device_inventory or args.pull_frameworks or args.probe_home_state or args.install_preflight_only or args.install_launcher or args.finish_install_launcher:
            raise SystemExit("Use --resume-install-launcher by itself.")
        assessment = archive_root._check_target(client)
        print("Archive-route runtime:", assessment.runtime)
        print("Archive-route capabilities:")
        print(assessment.capabilities)
        install_launcher(client, model, args.callback_host, args.resume_install_launcher)
        return

    if args.finish_install_launcher:
        if args.preflight_only or args.device_inventory or args.pull_frameworks or args.probe_home_state or args.install_preflight_only or args.install_launcher or args.resume_install_launcher or args.set_home_launcher:
            raise SystemExit("Use --finish-install-launcher by itself.")
        try:
            name, stage = args.finish_install_launcher.split(":", 1)
        except ValueError:
            raise SystemExit("Expected BACKUP_NAME:STAGE_TOKEN.")
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name) or not re.fullmatch(r"[A-Za-z0-9]+", stage):
            raise SystemExit("Invalid backup name or stage token.")
        stage_path = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-install-{stage}"
        script = REPO / ".local/s90f-candidate/finish-install-launcher.sh"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-finish-{stamp}.json"
        expected_installed_hash = "5577b460d00f5ec4a0d450bd2e57a494453e7b1ae834bddef3b7a88e19bb5609"
        result = authenticated_root_command(
            args.host, model, args.callback_host,
            root_script_command(script, (name, stage_path, expected_installed_hash)), log,
        )
        print(result["commands"][0]["stdout"], end="")
        print("Private root session:", log)
        return

    if args.set_home_launcher:
        if args.preflight_only or args.device_inventory or args.pull_frameworks or args.probe_home_state or args.install_preflight_only or args.install_launcher or args.resume_install_launcher or args.finish_install_launcher or args.update_launcher_and_startup:
            raise SystemExit("Use --set-home-launcher by itself.")
        name = args.set_home_launcher
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        script = REPO / ".local/s90f-candidate/set-home-launcher.sh"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-home-route-{stamp}.json"
        result = authenticated_root_command(
            args.host, model, args.callback_host,
            root_script_command(script, (name,)), log,
        )
        print(result["commands"][0]["stdout"], end="")
        print("Private root session:", log)
        return

    if args.update_launcher_and_startup:
        if args.preflight_only or args.runtime_inventory_only or args.device_inventory or args.app_icon_inventory or args.pull_app_icons or args.pull_frameworks or args.probe_home_state or args.install_preflight_only or args.install_launcher or args.resume_install_launcher or args.finish_install_launcher or args.set_home_launcher or args.update_launcher_icons:
            raise SystemExit("Use --update-launcher-and-startup by itself.")
        name = args.update_launcher_and_startup
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        package = REPO / ".local/package-s90f.tar.gz"
        script = REPO / ".local/s90f-candidate/update-and-startup.sh"
        if not package.is_file() or not script.is_file():
            raise SystemExit("The updated S90F package or deployment script is missing.")
        package_hash = file_sha256(package)
        assembly_hash = file_sha256(REPO / ".local/build/S90F/AICompanionUI.dll")
        stage_dir = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-update-{secrets.token_hex(6)}"
        parent = client.capture("mkdir -p /home/owner/share/tmp/sdk_tools", timeout=15)
        if "[exit:0]" not in parent.output:
            raise SystemExit("Could not prepare the temporary SDK staging parent.")
        created = client.capture(f"mkdir {shlex.quote(stage_dir)}", timeout=15)
        if "[exit:0]" not in created.output:
            raise SystemExit("Could not exclusively create the update staging directory.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-update-startup-{stamp}.json"
        try:
            client.push(package, PurePosixPath(stage_dir) / "package-s90f.tar.gz")
            command = root_script_command(
                script, (name, stage_dir, package_hash, "5577b460d00f5ec4a0d450bd2e57a494453e7b1ae834bddef3b7a88e19bb5609", assembly_hash),
            )
            result = authenticated_root_command(
                args.host, model, args.callback_host, command, log
            )
            print(result["commands"][0]["stdout"], end="")
            print("Private root session:", log)
        finally:
            cleanup = client.capture(f"rm -rf {shlex.quote(stage_dir)}", timeout=15)
            if "[exit:0]" not in cleanup.output:
                print(f"Temporary update stage cleanup should be checked at {stage_dir}.", file=sys.stderr)
        return

    if args.pull_launcher_files:
        base = "/opt/usr/apps/com.samsung.tv.AICompanionUI"
        paths = (f"{base}/bin/AICompanionUI.dll", f"{base}/res/quiet-home/apps.json", "/opt/usr/apps/com.samsung.tv.hotkey-service/bin/com.samsung.tv.hotkey_service.dll")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-pull-launcher-{stamp}.json"
        cmds = tuple(quiet_tv.pull_command(x) for x in paths) + (
            f"ls -lRn {base}/bin {base}/res | head -150; cat {base}/bin/*.json 2>/dev/null | head -40",)
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=cmds, command_timeout=90))
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit("Root or cleanup check failed; nothing saved.")
        out = REPO / ".local/installed-s90f"
        for response, remote in zip(result["commands"], paths):
            if response.get("exit_code") != 0:
                raise SystemExit(f"Pull failed for {remote}")
            data = quiet_tv.decode_pull(response["stdout"])
            quiet_tv.save_private(out / Path(remote).name, data)
            print("saved", Path(remote).name, len(data))
        quiet_tv.save_private(out / "listing.txt", result["commands"][-1]["stdout"].encode())
        print("saved listing.txt")
        return

    if args.update_launcher_backdrop:
        name = args.update_launcher_backdrop
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        package = REPO / ".local/package-backdrop.tar.gz"
        assembly = REPO / ".local/package-backdrop/AICompanionUI.dll"
        script = REPO / ".local/s90f-candidate/update-backdrop.sh"
        if not all(x.is_file() for x in (package, assembly, script)):
            raise SystemExit("Backdrop package, assembly or script is missing.")
        package_hash = file_sha256(package)
        assembly_hash = file_sha256(assembly)
        stage_dir = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-icons-{secrets.token_hex(6)}"
        parent = client.capture("mkdir -p /home/owner/share/tmp/sdk_tools", timeout=15)
        if "[exit:0]" not in parent.output:
            raise SystemExit("Could not prepare the temporary SDK staging parent.")
        created = client.capture(f"mkdir {shlex.quote(stage_dir)}", timeout=15)
        if "[exit:0]" not in created.output:
            raise SystemExit("Could not exclusively create the staging directory.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-backdrop-{stamp}.json"
        try:
            client.push(package, PurePosixPath(stage_dir) / "package-backdrop.tar.gz")
            result = authenticated_root_command(
                args.host, model, args.callback_host,
                root_script_command(script, (name, stage_dir, package_hash,
                    "0eae5772884883c0d19d78bfe27a3668994f122c838d8f86c37f79d68563011a", assembly_hash)),
                log, timeout=180,
            )
            print(result["commands"][0]["stdout"], end="")
            print("Private root session:", log)
        finally:
            cleanup = client.capture(f"rm -rf {shlex.quote(stage_dir)}", timeout=15)
            if "[exit:0]" not in cleanup.output:
                print(f"Check staging cleanup at {stage_dir}.", file=sys.stderr)
        return

    if args.fix_tizentube_smack:
        COBALT = "User::Pkg::com.samsung.tv.cobalt"
        TT = "User::Pkg::xvvl3S1TT1"
        cmds = (
            "SM=/sys/fs/smackfs/load2; test -f $SM || SM=/smack/load2; "
            f"printf '%s %s rwxat' '{COBALT}' '{TT}' > $SM 2>&1 && echo 'cobalt->xvvl3S1TT1 ok' || echo 'rule1 fail'; "
            f"printf '%s %s rwxat' '{TT}' '{COBALT}' > $SM 2>&1 && echo 'xvvl3S1TT1->cobalt ok' || echo 'rule2 fail'; "
            f"grep -E '{TT} {COBALT} |{COBALT} {TT} ' $SM 2>&1 | grep -v '::RO'",
        )
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=cmds, command_timeout=30))
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit("Root or cleanup check failed.")
        for c in result["commands"]:
            print(c["stdout"], end="")
        return

    if args.boot_hook_recon or args.boot_hook_test:
        HUBDIR = "/opt/usr/apps/com.samsung.tv.iot-hub-control/bin"
        recon = (
            "id; uname -a; cat /proc/self/attr/current 2>/dev/null; echo; "
            "grep -m1 -i 'CPU architecture' /proc/cpuinfo",
            "ls -l /bin/sh /bin/bash /usr/bin/bash 2>&1; "
            "readlink -f /bin/sh 2>&1; readlink -f /bin/bash 2>&1; "
            "head -c 16 /bin/bash | od -An -tx1",
            "cat /usr/lib/systemd/system/iot-hub-control-setup-factory.service 2>&1",
            "systemctl show iot-hub-control-setup-factory.service "
            "-p Environment -p EnvironmentFiles -p ExecStart -p KillMode "
            "-p CapabilityBoundingSet -p NoNewPrivileges -p SmackProcessLabel "
            "-p Type -p RemainAfterExit 2>&1; echo ---; "
            "systemctl --version | head -2; systemctl show-environment 2>&1 | head -40",
            "tr '\\0' '\\n' < /proc/1/environ | grep -E '^(PATH|LD_|SMACK)'; echo ---; "
            "grep -i smack /proc/self/mountinfo; echo ---; "
            "grep -i smack /etc/fstab 2>&1",
            "which getfattr setfattr 2>&1; "
            "getfattr -d -m - /usr/bin/iot-hub/hub-init.sh "
            "/usr/bin/iot-hub/matter-ip-forward.sh "
            f"{HUBDIR}/hub-init.sh {HUBDIR}/hub-init.sh.orig 2>&1; echo ---; "
            f"ls -la {HUBDIR}",
            "grep -a -o '.\\{0,40\\}uep.\\{0,40\\}' /bin/bash 2>/dev/null | head -20; echo ---; "
            "find /usr/lib /usr/bin /lib /usr/libexec -maxdepth 2 -iname '*uep*' "
            "2>/dev/null | head -30; echo ---; ls -la /usr/lib/uep* /usr/bin/*uep* "
            "/lib/uep* 2>&1 | head -20",
            "cat /etc/ld.so.preload 2>&1; ls -la /usr/lib/libkUEPUser.so 2>&1; "
            "readelf -d /bin/bash 2>/dev/null | grep NEEDED; "
            "ldd /bin/bash 2>&1 | grep -i uep; echo ---; "
            "grep -l libkUEPUser /proc/*/maps 2>/dev/null | head -30; echo ---; "
            "strings /usr/lib/libkUEPUser.so | grep -i -E "
            "'uep|sign|exec|xattr|smack|hash|deny|allow' | head -60",
            f"cmp -s /usr/bin/iot-hub/hub-init.sh {HUBDIR}/hub-init.sh.orig && "
            "echo orig_identical_to_vendor || echo orig_differs; "
            f"tail -c 30 {HUBDIR}/hub-init.sh.orig | od -c | tail -3; "
            f"tail -c 10 {HUBDIR}/hub-init.sh | od -c",
            "ls -ld /usr/local /usr/local/bin /usr/local/sbin 2>&1; "
            "ls -la /usr/local/bin 2>&1 | head; "
            "touch /usr/local/bin/.quiet-wtest 2>&1 && echo localbin_WRITABLE && "
            "rm -f /usr/local/bin/.quiet-wtest || echo localbin_ro; "
            "touch /opt/data/.quiet-wtest 2>&1 && echo optdata_WRITABLE && "
            "rm -f /opt/data/.quiet-wtest || echo optdata_ro; "
            "touch /opt/var/local/.quiet-wtest 2>&1 && echo optvarlocal_WRITABLE && "
            "rm -f /opt/var/local/.quiet-wtest || echo optvarlocal_ro",
            "grep -Rh '^ExecStart' /usr/lib/systemd/system 2>/dev/null | "
            "sed 's/^ExecStart=//' | sort -u | head -250",
            "grep -Rs 'smackload\\|smackfs\\|load2' /usr/lib/systemd/system "
            "/etc/systemd /opt/var/local /opt/usr/share 2>/dev/null | head -40; echo ---; "
            "ls -la /usr/bin/smackload /usr/bin/security-manager-rules-loader 2>&1",
            "systemctl list-units --type=service --state=running --no-pager 2>&1 | "
            "head -70; echo ---; for p in $(pidof node 2>/dev/null); do "
            "printf '%s ' $p; cat /proc/$p/attr/current 2>/dev/null; "
            "tr '\\0' ' ' < /proc/$p/cmdline | cut -c1-160; echo; done",
            "ls -la /opt/data 2>&1 | head -20; echo ---; "
            "ls -la /opt/var/local 2>&1 | head -30; echo ---; "
            "mount | grep -E ' /opt|vdfs|smack'",
            "ls -la /etc/cron* /var/spool/cron 2>&1 | head -30; echo ---; "
            "ls -la /etc/rc.local /etc/init.d 2>&1 | head -20",
        )
        tests = (
            "rm -f /opt/data/quiet-uep-test.sh; "
            "printf '#!/bin/sh\\necho UEP_SCRIPT_RAN\\n' > /opt/data/quiet-uep-test.sh; "
            "chmod 755 /opt/data/quiet-uep-test.sh; "
            "/bin/sh -c '/opt/data/quiet-uep-test.sh; echo script_exec_rc=$?'; "
            "/bin/sh -c '/bin/sh /opt/data/quiet-uep-test.sh; echo interp_rc=$?'; "
            "/bin/sh -c '. /opt/data/quiet-uep-test.sh; echo source_rc=$?'",
            "cp /usr/bin/id /opt/data/quiet-uep-elf 2>/dev/null || "
            "cp /bin/busybox /opt/data/quiet-uep-elf; "
            "chmod 755 /opt/data/quiet-uep-elf; "
            "/bin/sh -c '/opt/data/quiet-uep-elf; echo optdata_elf_rc=$?'",
            f"cp /usr/bin/id {HUBDIR}/quiet-uep-elf 2>&1; "
            f"chmod 755 {HUBDIR}/quiet-uep-elf; "
            f"/bin/sh -c '{HUBDIR}/quiet-uep-elf; echo pkgdir_elf_rc=$?'; "
            f"ln -sfn /opt/data/quiet-uep-elf {HUBDIR}/quiet-uep-link; "
            f"/bin/sh -c '{HUBDIR}/quiet-uep-link; echo symlink_elf_rc=$?'",
            f"rm -f /opt/data/quiet-uep-test.sh /opt/data/quiet-uep-elf "
            f"{HUBDIR}/quiet-uep-elf {HUBDIR}/quiet-uep-link; "
            f"ls -la {HUBDIR}; echo CLEANED",
        )
        commands = recon + (tests if args.boot_hook_test else ())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-boot-hook-recon-{stamp}.json"
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=commands, command_timeout=60))
        quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit(f"Root or cleanup check failed; inspect {log}")
        print("root smack label:", result.get("smack"))
        print("cap_eff:", result.get("cap_eff"))
        for c in result["commands"]:
            print("----", c["command"][:70])
            print(c["stdout"][-6000:])
            if c["stderr"]:
                print("STDERR:", c["stderr"][-800:])
        print("session log:", log)
        return

    if args.run_root_script:
        script_path = Path(args.run_root_script[0]).resolve()
        if not script_path.is_file():
            raise SystemExit(f"No such local script: {script_path}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-root-script-{stamp}.json"
        result = authenticated_root_command(
            args.host, model, args.callback_host,
            root_script_command(script_path, tuple(args.run_root_script[1:])), log,
            timeout=180)
        response = result["commands"][0]
        print(response["stdout"], end="")
        if response["stderr"]:
            print("STDERR:", response["stderr"], file=sys.stderr)
        print("session log:", log)
        return

    if args.install_smack_persist:
        import base64
        HUB = "/opt/usr/apps/com.samsung.tv.iot-hub-control/bin/hub-init.sh"
        ORIG = HUB + ".orig"
        TMP = "/tmp/quiet-hub-init-wrapper.sh"
        LABEL = "User::Pkg::com.samsung.tv.iot-hub-control::RO"
        COBALT = "User::Pkg::com.samsung.tv.cobalt"
        TT = "User::Pkg::xvvl3S1TT1"
        wrapper = (
            "#!/bin/sh\n"
            "# QUIET-HOME-SMACK-PERSIST: writes TizenTube<->cobalt SMACK rules at boot.\n"
            "# Chain to original hub-init on success, falling back cleanly if anything is missing.\n"
            "SM=/sys/fs/smackfs/load2\n"
            "[ -f \"$SM\" ] || SM=/smack/load2\n"
            f"printf '%s' '{COBALT} {TT} rwxat' > \"$SM\" 2>/dev/null\n"
            f"printf '%s' '{TT} {COBALT} rwxat' > \"$SM\" 2>/dev/null\n"
            f"if [ -x {ORIG} ]; then exec {ORIG} \"$@\"\n"
            "elif [ -x /usr/bin/iot-hub/hub-init.sh ]; then exec /usr/bin/iot-hub/hub-init.sh \"$@\"\n"
            "fi\n"
            "exit 0\n"
        )
        wrapper_b64 = base64.b64encode(wrapper.encode()).decode()
        cmds = (
            # 1. Preflight: fallback script must exist (safety net), and the hub-init.sh must be present
            "test -x /usr/bin/iot-hub/hub-init.sh && echo 'fallback_ok' || echo 'fallback_MISSING'; "
            f"test -f {HUB} && echo 'target_present' || echo 'target_MISSING'",
            # 2. Back up original to .orig via stdout redirect (vdfs-safe) if backup doesn't yet exist.
            #    If already installed, don't overwrite the backup.
            f"if [ -s {ORIG} ]; then echo 'orig backup already present, keeping'; "
            f"else cat {HUB} > {ORIG} && echo 'backed up {HUB} -> {ORIG}' || echo 'backup FAILED'; fi; "
            f"chmod 755 {ORIG} 2>&1; chown 201:0 {ORIG} 2>&1; chsmack -a '{LABEL}' {ORIG} 2>&1; "
            f"ls -la {ORIG} 2>&1 | awk '{{print $1,$3,$5}}'",
            # 3. Install wrapper via stdout redirect (same pattern we verified works on vdfs for config.xml)
            f"echo '{wrapper_b64}' | base64 -d > {TMP} && test -s {TMP} && echo 'tmp_ok' || echo 'tmp_FAIL'; "
            f"cat {TMP} > {HUB} && echo 'wrapper_installed'; "
            f"chmod 755 {HUB}; chown 201:0 {HUB}; chsmack -a '{LABEL}' {HUB}; "
            f"rm -f {TMP}",
            # 4. Verify file contents (first line + grep for marker) and apply SMACK rules now
            f"head -2 {HUB} 2>&1; "
            f"grep -c 'QUIET-HOME-SMACK-PERSIST' {HUB} 2>&1; "
            "SM=/sys/fs/smackfs/load2; [ -f \"$SM\" ] || SM=/smack/load2; "
            f"printf '%s' '{COBALT} {TT} rwxat' > \"$SM\"; "
            f"printf '%s' '{TT} {COBALT} rwxat' > \"$SM\"; "
            f"grep -E '{TT} {COBALT} |{COBALT} {TT} ' $SM 2>&1 | grep -v '::RO'",
        )
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=cmds, command_timeout=60))
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit("Root or cleanup check failed.")
        for c in result["commands"]:
            print("----", c["command"][:70])
            print(c["stdout"][-2000:])
            print(c["stderr"][-400:])
        return

    if args.uninstall_smack_persist:
        HUB = "/opt/usr/apps/com.samsung.tv.iot-hub-control/bin/hub-init.sh"
        ORIG = HUB + ".orig"
        LABEL = "User::Pkg::com.samsung.tv.iot-hub-control::RO"
        cmds = (
            f"test -e {ORIG} || {{ echo 'no backup, nothing to restore'; exit 1; }}",
            f"cat {ORIG} > {HUB} && echo 'restored original'; "
            f"chmod 755 {HUB}; chown 201:0 {HUB}; chsmack -a '{LABEL}' {HUB}; "
            f"rm -f {ORIG} && echo 'removed backup'; "
            f"head -3 {HUB}",
        )
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=cmds, command_timeout=30))
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit("Root or cleanup check failed.")
        for c in result["commands"]:
            print(c["stdout"], end="")
        return

    if args.diagnose_launcher:
        R = "/opt/usr/apps/com.samsung.tv.AICompanionUI/res/quiet-home"
        DB = "/opt/dbspace/.pkgmgr_parser.db"
        JOURNAL = "/opt/dbspace/.pkgmgr_parser.db-journal"
        APP_ID = "xvvl3S1TT1.TizenTubeStandalone"
        MD_KEY = "http://samsung.com/tv/metadata/native.userdata"
        CFG = "/opt/usr/apps/xvvl3S1TT1/res/wgt/config.xml"
        cmds = (
            # Full content of the signed fallback hub-init.sh
            "cat /usr/bin/iot-hub/hub-init.sh 2>&1",
            "echo '==='; "
            "cat /usr/bin/iot-hub/matter-ip-forward.sh 2>&1",
        )
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=cmds, command_timeout=60))
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit("Root or cleanup check failed.")
        for c in result["commands"]:
            print("----", c["command"][:70]); print(c["stdout"][-4000:]); print(c["stderr"][-400:])
        return

    if args.keymap_add or args.keymap_remove or args.keymap_disable or args.keymap_restore_key:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-keymap-{stamp}.json"
        pull_backup_name = None
        if args.keymap_add:
            name, key, appid = args.keymap_add
            if not re.fullmatch(r"quiet-home-s90f-keymap-[A-Za-z0-9_-]+", name):
                raise SystemExit("Invalid backup name.")
            pull_backup_name = name
            cmds = (
                root_script_command(REPO / ".local/s90f-candidate/keymap-add.sh", (name, key, appid)),
                quiet_tv.pull_command(f"/opt/usr/share/quiet-tizen-backups/{name}/app-context.db"),
            )
        elif args.keymap_remove:
            key, appid = args.keymap_remove
            cmds = (root_script_command(REPO / ".local/s90f-candidate/keymap-remove.sh", (key, appid)),)
        elif args.keymap_disable:
            name, key = args.keymap_disable
            if not re.fullmatch(r"quiet-home-s90f-keymap-[A-Za-z0-9_-]+", name):
                raise SystemExit("Invalid backup name.")
            pull_backup_name = name
            cmds = (
                root_script_command(REPO / ".local/s90f-candidate/keymap-disable.sh", (name, key)),
                quiet_tv.pull_command(f"/opt/usr/share/quiet-tizen-backups/{name}/app-context.db"),
            )
        else:
            name = args.keymap_restore_key
            if not re.fullmatch(r"quiet-home-s90f-keymap-[A-Za-z0-9_-]+", name):
                raise SystemExit("Invalid backup name.")
            cmds = (root_script_command(REPO / ".local/s90f-candidate/keymap-restore-key.sh", (name,)),)
        result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host, payloads=PAYLOADS,
            commands=cmds, command_timeout=90))
        quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())
        if result.get("uid") != 0 or not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
            raise SystemExit(f"Root or cleanup check failed; inspect {log}")
        first = result["commands"][0]
        print(first["stdout"], first["stderr"][-300:], sep="")
        if first.get("exit_code") != 0:
            raise SystemExit(f"Key map step failed (exit {first.get('exit_code')}); see {log}")
        if pull_backup_name and len(result["commands"]) > 1 and result["commands"][1].get("exit_code") == 0:
            data = quiet_tv.decode_pull(result["commands"][1]["stdout"])
            quiet_tv.save_private(REPO / f".local/backups/S90F/{pull_backup_name}-app-context.db", data)
            print("local recovery copy saved,", len(data), "bytes")
        return

    if args.set_weather:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-weather-{stamp}.json"
        result = authenticated_root_command(
            args.host, model, args.callback_host,
            root_script_command(REPO / ".local/s90f-candidate/set-weather.sh", tuple(args.set_weather)), log)
        print(result["commands"][0]["stdout"], end="")
        return
    if args.set_video_mode:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-video-mode-{stamp}.json"
        result = authenticated_root_command(
            args.host, model, args.callback_host,
            root_script_command(REPO / ".local/s90f-candidate/set-video-mode.sh", (args.set_video_mode,)), log)
        print(result["commands"][0]["stdout"], end="")
        return
    if args.update_launcher_dll:
        name = args.update_launcher_dll
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        package = REPO / ".local/package-dll.tar.gz"
        assembly = REPO / ".local/package-dll/AICompanionUI.dll"
        script = REPO / ".local/s90f-candidate/update-dll.sh"
        package_hash = file_sha256(package)
        assembly_hash = file_sha256(assembly)
        stage_dir = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-icons-{secrets.token_hex(6)}"
        for cmd in ("mkdir -p /home/owner/share/tmp/sdk_tools", f"mkdir {shlex.quote(stage_dir)}"):
            if "[exit:0]" not in client.capture(cmd, timeout=15).output:
                raise SystemExit("Could not prepare staging.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-dll-{stamp}.json"
        try:
            client.push(package, PurePosixPath(stage_dir) / "package-dll.tar.gz")
            result = authenticated_root_command(
                args.host, model, args.callback_host,
                root_script_command(script, (name, stage_dir, package_hash,
                    "d8c93de9021fb2843c40a25b6f29718711fe34b7eb5834acf31998e6ed97e6ac", assembly_hash)),
                log, timeout=120)
            print(result["commands"][0]["stdout"], end="")
        finally:
            if "[exit:0]" not in client.capture(f"rm -rf {shlex.quote(stage_dir)}", timeout=15).output:
                print(f"Check staging cleanup at {stage_dir}.", file=sys.stderr)
        return

    if args.update_launcher_catalog:
        name = args.update_launcher_catalog
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        package = REPO / ".local/package-s90f.tar.gz"
        script = REPO / ".local/s90f-candidate/update-catalog.sh"
        package_hash = file_sha256(package)
        stage_dir = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-icons-{secrets.token_hex(6)}"
        parent = client.capture("mkdir -p /home/owner/share/tmp/sdk_tools", timeout=15)
        if "[exit:0]" not in parent.output:
            raise SystemExit("Could not prepare the temporary SDK staging parent.")
        created = client.capture(f"mkdir {shlex.quote(stage_dir)}", timeout=15)
        if "[exit:0]" not in created.output:
            raise SystemExit("Could not exclusively create the staging directory.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-catalog-update-{stamp}.json"
        try:
            client.push(package, PurePosixPath(stage_dir) / "package-s90f.tar.gz")
            result = authenticated_root_command(
                args.host, model, args.callback_host,
                root_script_command(script, (name, stage_dir, package_hash)), log, timeout=180,
            )
            print(result["commands"][0]["stdout"], end="")
            print("Private root session:", log)
        finally:
            cleanup = client.capture(f"rm -rf {shlex.quote(stage_dir)}", timeout=15)
            if "[exit:0]" not in cleanup.output:
                print(f"Check staging cleanup at {stage_dir}.", file=sys.stderr)
        return

    if args.update_launcher_icons:
        if (args.preflight_only or args.runtime_inventory_only or args.device_inventory
                or args.app_icon_inventory or args.pull_frameworks or args.pull_app_icons
                or args.probe_home_state or args.install_preflight_only
                or args.install_launcher or args.resume_install_launcher
                or args.finish_install_launcher or args.set_home_launcher
                or args.update_launcher_and_startup or args.restore_ai_companion
                or args.launcher_update_inventory):
            raise SystemExit("Use --update-launcher-icons by itself.")
        name = args.update_launcher_icons
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        package = REPO / ".local/package-s90f.tar.gz"
        assembly = REPO / ".local/build/S90F/AICompanionUI.dll"
        script = REPO / ".local/s90f-candidate/update-launcher-icons.sh"
        if not all(path.is_file() for path in (package, assembly, script)):
            raise SystemExit("The built S90F package, assembly, or update script is missing.")
        package_hash = file_sha256(package)
        assembly_hash = file_sha256(assembly)
        stage_dir = f"/home/owner/share/tmp/sdk_tools/quiet-tizen-icons-{secrets.token_hex(6)}"
        parent = client.capture("mkdir -p /home/owner/share/tmp/sdk_tools", timeout=15)
        if "[exit:0]" not in parent.output:
            raise SystemExit("Could not prepare the temporary SDK staging parent.")
        created = client.capture(f"mkdir {shlex.quote(stage_dir)}", timeout=15)
        if "[exit:0]" not in created.output:
            raise SystemExit("Could not exclusively create the icon update staging directory.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log = REPO / ".local/sessions" / f"s90f-launcher-icons-update-{stamp}.json"
        try:
            client.push(package, PurePosixPath(stage_dir) / "package-s90f.tar.gz")
            command = root_script_command(
                script,
                (name, stage_dir, package_hash,
                 "0eae5772884883c0d19d78bfe27a3668994f122c838d8f86c37f79d68563011a",
                 assembly_hash),
            )
            result = authenticated_root_command(
                args.host, model, args.callback_host, command, log, timeout=180
            )
            print(result["commands"][0]["stdout"], end="")
            print("Private root session:", log)
        finally:
            cleanup = client.capture(f"rm -rf {shlex.quote(stage_dir)}", timeout=15)
            if "[exit:0]" not in cleanup.output:
                print(f"Temporary icon update stage cleanup should be checked at {stage_dir}.", file=sys.stderr)
        return

    assessment = archive_root._check_target(client)
    print("Archive-route runtime:", assessment.runtime)
    print("Archive-route capabilities:")
    print(assessment.capabilities)
    print("System file hashes captured before root attempt.")

    if args.preflight_only:
        print("Preflight passed. No root attempt was made.")
        return

    framework_paths = (
        "/usr/share/dotnet.tizen/framework/Tizen.NUI.dll",
        "/usr/share/dotnet.tizen/framework/Tizen.Applications.Common.dll",
        "/usr/share/dotnet.tizen/framework/Tizen.System.dll",
        "/usr/share/dotnet.tizen/framework/Tizen.dll",
    )
    commands = ("id; uname -srmo",)
    probe_directory = ""
    probe_remote = ""
    probe_uploaded = False
    probe_directory_created = False
    sdk_tools_directory_created = False
    if args.probe_home_state:
        probe_directory = (
            "/home/owner/share/tmp/sdk_tools/quiet-tizen-probe-"
            + secrets.token_hex(6)
        )
        probe_remote = f"{probe_directory}/Probe.dll"
        probe_local = REPO / ".local/build/Probe/Probe.dll"
        if not probe_local.is_file():
            raise SystemExit("Build the launcher first; Probe.dll is missing.")
        staging = client.capture(
            "test -d /home/owner/share/tmp/sdk_tools && echo present || echo absent",
            timeout=15,
        )
        if "[exit:0]" not in staging.output:
            raise SystemExit("Could not inspect the temporary Probe directory.")
        if "absent\n[exit:0]" in staging.output:
            sdk_tools_directory_created = True
            created = client.capture(
                "mkdir -p /home/owner/share/tmp/sdk_tools", timeout=15
            )
            if "[exit:0]" not in created.output:
                raise SystemExit("Could not create the temporary SDK staging root.")
        created = client.capture(f"mkdir {probe_directory}", timeout=15)
        if "[exit:0]" not in created.output:
            if probe_directory_created:
                client.capture(f"rmdir {probe_directory}", timeout=15)
            if sdk_tools_directory_created:
                client.capture("rmdir /home/owner/share/tmp/sdk_tools", timeout=15)
            raise SystemExit("Could not exclusively create the unique Probe staging directory; no file was overwritten.")
        probe_directory_created = True
        probe_uploaded = True
        try:
            client.push(probe_local, PurePosixPath(probe_remote))
        except Exception:
            try:
                client.capture(f"rm -f {probe_remote}", timeout=15)
                if probe_directory_created:
                    client.capture(f"rmdir {probe_directory}", timeout=15)
                if sdk_tools_directory_created:
                    client.capture("rmdir /home/owner/share/tmp/sdk_tools", timeout=15)
            except Exception:
                pass
            raise
        commands = (
            f"/usr/bin/dotnet {probe_remote}; status=$?; "
            f"rm -f {probe_remote}; exit $status",
        )
    if args.pull_frameworks:
        commands = tuple(quiet_tv.pull_command(path) for path in framework_paths)
    if args.device_inventory:
        commands = (
            "uname -srmo; readlink -f /usr/share/dotnet.tizen/netcoreapp",
            'sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db ".tables"; '
            'sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db ".schema package_app_info"; '
            'sqlite3 -readonly -header -csv /opt/dbspace/.pkgmgr_parser.db '
            '"SELECT app_id,app_disable,app_onboot,app_autorestart FROM package_app_info ORDER BY app_id;"',
            'sqlite3 -readonly /opt/dbspace/.app-context.db ".tables"; '
            'sqlite3 -readonly /opt/dbspace/.app-context.db ".schema key_filter"; '
            'sqlite3 -readonly -header -csv /opt/dbspace/.app-context.db '
            '"SELECT * FROM key_filter;"',
            'for key in db/appfw/home_appid db/appfw/startup_appid '
            'db/was/preload_by_country db/menu/autorun_tv_plus; '
            'do echo "KEY=$key"; vconftool get "$key"; done',
            'find /usr/share/dotnet.tizen -name Tizen.NUI.dll -o '
            '-name Tizen.Applications.Common.dll -o -name Tizen.System.dll '
            '-o -name Tizen.dll',
            'find /opt/usr/apps -mindepth 2 -maxdepth 2 -name appinfo.xml -print',
        )
    if args.network_diagnostics:
        commands = (
            "date -u; ip addr; ip route",
            "echo RESOLV_CONF; cat /etc/resolv.conf; "
            "echo HOSTS_METADATA; stat -c '%n %s bytes' /etc/hosts; "
            "sha256sum /etc/hosts; echo RELEVANT_HOSTS_ENTRIES; "
            "grep -iE 'youtube|google|jellyfin|spotify|netflix|samsung' /etc/hosts "
            "|| true",
            "echo NETWORK_TOOLS; for x in curl wget getent nslookup ping; do "
            "command -v $x || true; done; echo DNS_LOOKUPS; "
            "if command -v getent >/dev/null 2>&1; then "
            "for h in www.youtube.com youtubei.googleapis.com www.google.com; do "
            "echo HOST=$h; getent ahostsv4 $h || true; done; "
            "elif command -v nslookup >/dev/null 2>&1; then "
            "for h in www.youtube.com youtubei.googleapis.com www.google.com; do "
            "echo HOST=$h; nslookup $h || true; done; "
            "else echo 'No DNS lookup utility found'; fi",
            "if command -v curl >/dev/null 2>&1; then "
            "for u in https://www.google.com/generate_204 "
            "https://www.youtube.com/generate_204; do echo URL=$u; "
            "curl -sS -o /dev/null -w 'HTTP=%{http_code} REMOTE_IP=%{remote_ip} TLS=%{ssl_verify_result}\\n' "
            "--connect-timeout 5 --max-time 12 $u || echo CURL_FAILED=$?; done; "
            "elif command -v wget >/dev/null 2>&1; then "
            "wget -S --spider -T 12 https://www.google.com/generate_204 2>&1; "
            "wget -S --spider -T 12 https://www.youtube.com/generate_204 2>&1; "
            "else echo 'No curl/wget available for outbound HTTPS checks'; fi",
        )
    if args.launcher_update_inventory:
        name = args.launcher_update_inventory
        if not re.fullmatch(r"quiet-home-s90f-[A-Za-z0-9_-]+", name):
            raise SystemExit("Invalid S90F backup name.")
        backup = f"/opt/usr/share/quiet-tizen-backups/{name}"
        commands = (
            f"D={shlex.quote(backup)}; A=/opt/usr/apps/com.samsung.tv.AICompanionUI; "
            "echo BACKUP_DIR; ls -ldn \"$D\" 2>&1; "
            "echo BACKUP_FILES; find \"$D\" -maxdepth 2 -type f -print 2>&1",
            "A=/opt/usr/apps/com.samsung.tv.AICompanionUI; "
            "echo INSTALLED_LAUNCHER; ls -ldn \"$A\" \"$A/res/quiet-home\"; "
            "sha256sum \"$A/bin/AICompanionUI.dll\"; "
            "sha256sum \"$A/res/quiet-home/home-background.jpg\" "
            "\"$A/res/quiet-home/apps.json\" 2>&1",
            "for key in db/appfw/home_appid db/appfw/startup_appid; do "
            "echo KEY=$key; vconftool get \"$key\"; done; "
            "echo LEFTOVER_ICON_STAGES; "
            "find /home/owner/share/tmp/sdk_tools -maxdepth 1 -type d -name 'quiet-tizen-icons-*' -print 2>&1",
        )
    if args.app_icon_inventory:
        app_ids = (
            "org.tizen.netflix-app", "9Ur5IzDKqV.TizenYouTube",
            "rTn6ClEurC.Jellyfin", "RtArchTzn0.RetroArch",
            "rJeHak5zRg.Spotify", "org.tizen.tv-viewer",
        )
        commands = tuple(
            "app='" + app_id + "'; "
            "pkg=$(sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "
            "\"SELECT package FROM package_app_info WHERE app_id='$app' LIMIT 1;\"); "
            "root=$(sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db "
            "\"SELECT root_path FROM package_info WHERE package='$pkg' LIMIT 1;\"); "
            "echo APP=$app PACKAGE=$pkg ROOT=$root; "
            "if [ -n \"$root\" ] && [ -d \"$root\" ]; then "
            "find \"$root\" -maxdepth 7 -type f | grep -Ei 'icon|logo|app' | "
            "while IFS= read -r f; do stat -c '%n %s' \"$f\"; done | awk 'NR<=80 {print}'; "
            "for f in \"$root/config.xml\" \"$root/tizen-manifest.xml\" "
            "\"$root/res/wgt/config.xml\" \"$root/appinfo.xml\"; do "
            "if [ -f \"$f\" ]; then grep -Hni -E 'icon|image' \"$f\"; fi; "
            "done | awk 'NR<=60 {print}'; "
            "else echo 'NO_PACKAGE_ROOT'; fi"
            for app_id in app_ids
        )
    if args.pull_app_icons:
        icon_sources = (
            ("netflix.png", "find /opt/usr/apps/org.tizen.netflix-app -type f -name org.tizen.netflix-app.png -print -quit"),
            ("youtube.png", "echo /opt/usr/apps/9Ur5IzDKqV/shared/res/9Ur5IzDKqV.TizenYouTube.png"),
            ("jellyfin.png", "echo /opt/usr/apps/rTn6ClEurC/shared/res/rTn6ClEurC.Jellyfin.png"),
            ("retroarch.png", "echo /opt/usr/apps/RtArchTzn0/shared/res/RtArchTzn0.RetroArch.png"),
            ("spotify.png", "echo /opt/usr/apps/rJeHak5zRg/shared/res/rJeHak5zRg.Spotify.png"),
            ("live-tv.svg", "echo /usr/apps/com.samsung.tv.theme-resource/shared/res/VD_ICONS/i_icon_device_m_tv.svg"),
        )
        commands = tuple(
            "f=$( " + find_command + " ); test -s \"$f\"; "
            "echo PATH=\"$f\"; stat -c 'SIZE=%s' \"$f\"; "
            "sha256sum \"$f\" | awk '{print \"SHA256=\"$1}'"
            for _, find_command in icon_sources
        )
    if args.install_preflight_only:
        commands = (
            'sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db '
            '"SELECT app_id,app_component,app_exec,app_type,app_package_type,app_package_system,app_installed_storage,app_root_path,package FROM package_app_info WHERE app_id IN (\'com.samsung.tv.bixby-promotion\',\'com.samsung.tv.AICompanionUI\',\'com.samsung.tv.AICompanionAgent\',\'com.samsung.tv.ai-discovery-ui\',\'com.samsung.tv.ai-discovery-service\',\'homeLauncr.Launcher\') ORDER BY app_id;"',
            'for d in /opt/usr/apps/com.samsung.tv.bixby-promotion /opt/usr/apps/com.samsung.tv.AICompanionUI /opt/usr/apps/com.samsung.tv.AICompanionAgent /opt/usr/apps/com.samsung.tv.ai-discovery-ui /opt/usr/apps/com.samsung.tv.ai-discovery-service /opt/usr/apps/homeLauncr; do '
            'echo "APP_DIR=$d"; if [ -d "$d" ]; then ls -ldn "$d"; find "$d" -maxdepth 3 -type f -print | awk \'NR<=30 {print}\'; else echo absent; fi; done',
            'for f in /opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.dll /opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.runtimeconfig.json /opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.deps.json /opt/usr/apps/homeLauncr/config.xml /opt/usr/apps/homeLauncr/index.html; do if [ -f "$f" ]; then stat -c "%n %s bytes owner=%u:%g mode=%a" "$f"; sha256sum "$f"; fi; done',
            'cat /opt/usr/apps/com.samsung.tv.AICompanionUI/bin/AICompanionUI.runtimeconfig.json; '
            'sed -n "1,180p" /opt/usr/apps/homeLauncr/res/wgt/config.xml; '
            'sed -n "1,140p" /opt/usr/apps/homeLauncr/res/wgt/index.html',
            'sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db '
            '"SELECT package,package_type,package_version,package_system,package_removable,package_readonly,mainapp_id,root_path FROM package_info WHERE package IN (\'com.samsung.tv.AICompanionUI\',\'homeLauncr\') ORDER BY package;"',
            'sqlite3 -readonly /opt/dbspace/.pkgmgr_parser.db '
            '"PRAGMA table_info(package_info);"',
            'for p in /usr/bin/pkgcmd /usr/bin/app_launcher /usr/bin/chsmack; do ls -l "$p"; done',
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    log = REPO / ".local/sessions" / f"s90f-root-{stamp}.json"
    try:
        result = asyncio.run(
            archive_root.probe(
                args.host,
                model=model,
                callback_host=args.callback_host,
                payloads=PAYLOADS,
                commands=commands,
            )
        )
    except Exception as error:
        quiet_tv.save_private(
            log,
            (json.dumps({"model": model, "host": args.host, "error": str(error)}, indent=2) + "\n").encode(),
        )
        raise SystemExit(f"Probe failed; inspect {log}. Do not retry until reviewed.") from error
    finally:
        if probe_uploaded:
            try:
                cleanup = client.capture(f"rm -f {probe_remote}", timeout=15)
                if "[exit:0]" not in cleanup.output:
                    raise RuntimeError(cleanup.output.strip())
                if probe_directory_created:
                    cleanup = client.capture(f"rmdir {probe_directory}", timeout=15)
                    if "[exit:0]" not in cleanup.output:
                        raise RuntimeError(cleanup.output.strip())
                if sdk_tools_directory_created:
                    cleanup = client.capture("rmdir /home/owner/share/tmp/sdk_tools", timeout=15)
                    if "[exit:0]" not in cleanup.output:
                        raise RuntimeError(cleanup.output.strip())
            except Exception as error:
                print(f"Warning: temporary Probe.dll cleanup needs review: {error}")

    if result.get("uid") != 0 or result.get("euid") != 0:
        raise SystemExit(f"Root was not authenticated; private log: {log}")
    if not result.get("system_files_unchanged") or not result.get("staging_cleaned"):
        raise SystemExit(f"Cleanup/hash check failed; inspect private log: {log}")

    if args.pull_frameworks:
        framework_dir = REPO / ".local/tv-framework"
        framework_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for response, remote in zip(result.get("commands", []), framework_paths):
            if response.get("exit_code") != 0 or response.get("timed_out"):
                quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())
                raise SystemExit(f"Framework pull failed for {remote}; inspect {log}.")
            data = quiet_tv.decode_pull(response["stdout"])
            destination = framework_dir / Path(remote).name
            quiet_tv.save_private(destination, data)
            response["stdout"] = (
                f"Saved private framework reference {destination.name} ({len(data)} bytes)."
            )
        result["framework_paths"] = [Path(path).name for path in framework_paths]

    if args.pull_app_icons:
        icon_sources = (
            "netflix.png", "youtube.png", "jellyfin.png",
            "retroarch.png", "spotify.png", "live-tv.svg",
        )
        icon_dir = REPO / ".local/tv-app-icons"
        icon_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        result["app_icons"] = []
        quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())
        specs = []
        for response, filename in zip(result.get("commands", []), icon_sources):
            if response.get("exit_code") != 0 or response.get("timed_out"):
                quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())
                raise SystemExit(f"Icon extraction failed for {filename}; inspect {log}.")
            stdout = response["stdout"]
            try:
                remote_path = re.search(r"(?m)^PATH=(.+)$", stdout).group(1)
                size = int(re.search(r"(?m)^SIZE=(\d+)$", stdout).group(1))
                expected_hash = re.search(r"(?m)^SHA256=([0-9a-f]{64})$", stdout).group(1)
            except (AttributeError, IndexError, ValueError) as error:
                quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())
                raise SystemExit(f"Malformed icon metadata for {filename}; inspect {log}.") from error
            specs.append({"file": filename, "source": remote_path, "size": size,
                          "sha256": expected_hash,
                          "chunks": (size + 23_999) // 24_000})
        chunk_commands = tuple(
            "printf 'DATA='; dd if=" + shlex.quote(spec["source"])
            + " bs=24000 skip=" + str(index) + " count=1 2>/dev/null | base64 -w0"
            for spec in specs for index in range(spec["chunks"])
        )
        chunk_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        chunk_log = REPO / ".local/sessions" / f"s90f-app-icon-chunks-{chunk_stamp}.json"
        chunk_result = asyncio.run(archive_root.probe(
            args.host, model=model, callback_host=args.callback_host,
            payloads=PAYLOADS, commands=chunk_commands, command_timeout=90,
        ))
        quiet_tv.save_private(chunk_log, (json.dumps(chunk_result, indent=2) + "\n").encode())
        if (chunk_result.get("uid") != 0 or chunk_result.get("euid") != 0
                or not chunk_result.get("system_files_unchanged")
                or not chunk_result.get("staging_cleaned")):
            raise SystemExit(f"Icon transfer session verification failed; inspect {chunk_log}.")
        responses = chunk_result.get("commands", [])
        if len(responses) != len(chunk_commands) or any(
            item.get("exit_code") != 0 or item.get("timed_out") for item in responses
        ):
            raise SystemExit(f"Icon data chunk failed; inspect {chunk_log}.")
        response_index = 0
        for spec in specs:
            data = bytearray()
            for _ in range(spec["chunks"]):
                stdout = responses[response_index]["stdout"]
                response_index += 1
                encoded_match = re.search(r"DATA=([A-Za-z0-9+/=]+)", stdout)
                if not encoded_match:
                    raise SystemExit(f"Malformed icon data chunk; inspect {chunk_log}.")
                data.extend(base64.b64decode(encoded_match.group(1), validate=True))
            image_data = bytes(data)
            if len(image_data) != spec["size"] or hashlib.sha256(image_data).hexdigest() != spec["sha256"]:
                raise SystemExit(f"Icon verification failed for {spec['file']}; no file saved.")
            filename = spec["file"]
            destination = icon_dir / filename
            quiet_tv.save_private(destination, image_data)
            result["app_icons"].append({
                "file": filename, "source": spec["source"], "bytes": spec["size"],
                "sha256": spec["sha256"],
            })
        for response, spec in zip(result.get("commands", []), specs):
            response["stdout"] = f"Saved verified TV app icon {spec['file']} ({spec['size']} bytes)."
        result["icon_transfer_log"] = str(chunk_log)

    quiet_tv.save_private(log, (json.dumps(result, indent=2) + "\n").encode())

    print(json.dumps(result, indent=2))
    print("Authenticated UID/EUID 0; system-file hashes unchanged; staging cleaned.")
    print("Private session record:", log)


if __name__ == "__main__":
    main()
