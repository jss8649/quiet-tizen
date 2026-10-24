"""Fixed-scope, non-root compatibility observations; never install or change settings."""
import re
import shlex

from samsung_tv_root.archive_root import _file_capabilities


# These are candidates to inspect, not assumptions that they exist on a new TV.
CANDIDATE_FILES = {
    "bixby_promotion": "/opt/usr/apps/com.samsung.tv.bixby-promotion/bin/BixbyPromotion.dll",
    "quicklaunch": "/opt/usr/apps/com.samsung.tv.quicklaunch/bin/QuickLaunch.dll",
    "package_registry": "/opt/dbspace/.pkgmgr_parser.db",
    "key_registry": "/opt/dbspace/.app-context.db",
    "source_api": "/usr/lib/libsource-api.so",
    "settings_api": "/usr/lib/libsettings-api.so",
    "sound_api": "/usr/lib/libcapi-media-sound-manager-tv.so.0",
    "app_control_api": "/usr/lib/libcapi-appfw-app-control.so.0",
}

RUNTIME_FALLBACK = (
    'd=$(readlink -f /usr/share/dotnet.tizen/netcoreapp) && '
    'test -f "$d/libcoreclr.so" && test -f "$d/System.Private.CoreLib.dll" && '
    'printf "Microsoft.NETCore.App %s [%s]\\n" "${d##*/}" "$d"'
)


class DiagnosticCommandError(RuntimeError):
    pass


def capture_text(client, command, callback_host=None):
    result = client.capture(command, callback_host=callback_host, timeout=15)
    match = re.search(r"\n\[exit:(\d+)\]\s*$", result.output)
    if not match or match.group(1) != "0":
        # Raw command output is used locally only to recognize a narrow fallback.
        # It is deliberately not copied into the report.
        raise DiagnosticCommandError(result.output)
    return result.output[:match.start()].strip()


def failure_code(error):
    text = str(error).lower()
    if "callback" in text or "cannot listen" in text:
        return "callback_unavailable_check_host_ip_and_firewall"
    if "shell execution was not confirmed" in text:
        return "sdk_command_route_not_confirmed"
    if "permission denied" in text:
        return "not_readable_as_sdk_user"
    if "no such file" in text or "not found" in text:
        return "file_or_command_unavailable"
    if "timed out" in text or "timeout" in text:
        return "check_timed_out"
    return "check_incomplete"


def file_probe_command():
    commands = []
    for name, path in CANDIDATE_FILES.items():
        quoted = shlex.quote(path)
        commands.append(
            f"if test -e {quoted}; then "
            f"r=0; test ! -r {quoted} || r=1; "
            f"m=$(stat -c '%u:%g:%a:%s' {quoted} 2>/dev/null) || m=unknown; "
            f"printf '{name}|1|%s|%s\\n' \"$r\" \"$m\"; "
            f"else printf '{name}|0|0|unknown\\n'; fi"
        )
    return "; ".join(commands)


def parse_files(output):
    files = {}
    for line in output.splitlines():
        fields = line.split("|")
        if (len(fields) != 4 or fields[0] not in CANDIDATE_FILES
                or fields[1] not in ("0", "1") or fields[2] not in ("0", "1")
                or fields[0] in files):
            raise ValueError("Unexpected candidate-file observation")
        item = {"path": CANDIDATE_FILES[fields[0]],
                "visible_to_sdk": fields[1] == "1", "readable": fields[2] == "1"}
        if re.fullmatch(r"\d+:\d+:[0-7]{3,4}:\d+", fields[3]):
            uid, gid, mode, size = fields[3].split(":")
            item.update(owner_uid=int(uid), owner_gid=int(gid), mode=mode, size_bytes=int(size))
        elif fields[3] != "unknown":
            raise ValueError("Unexpected file metadata")
        files[fields[0]] = item
    if set(files) != set(CANDIDATE_FILES):
        raise ValueError("Incomplete candidate-file observations")
    return files


def parse_runtime(output):
    versions = []
    for line in output.splitlines():
        match = re.fullmatch(r"Microsoft\.NETCore\.App (\d+\.\d+\.\d+) \[[^\r\n]+\]", line.strip())
        if match:
            versions.append(match.group(1))
    if not versions:
        raise ValueError("No recognized runtime version")
    return {"versions": sorted(set(versions)),
            "net6_or_later_present": any(int(v.split(".")[0]) >= 6 for v in versions)}


def parse_kernel(output):
    # uname -srmo intentionally omits hostname and the potentially personal build string.
    if not re.fullmatch(r"Linux [A-Za-z0-9_.+~/-]+ [A-Za-z0-9_-]+(?: GNU/Linux)?", output):
        raise ValueError("Unrecognized kernel observation")
    return output


def parse_columns(output):
    columns = []
    for line in output.splitlines():
        fields = line.split("|")
        if (len(fields) != 2 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", fields[0])
                or not re.fullmatch(r"[A-Za-z0-9_ (),]{0,40}", fields[1])):
            raise ValueError("Unrecognized schema observation")
        columns.append({"name": fields[0], "type": fields[1]})
    if not columns:
        raise ValueError("Required table not observed")
    return columns


def collect_diagnostics(client, profile, model, firmware, callback_host=None):
    """No root payloads or user-supplied shell commands are used here.

    The existing SDK transport uses temporary files. File visibility as the SDK
    user does not establish absence on disk, and file presence is not API proof.
    """
    report = {
        "report_version": 1,
        "profile": {"model": profile["model"], "firmware": profile["firmware"],
                    "support_status": profile["support_status"]},
        "identity": {"sdb_model": model, "declared_firmware": firmware,
                     "firmware_source": "operator_about_screen",
                     "matches_profile": model == profile["model"] and firmware == profile["firmware"]},
        "scope": "non-root diagnostics; temporary SDK transport files; no persistent configuration changes",
        "root_tested": False,
        "launcher_tested": False,
        "cleanup_tested": False,
        "checks": {},
        "archive_prerequisites": "not_established",
        "remaining_device_checks": [
            "authenticated temporary root and cleanup proof",
            "matching native framework assemblies and API behavior",
            "actual HDMI source IDs and switching",
            "Home/startup selectors and settings key routes",
            "installed app IDs, service stop conditions and selected cleanup",
            "backup/restore, full restart, standby/wake and visible launcher operation",
        ],
    }
    checks = report["checks"]
    try:
        client.require_shell_injection()
    except Exception as error:
        checks["sdk_command_route"] = {"status": "incomplete", "reason": failure_code(error)}
        return report
    checks["sdk_command_route"] = {"status": "passed"}

    def observe(name, command, parser=lambda value: value):
        try:
            value = parser(capture_text(client, command, callback_host))
            checks[name] = {"status": "observed", "value": value}
            return value
        except Exception as error:
            checks[name] = {"status": "incomplete", "reason": failure_code(error)}
            return None

    observe("kernel", "uname -srmo", parse_kernel)

    def parse_capabilities(output):
        observed = {}
        for path in ("/usr/bin/dotnet", "/usr/sbin/sdbd-tarlauncher"):
            line = next((line for line in output.splitlines() if line.startswith(path + " ")), "")
            observed[path] = _file_capabilities(line)
        return observed

    caps = observe("archive_file_capabilities",
                   "getcap /usr/bin/dotnet /usr/sbin/sdbd-tarlauncher", parse_capabilities)
    try:
        try:
            runtime_text = capture_text(client, "/usr/bin/dotnet --list-runtimes", callback_host)
            method = "list-runtimes"
        except DiagnosticCommandError as error:
            if "Unknown option --list-runtimes" not in str(error):
                raise
            runtime_text = capture_text(client, RUNTIME_FALLBACK, callback_host)
            method = "resolved-clr-files"
        runtime = parse_runtime(runtime_text)
        checks["dotnet_runtime"] = {"status": "observed", "method": method, "value": runtime}
    except Exception as error:
        runtime = None
        checks["dotnet_runtime"] = {"status": "incomplete", "reason": failure_code(error)}

    tar = observe("tar_to_command", "/usr/bin/tar --help", lambda value: "--to-command" in value)
    observe("candidate_files", file_probe_command(), parse_files)
    for name, database, table in (
        ("package_registry_columns", "/opt/dbspace/.pkgmgr_parser.db", "package_app_info"),
        ("key_registry_columns", "/opt/dbspace/.app-context.db", "key_filter"),
    ):
        # Only column names/types. Never read accounts, serials, app data, or full databases.
        sql = f"SELECT name,type FROM pragma_table_info('{table}');"
        observe(name, f"sqlite3 -readonly {database} {shlex.quote(sql)}", parse_columns)

    cap_ready = caps is not None and all(
        "e" in caps[path].get(capability, "")
        for path, names in (("/usr/bin/dotnet", ("cap_setgid", "cap_sys_admin")),
                            ("/usr/sbin/sdbd-tarlauncher", ("cap_setgid", "cap_setuid")))
        for capability in names
    )
    if cap_ready and runtime and runtime["net6_or_later_present"] and tar:
        report["archive_prerequisites"] = "observed_not_root_proof"
    return report
