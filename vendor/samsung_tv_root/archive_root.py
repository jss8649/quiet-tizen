"""SDK archive launcher root route for owner-authorized TVs."""

from __future__ import annotations

import asyncio
import hashlib
import io
import ipaddress
import json
import re
import secrets
import shlex
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .resources import payload_directory
from .root_agent import MAXIMUM_FRAME_BYTES, RootAgentServer, generate_secret, write_secret
from .sdb import (CaptureResult, SDB_APPINSTALL_MAX_SAFE_BYTES, SdbClient, SdbError,
                  find_sdb, route_callback_host)


STAGING_ROOT = PurePosixPath("/home/owner/share/tmp/sdk_tools")
ON_DEMAND = STAGING_ROOT / "on-demand"
PAYLOAD_FILES = (
    "SamsungTvArchiveRoot.dll",
    "SamsungTvRootAgent.dll",
)
RUNTIME_CONFIG_FILES = (
    "SamsungTvArchiveRoot.runtimeconfig.json",
    "SamsungTvRootAgent.runtimeconfig.json",
)
SYSTEM_HASH_COMMAND = "sha256sum /etc/passwd /usr/share/sdbd/public.pem"


class ArchiveRootError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetAssessment:
    capabilities: str
    original_hashes: str
    runtime: str


def _capture(client: SdbClient, command: str, timeout: float = 15.0) -> str:
    result = client.capture(command, timeout=timeout)
    if "[exit:0]" not in result.output:
        raise ArchiveRootError(
            f"SDK command failed: {command}: {result.output.strip()}"
        )
    return result.output.split("\n[exit:0]", 1)[0].strip()


def _file_capabilities(line: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for names, flags in re.findall(
        r"(cap_[a-z0-9_]+(?:,cap_[a-z0-9_]+)*)[=+]([eip]+)", line
    ):
        for name in names.split(","):
            result[name] = flags
    return result


def _check_target(client: SdbClient) -> TargetAssessment:
    client.connect()
    client.require_device()
    client.require_shell_injection()
    capabilities = _capture(client, "getcap /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher")
    lines = capabilities.splitlines()
    dotnet = next((line for line in lines if "/usr/bin/dotnet" in line), "")
    launcher = next(
        (line for line in lines if "/usr/sbin/sdbd-tarlauncher" in line), ""
    )
    dotnet_caps = _file_capabilities(dotnet)
    launcher_caps = _file_capabilities(launcher)
    if not all(
        "e" in dotnet_caps.get(name, "") for name in ("cap_setgid", "cap_sys_admin")
    ):
        raise ArchiveRootError("dotnet lacks effective SETGID/SYS_ADMIN capabilities")
    if not all(
        "e" in launcher_caps.get(name, "") for name in ("cap_setgid", "cap_setuid")
    ):
        raise ArchiveRootError(
            "sdbd-tarlauncher lacks effective SETUID/SETGID capabilities"
        )
    try:
        runtimes = _capture(client, "/usr/bin/dotnet --list-runtimes")
    except ArchiveRootError as error:
        if "Unknown option --list-runtimes" not in str(error):
            raise
        # Samsung's custom host on this TV omits --list-runtimes.
        # Verify the actual CLR and core assembly at its resolved runtime path.
        runtimes = _capture(
            client,
            'd=$(readlink -f /usr/share/dotnet.tizen/netcoreapp) && '
            'test -f "$d/libcoreclr.so" && '
            'test -f "$d/System.Private.CoreLib.dll" && '
            'printf "Microsoft.NETCore.App %s [%s]\\n" "${d##*/}" "$d"',
        )
    majors = {
        int(match.group(1))
        for line in runtimes.splitlines()
        if (match := re.match(r"Microsoft\.NETCore\.App (\d+)\.\d+\.\d+\s+\[", line))
    }
    if any(major >= 6 for major in majors):
        runtime = "6.0"
    elif 3 in majors and any(
        re.match(r"Microsoft\.NETCore\.App 3\.1\.\d+\s+\[", line)
        for line in runtimes.splitlines()
    ):
        runtime = "3.1"
    else:
        raise ArchiveRootError("no supported Microsoft.NETCore.App runtime (3.1 or 6+)")
    tar_options = _capture(client, "/usr/bin/tar --help | grep -- --to-command")
    if "--to-command" not in tar_options:
        raise ArchiveRootError("TV tar does not support --to-command")
    return TargetAssessment(
        capabilities, _capture(client, SYSTEM_HASH_COMMAND), runtime
    )


def _openssl(*arguments: str) -> None:
    result = subprocess.run(
        ("openssl", *arguments), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ArchiveRootError(
            f"openssl {arguments[0]} failed: {result.stderr.strip()}"
        )


def _prepare_artifacts(
    directory: Path,
    runtime: str,
    package: str,
    callback_host: str,
    callback_port: int,
    secret: bytes,
) -> None:
    staging = STAGING_ROOT / package
    private_key = directory / "private.pem"
    public_key = directory / "public.pem"
    archive = directory / f"{package}.tar.gz"
    signature = directory / f"{package}.tar.gz.signature"
    _openssl(
        "genpkey",
        "-algorithm",
        "RSA",
        "-pkeyopt",
        "rsa_keygen_bits:2048",
        "-out",
        str(private_key),
    )
    _openssl("pkey", "-in", str(private_key), "-pubout", "-out", str(public_key))
    (directory / "passwd").write_text(
        "owner:x:0:0:owner:/home/owner:/bin/sh\n", encoding="ascii"
    )
    runtime_version = "3.1.0" if runtime == "3.1" else "6.0.0"
    runtime_config = {
        "runtimeOptions": {
            "tfm": "netcoreapp3.1" if runtime == "3.1" else "net6.0",
            "rollForward": "Major" if runtime == "6.0" else "LatestPatch",
            "framework": {
                "name": "Microsoft.NETCore.App",
                "version": runtime_version,
            },
        }
    }
    for name in RUNTIME_CONFIG_FILES:
        (directory / name).write_text(
            json.dumps(runtime_config) + "\n", encoding="ascii"
        )
    write_secret(directory / "root-agent.token", secret)
    script = (
        "#!/bin/sh\n"
        f"exec /usr/bin/dotnet {staging}/SamsungTvRootAgent.dll "
        f"{callback_host} {callback_port} {staging}/root-agent.token {staging}\n"
    ).encode("ascii")
    with tarfile.open(archive, "w:gz") as output:
        member = tarfile.TarInfo("launch.sh")
        member.size = len(script)
        member.mode = 0o600
        member.mtime = 0
        output.addfile(member, io.BytesIO(script))
    _openssl(
        "dgst",
        "-sha256",
        "-sign",
        str(private_key),
        "-out",
        str(signature),
        str(archive),
    )
    _openssl(
        "dgst",
        "-sha256",
        "-verify",
        str(public_key),
        "-signature",
        str(signature),
        str(archive),
    )


def _stage(client: SdbClient, directory: Path, payloads: Path, package: str) -> None:
    staging = STAGING_ROOT / package
    _capture(client, f"/bin/mkdir -p {staging}")
    _capture(client, f"/bin/mkdir -p {ON_DEMAND}")
    for name in PAYLOAD_FILES:
        source = payloads / name
        if not source.is_file():
            raise ArchiveRootError(f"missing payload {source}; run make common-payload")
        client.push(source, staging / name)
    for name in RUNTIME_CONFIG_FILES:
        client.push(directory / name, staging / name)
    for name in ("public.pem", "passwd", "root-agent.token"):
        client.push(directory / name, staging / name)
    archive_name = f"{package}.tar.gz"
    client.push(directory / archive_name, ON_DEMAND / archive_name)
    client.push(
        directory / f"{archive_name}.signature",
        ON_DEMAND / f"{archive_name}.signature",
    )


def _cleanup(client: SdbClient, package: str) -> bool:
    staging = STAGING_ROOT / package
    archive = ON_DEMAND / f"{package}.tar.gz"
    signature = ON_DEMAND / f"{package}.tar.gz.signature"
    _capture(client, f"/bin/rm -rf {staging}")
    _capture(client, f"/bin/rm -f {archive}")
    _capture(client, f"/bin/rm -f {signature}")
    for path in (staging, archive, signature):
        if _capture(client, f"test ! -e {path} && echo absent") != "absent":
            return False
    return True


async def _read_staged_files(connection, staging, files, output_dir, timeout):
    """Copy bounded files into this session's staging and verify private downloads."""
    if output_dir is None:
        raise ValueError("Private file destination is required.")
    if len({name for name, _ in files}) != len(files):
        raise ValueError("Duplicate private file destination.")
    for name, source in files:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name) or not source.startswith("/"):
            raise ValueError("Invalid private file request.")
        if (output_dir / name).exists():
            raise FileExistsError(f"Preserve existing private file: {name}")
    observations = []
    for name, source in files:
        staged = staging / name
        copy = await connection.execute(
            f"/bin/cp {shlex.quote(source)} {shlex.quote(str(staged))}", timeout)
        if copy.exit_code or copy.timed_out:
            raise ArchiveRootError(f"Could not stage private file {name}.")
        downloaded = await connection.read_file(str(staged), timeout)
        original = await connection.execute(f"sha256sum {shlex.quote(source)}", timeout)
        digest = original.stdout.split()[0] if original.stdout.split() else ""
        if (original.exit_code or original.timed_out or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or digest != downloaded.sha256 or hashlib.sha256(downloaded.data).hexdigest() != digest):
            raise ArchiveRootError(f"Private file checksum mismatch for {name}.")
        destination = output_dir / name
        with destination.open("xb") as stream:
            stream.write(downloaded.data)
        destination.chmod(0o600)
        observations.append({"name": name, "size_bytes": len(downloaded.data), "sha256": digest})
    return observations


async def probe(
    tv_host: str,
    *,
    model: str | None = None,
    callback_host: str | None = None,
    bind_host: str | None = None,
    sdb_timeout: float = 15.0,
    accept_timeout: float = 30.0,
    command_timeout: float = 45.0,
    commands: tuple[str, ...] = (),
    payloads: Path | None = None,
    max_appinstall_bytes: int = SDB_APPINSTALL_MAX_SAFE_BYTES,
    read_files: tuple[tuple[str, str], ...] = (),
    output_dir: Path | None = None,
    staged_files: tuple[tuple[str, Path | bytes], ...] = (),
    run_staged: tuple[str, ...] = (),
    run_staged_shell: tuple[str, str] | None = None,
) -> dict[str, object]:
    ipaddress.IPv4Address(tv_host)
    callback = callback_host or route_callback_host(tv_host)
    ipaddress.IPv4Address(callback)
    bind = bind_host or callback
    ipaddress.IPv4Address(bind)
    client = SdbClient(find_sdb(), tv_host, timeout=sdb_timeout,
                       max_appinstall_bytes=max_appinstall_bytes)
    assessment = await asyncio.to_thread(_check_target, client)
    payloads = payloads or payload_directory(
        "common31" if assessment.runtime == "3.1" else "common"
    )
    for name in PAYLOAD_FILES:
        if not (payloads / name).is_file():
            raise ArchiveRootError(f"missing payload {payloads / name}")
    package = "archive-root-" + secrets.token_hex(8)
    staging_started = False
    launch_task: asyncio.Task[CaptureResult] | None = None
    server = RootAgentServer(bind, 0, tv_host, generate_secret(), require_root=True)
    await server.start()
    try:
        with tempfile.TemporaryDirectory(prefix="samsung-tv-archive-root-") as temp:
            directory = Path(temp)
            _prepare_artifacts(
                directory,
                assessment.runtime,
                package,
                callback,
                server.listening_port,
                server.secret,
            )
            staging_started = True
            await asyncio.to_thread(_stage, client, directory, payloads, package)
            command = (
                f"/usr/bin/dotnet {STAGING_ROOT / package}/SamsungTvArchiveRoot.dll "
                f"{package}"
            )
            launch_task = asyncio.create_task(
                asyncio.to_thread(
                    client.capture,
                    command,
                    callback_host=callback,
                    bind_host=bind,
                    timeout=accept_timeout + 20,
                )
            )
            try:
                connection = await server.accept(accept_timeout)
            except Exception as error:
                log_result = await asyncio.to_thread(
                    client.capture,
                    f"/bin/cat {STAGING_ROOT / package}/launcher.log",
                    timeout=10,
                )
                log = log_result.output.strip()
                launch_output = "pending"
                if launch_task.done():
                    try:
                        launch_output = launch_task.result().output.strip()
                    except Exception as launch_error:
                        launch_output = str(launch_error)
                raise ArchiveRootError(
                    f"no authenticated root callback; launch output: {launch_output}; "
                    f"launcher log: {log}"
                ) from error
            try:
                identity = await connection.ping()
                evidence = {
                    "model": model,
                    "host": tv_host,
                    "runtime": assessment.runtime,
                    "authenticated": True,
                    "uid": identity.uid,
                    "euid": identity.euid,
                    "gid": identity.gid,
                    "egid": identity.egid,
                    "cap_eff": identity.effective_capabilities,
                    "smack": identity.smack_label.strip(),
                    "preflight_capabilities": assessment.capabilities,
                }
                staged_names = set()
                for name, local in staged_files:
                    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name)
                            or name in staged_names):
                        raise ValueError("Invalid staged file name.")
                    staged_names.add(name)
                    data = local if isinstance(local, bytes) else local.read_bytes()
                    if len(data) > MAXIMUM_FRAME_BYTES:
                        raise ValueError("Staged file exceeds root-agent limit.")
                    written = await connection.write_file(
                        str(STAGING_ROOT / package / name), data, command_timeout)
                    if written.sha256 != hashlib.sha256(data).hexdigest():
                        raise ArchiveRootError(f"Staged file verification failed: {name}")
                if run_staged:
                    if any(name not in staged_names for name in run_staged):
                        raise ValueError("Only uploaded files may be run from staging.")
                    evidence["commands"] = []
                    for name in run_staged:
                        command_text = f"/usr/bin/dotnet {STAGING_ROOT / package / name}"
                        result = await connection.execute(command_text, command_timeout)
                        evidence["commands"].append(
                            {"command": command_text, "exit_code": result.exit_code,
                             "timed_out": result.timed_out, "stdout": result.stdout,
                             "stderr": result.stderr}
                        )
                if run_staged_shell:
                    name, phase = run_staged_shell
                    if name not in staged_names or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", phase):
                        raise ValueError("Only an uploaded script and a simple phase name may be run.")
                    command_text = (f"/bin/cat {shlex.quote(str(STAGING_ROOT / package / name))} "
                                    f"| /bin/sh -s -- {shlex.quote(phase)} "
                                    f"{shlex.quote(str(STAGING_ROOT / package))}")
                    result = await connection.execute(command_text, command_timeout)
                    evidence.setdefault("commands", []).append(
                        {"command": command_text, "exit_code": result.exit_code,
                         "timed_out": result.timed_out, "stdout": result.stdout,
                         "stderr": result.stderr}
                    )
                if commands:
                    evidence.setdefault("commands", [])
                    for command_text in commands:
                        result = await connection.execute(command_text, command_timeout)
                        evidence["commands"].append(
                            {
                                "command": command_text,
                                "exit_code": result.exit_code,
                                "timed_out": result.timed_out,
                                "stdout": result.stdout,
                                "stderr": result.stderr,
                            }
                        )
                if read_files:
                    evidence["private_files"] = await _read_staged_files(
                        connection, STAGING_ROOT / package, read_files,
                        output_dir, command_timeout)
            finally:
                await connection.shutdown()
            if launch_task is not None:
                launch_result = await asyncio.wait_for(launch_task, timeout=15)
                if "[exit:0]" not in launch_result.output:
                    raise ArchiveRootError(
                        "launcher exited unsuccessfully: "
                        + launch_result.output.strip()
                    )
            return evidence
    finally:
        await server.close()
        if launch_task is not None and not launch_task.done():
            try:
                await asyncio.wait_for(launch_task, timeout=5)
            except Exception:
                pass
        cleaned = False
        if staging_started:
            try:
                cleaned = await asyncio.to_thread(_cleanup, client, package)
            except (ArchiveRootError, SdbError):
                pass
        final_hashes = await asyncio.to_thread(_capture, client, SYSTEM_HASH_COMMAND)
        if "evidence" in locals():
            evidence["system_files_unchanged"] = (
                final_hashes == assessment.original_hashes
            )
            evidence["staging_cleaned"] = cleaned
            if not evidence["system_files_unchanged"] or not cleaned:
                raise ArchiveRootError(
                    "root callback succeeded, but system-file or cleanup checks failed; "
                    f"staging={STAGING_ROOT / package}"
                )
