import contextlib
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tv
import plan_cleanup
from device_profiles import load_profile
from diagnostics import CANDIDATE_FILES, collect_diagnostics, capture_text, file_probe_command
from samsung_tv_root.sdb import SdbClient, SdbError, CaptureResult

CANDIDATE_PATH = ROOT / "profiles/qn75qn85ddfxza-2130.0.json"


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(CANDIDATE_PATH)
        self.client = Mock(spec=SdbClient)
        self.client.capture.side_effect = self.capture

    def capture(self, command, **kwargs):
        if command == "uname -srmo":
            output = "Linux 5.4.261 armv7l GNU/Linux"
        elif command.startswith("getcap "):
            output = ("/usr/bin/dotnet cap_setgid,cap_sys_admin=ep\n"
                      "/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=ep")
        elif command == "/usr/bin/dotnet --list-runtimes":
            output = "Microsoft.NETCore.App 6.0.9 [/usr/share/dotnet.tizen/netcoreapp/6.0.9]"
        elif command == "/usr/bin/tar --help":
            output = "--to-command=COMMAND"
        elif command == file_probe_command():
            output = "\n".join(f"{name}|1|1|201:0:644:1024" for name in CANDIDATE_FILES)
        elif "pragma_table_info" in command:
            output = "app_id|TEXT\napp_disable|TEXT"
        else:
            raise AssertionError(f"Unexpected diagnostic command: {command}")
        return CaptureResult(output + "\n[exit:0]\n", 0)

    def collect(self, **kwargs):
        return collect_diagnostics(self.client, self.profile, self.profile["model"],
                                   self.profile["firmware"], **kwargs)

    def test_complete_diagnostics_are_not_root_or_launcher_proof(self):
        report = self.collect(callback_host="192.0.2.20")
        self.assertEqual(report["archive_prerequisites"], "observed_not_root_proof")
        self.assertFalse(report["root_tested"])
        self.assertFalse(report["launcher_tested"])
        self.assertFalse(report["cleanup_tested"])
        self.assertEqual(report["profile"]["support_status"], "preview-validated")
        self.assertTrue(report["identity"]["matches_profile"])
        for call in self.client.capture.call_args_list:
            self.assertEqual(call.kwargs["callback_host"], "192.0.2.20")
        self.client.push.assert_not_called()
        serialized = json.dumps(report)
        self.assertNotIn("192.0.2.20", serialized)

    def test_missing_capability_keeps_other_observations_and_profile_unverified(self):
        def capture(command, **kwargs):
            if command.startswith("getcap "):
                return CaptureResult("/usr/bin/dotnet cap_setgid=ep\n[exit:0]\n", 0)
            return self.capture(command, **kwargs)
        self.client.capture.side_effect = capture
        report = self.collect()
        self.assertEqual(report["archive_prerequisites"], "not_established")
        self.assertEqual(report["checks"]["dotnet_runtime"]["status"], "observed")
        self.assertEqual(report["checks"]["candidate_files"]["status"], "observed")

    def test_failed_sdk_route_stops_further_commands_and_excludes_raw_details(self):
        self.client.require_shell_injection.side_effect = SdbError(
            "package-name shell execution was not confirmed; 192.0.2.20 serial PRIVATE-ID")
        report = self.collect()
        self.client.capture.assert_not_called()
        self.assertIn("sdk_command_route_not_confirmed", json.dumps(report))
        self.assertNotIn("PRIVATE-ID", json.dumps(report))
        self.assertNotIn("192.0.2.20", json.dumps(report))

    def test_unreadable_schema_does_not_erase_runtime_evidence(self):
        def capture(command, **kwargs):
            if "pragma_table_info" in command:
                return CaptureResult("permission denied PRIVATE-ID\n[exit:1]\n", 0)
            return self.capture(command, **kwargs)
        self.client.capture.side_effect = capture
        report = self.collect()
        self.assertEqual(report["checks"]["package_registry_columns"]["status"], "incomplete")
        self.assertEqual(report["checks"]["dotnet_runtime"]["value"]["versions"], ["6.0.9"])
        self.assertNotIn("PRIVATE-ID", json.dumps(report))

    def test_runtime_fallback_requires_exact_unsupported_option_error(self):
        for error, should_fallback in (("Unknown option --list-runtimes", True),
                                       ("permission denied", False)):
            with self.subTest(error=error):
                def capture(command, **kwargs):
                    if command == "/usr/bin/dotnet --list-runtimes":
                        return CaptureResult(error + "\n[exit:1]\n", 0)
                    if command.startswith("d=$(readlink"):
                        return CaptureResult("Microsoft.NETCore.App 6.0.9 [/usr/share/runtime/6.0.9]\n[exit:0]\n", 0)
                    return self.capture(command, **kwargs)
                self.client.capture.reset_mock()
                self.client.capture.side_effect = capture
                report = self.collect()
                fallback_calls = [c for c in self.client.capture.call_args_list
                                  if c.args[0].startswith("d=$(readlink")]
                self.assertEqual(bool(fallback_calls), should_fallback)
                self.assertEqual(report["checks"]["dotnet_runtime"]["status"],
                                 "observed" if should_fallback else "incomplete")

    def test_capture_requires_final_success_marker(self):
        self.client.capture.side_effect = None
        self.client.capture.return_value = CaptureResult("data\n[exit:0]\ntruncated", 0)
        with self.assertRaises(RuntimeError):
            capture_text(self.client, "uname -srmo")

    def test_candidate_operations_stop_before_network_or_staging(self):
        operations = (("exec", "--command", "id"), ("push", "missing.tar", "package.tar"),
                      ("pull", "/example", ".local/example"))
        for operation in operations:
            with self.subTest(operation=operation), patch("tv.find_sdb") as find, \
                    patch("tv.SdbClient") as client, patch("tv.probe") as probe:
                with self.assertRaisesRegex(ValueError, "preview-validated"):
                    tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                             "--firmware", self.profile["firmware"], *operation])
                find.assert_not_called()
                client.assert_not_called()
                probe.assert_not_called()

    def test_candidate_root_check_forwards_conservative_transport_limit(self):
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "commands": [{"stdout": "uid=0(root)\n", "stderr": "", "exit_code": 0,
                                "timed_out": False}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch("tv.ROOT", Path(directory)), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                tv.main(["--host", "192.0.2.10", "--callback-host", "192.0.2.20",
                         "--profile", str(CANDIDATE_PATH), "--firmware", self.profile["firmware"],
                         "root-check"])
            self.assertEqual(probe.call_args.kwargs["max_appinstall_bytes"], 400)
            self.assertEqual(probe.call_args.kwargs["commands"], ("id",))

    def test_fixed_inventory_is_private_and_still_requires_clean_root_exit(self):
        from root_inventory import ROOT_INVENTORY_COMMANDS
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "commands": [{"stdout": "PRIVATE-APP", "stderr": "", "exit_code": 0,
                                "timed_out": False} for _ in ROOT_INVENTORY_COMMANDS]}
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch("tv.ROOT", Path(directory)), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(output):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "inventory"])
            self.assertEqual(probe.call_args.kwargs["commands"],
                             tuple(command for _, command in ROOT_INVENTORY_COMMANDS))
            self.assertNotIn("PRIVATE-APP", output.getvalue())
            self.assertEqual(len(list((Path(directory) / ".local/sessions").glob("*.json"))), 1)

    def test_framework_pull_uses_only_fixed_paths_and_private_destination(self):
        from root_inventory import FRAMEWORK_FILES
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "private_files": [{"name": name, "size_bytes": 1, "sha256": "0" * 64}
                                    for name in FRAMEWORK_FILES]}
        with tempfile.TemporaryDirectory() as directory:
            client = Mock(spec=SdbClient)
            with patch("tv.ROOT", Path(directory)), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient", return_value=client), \
                    patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "framework-pull"])
            client.pull.assert_not_called()
            self.assertEqual(probe.call_args.kwargs["read_files"], tuple(FRAMEWORK_FILES.items()))
            self.assertEqual(probe.call_args.kwargs["output_dir"], Path(directory) / ".local/tv-framework")

    def test_source_probe_stages_only_built_probe_and_keeps_output_private(self):
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "commands": [{"stdout": "PRIVATE_SOURCE", "stderr": "", "exit_code": 0,
                                "timed_out": False}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            built = root / ".local/build/Probe/Probe.dll"
            built.parent.mkdir(parents=True)
            built.write_bytes(b"synthetic probe")
            output = io.StringIO()
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(output):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "source-probe"])
            self.assertEqual(probe.call_args.kwargs["staged_files"], (("Probe.dll", built),))
            self.assertEqual(probe.call_args.kwargs["run_staged"], ("Probe.dll",))
            self.assertNotIn("PRIVATE_SOURCE", output.getvalue())

    def test_snapshot_uses_fixed_script_and_rejects_bad_name_before_network(self):
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "commands": [{"stdout": "saved", "stderr": "", "exit_code": 0,
                                "timed_out": False}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "recipes").mkdir()
            (root / "recipes/snapshot.sh").write_bytes(b"set -eu\r\necho fixed snapshot\r\n")
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")) as find, \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                for name in ("../escape", "bad name", "bad;id"):
                    with self.subTest(name=name), self.assertRaisesRegex(ValueError, "phase name"):
                        tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                                 "--firmware", self.profile["firmware"], "snapshot", name])
                find.assert_not_called()
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "snapshot", "home-test"])
            command = probe.call_args.kwargs["commands"][0]
            self.assertIn(base64.b64encode(b"set -eu\necho fixed snapshot\n").decode(), command)
            self.assertTrue(command.endswith("base64 -d | /bin/sh -s -- home-test"))

    def test_backup_pull_is_fixed_to_selected_phase_and_refuses_overwrite(self):
        from root_inventory import BACKUP_FILES
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "private_files": [{"name": name} for name in BACKUP_FILES]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")) as find, \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "backup-pull", "home-test"])
                self.assertEqual(probe.call_args.kwargs["read_files"], tuple(
                    (local, f"/opt/usr/share/quiet-tizen-backups/home-test/{remote}")
                    for local, remote in BACKUP_FILES.items()))
                self.assertEqual(probe.call_args.kwargs["output_dir"],
                                 root / ".local/backups/home-test")
                (root / ".local/backups/home-test/package-registry.db").write_bytes(b"keep")
                with self.assertRaisesRegex(ValueError, "already exists"):
                    tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                             "--firmware", self.profile["firmware"], "backup-pull", "home-test"])
            self.assertEqual(probe.call_count, 1)

    def test_preview_install_requires_private_backup_and_stages_fixed_scripts(self):
        from root_inventory import BACKUP_FILES
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "commands": [{"stdout": "preview requested", "stderr": "", "exit_code": 0,
                                "timed_out": False}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("tv.ROOT", root), patch("tv.find_sdb") as find:
                with self.assertRaisesRegex(ValueError, "backup files"):
                    tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                             "--firmware", self.profile["firmware"],
                             "preview-install", "home-test"])
                find.assert_not_called()
            backup = root / ".local/backups/home-test"
            backup.mkdir(parents=True)
            for name in BACKUP_FILES:
                (backup / name).write_bytes(b"backup")
            package = root / ".local/package"
            required = ("BixbyPromotion.dll", "Probe.dll", "quiet-home/apps.json",
                        "quiet-home/home-layout.json")
            for name in required:
                destination = package / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(name.encode())
            archive = root / ".local/package-preview.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                for name in required:
                    stream.add(package / name, arcname="./" + name)
            recipes = root / "recipes"
            recipes.mkdir()
            (recipes / "install-launcher.sh").write_bytes(b"set -eu\r\necho install\r\n")
            (recipes / "restore-preview.sh").write_bytes(b"set -eu\r\necho restore\r\n")
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"],
                         "preview-install", "home-test"])
            staged = probe.call_args.kwargs["staged_files"]
            self.assertEqual([name for name, _ in staged],
                             ["package.tar.gz", "install-launcher.sh", "restore-preview.sh"])
            self.assertEqual(staged[1][1], b"set -eu\necho install\n")
            self.assertEqual(staged[2][1], b"set -eu\necho restore\n")
            self.assertEqual(probe.call_args.kwargs["run_staged_shell"],
                             ("install-launcher.sh", "home-test"))

    def test_artwork_install_refuses_missing_or_corrupt_backup_before_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("tv.ROOT", root), patch("tv.find_sdb") as find:
                args = ["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                        "--firmware", self.profile["firmware"], "artwork-install", "art-test"]
                with self.assertRaisesRegex(ValueError, "Copy the artwork catalog backup"):
                    tv.main(args)
                backup = root / ".local/backups/art-test"
                backup.mkdir(parents=True)
                (backup / "apps-before.json").write_bytes(b"original catalog")
                (backup / "apps-before.sha256").write_text("0" * 64 + "  catalog\n")
                (backup / "launcher-assembly.sha256").write_text("0" * 64 + "  launcher\n")
                with self.assertRaisesRegex(ValueError, "digest mismatch"):
                    tv.main(args)
                find.assert_not_called()

    def test_artwork_inputs_require_selected_apps_and_untampered_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "launcher/assets"
            assets.mkdir(parents=True)
            catalog, receipts = [], {}
            for name, app_id, asset, _ in tv.ARTWORK_ASSETS:
                path = assets / asset
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(name.encode())
                catalog.append({"Name": name, "Id": app_id, "Asset": asset})
                receipts[name] = {"asset_sha256": hashlib.sha256(name.encode()).hexdigest()}
            catalog.append({"Name": "Get more apps"})
            (assets / "apps.local.json").write_text(json.dumps(catalog))
            (root / ".local").mkdir()
            (root / ".local/artwork-receipts.json").write_text(json.dumps(receipts))
            with patch("tv.ROOT", root):
                self.assertEqual(len(tv.verify_artwork_inputs()), 4)
                (assets / "app-icons/netflix.svg").write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    tv.verify_artwork_inputs()

    def test_preview_launch_uses_only_fixed_launcher_command(self):
        from root_inventory import BACKUP_FILES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / ".local/backups/home-test"
            backup.mkdir(parents=True)
            for name in BACKUP_FILES:
                (backup / name).write_bytes(b"backup")
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient") as client_class, \
                    patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe") as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                client_class.return_value.capture.return_value.output = "launched\n[exit:0]\n"
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"],
                         "preview-launch", "home-test"])
            client_class.return_value.capture.assert_called_once_with(
                "app_launcher -u 5001 -s com.samsung.tv.bixby-promotion",
                callback_host=None, timeout=15)
            probe.assert_not_called()

    def test_home_routing_stages_fixed_inverse_before_mutation(self):
        from root_inventory import BACKUP_FILES
        result = {"uid": 0, "euid": 0, "system_files_unchanged": True,
                  "staging_cleaned": True,
                  "commands": [{"stdout": "route checked", "stderr": "", "exit_code": 0,
                                "timed_out": False}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / ".local/backups/home-test"
            backup.mkdir(parents=True)
            for name in BACKUP_FILES:
                (backup / name).write_bytes(b"backup")
            recipes = root / "recipes"
            recipes.mkdir()
            (recipes / "route-home.sh").write_bytes(b"set -eu\r\necho route\r\n")
            (recipes / "restore-home-route.sh").write_bytes(b"set -eu\r\necho restore\r\n")
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient"), patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.probe", new_callable=AsyncMock, return_value=result) as probe, \
                    contextlib.redirect_stdout(io.StringIO()):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "home-route", "home-test"])
                self.assertEqual(probe.call_args.kwargs["staged_files"],
                                 (("route-home.sh", b"set -eu\necho route\n"),
                                  ("restore-home-route.sh", b"set -eu\necho restore\n")))
                self.assertEqual(probe.call_args.kwargs["run_staged_shell"],
                                 ("route-home.sh", "home-test"))
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "home-restore", "home-test"])
                self.assertEqual(probe.call_args.kwargs["staged_files"],
                                 (("restore-home-route.sh", b"set -eu\necho restore\n"),))
                self.assertEqual(probe.call_args.kwargs["run_staged_shell"],
                                 ("restore-home-route.sh", "home-test"))

    def test_explicit_doctor_identity_mismatch_stops_before_diagnostic_commands(self):
        with patch("tv.find_sdb", return_value=Path("sdb")), patch("tv.SdbClient"), \
                patch("tv.observed_model", return_value="DIFFERENT_MODEL"), \
                patch("tv.collect_diagnostics") as collect, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "does not match"):
                tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                         "--firmware", self.profile["firmware"], "doctor"])
            collect.assert_not_called()

    def test_candidate_cli_saves_report_and_uses_profile_transport_limit(self):
        report = self.collect()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / ".local/report.json"
            with patch("tv.ROOT", root), patch("tv.find_sdb", return_value=Path("sdb")), \
                    patch("tv.SdbClient") as client, \
                    patch("tv.observed_model", return_value=self.profile["model"]), \
                    patch("tv.collect_diagnostics", return_value=report) as collect, \
                    contextlib.redirect_stdout(io.StringIO()):
                result = tv.main(["--host", "192.0.2.10", "--profile", str(CANDIDATE_PATH),
                                  "--firmware", self.profile["firmware"],
                                  "--callback-host", "192.0.2.20", "doctor", "--report", str(output)])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertEqual(client.call_args.kwargs["max_appinstall_bytes"], 400)
            self.assertEqual(collect.call_args.args[-1], "192.0.2.20")

    def test_report_path_outside_private_directory_rejected_before_connection(self):
        with patch("tv.find_sdb") as find:
            with self.assertRaisesRegex(ValueError, "inside this checkout"):
                tv.main(["--host", "192.0.2.10", "doctor", "--report", str(ROOT / "public.json")])
            find.assert_not_called()

    def test_cleanup_candidate_rejected_before_snapshot_read_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory, patch("plan_cleanup.read_rows") as read:
            output = Path(directory) / "never-created"
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                plan_cleanup.main(["--profile", str(CANDIDATE_PATH), "--snapshot", "absent.db",
                                   "--groups", "advertising", "--output", str(output)])
            read.assert_not_called()
            self.assertFalse(output.exists())


class TransportLimitTests(unittest.TestCase):
    def test_default_is_preserved_and_candidate_limit_is_enforced(self):
        default = SdbClient(Path("sdb"), "192.0.2.10")
        candidate = SdbClient(Path("sdb"), "192.0.2.10", max_appinstall_bytes=400)
        command = "true " + "x" * 220
        with patch.object(default, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            default.inject(command)
            run.assert_called_once()
        with patch.object(candidate, "run") as run:
            with self.assertRaisesRegex(SdbError, "400"):
                candidate.inject(command)
            run.assert_not_called()

    def test_capture_stages_long_commands_for_the_candidate_limit(self):
        client = SdbClient(Path("sdb"), "192.0.2.10", max_appinstall_bytes=400)
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.recv.side_effect = [b"ok\n[exit:0]\n", b""]
        listener = Mock()
        listener.__enter__ = Mock(return_value=listener)
        listener.__exit__ = Mock(return_value=False)
        listener.getsockname.return_value = ("192.0.2.20", 12345)
        listener.accept.return_value = (connection, ("192.0.2.10", 12345))
        with patch("samsung_tv_root.sdb.socket.socket", return_value=listener), \
                patch.object(client, "_stage_script", return_value="sh /tmp/probe.sh") as stage, \
                patch.object(client, "inject", return_value=subprocess.CompletedProcess([], 0)) as inject:
            result = client.capture("true " + "x" * 220, callback_host="192.0.2.20")
        stage.assert_called_once()
        self.assertIn("/dev/tcp/192.0.2.20/12345", stage.call_args.args[0])
        self.assertEqual(inject.call_args.args[0], "sh /tmp/probe.sh")
        self.assertEqual(result.output, "ok\n[exit:0]\n")

    def test_invalid_transport_limits_are_rejected(self):
        for limit in (0, 299, 511, True, "400"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                SdbClient(Path("sdb"), "192.0.2.10", max_appinstall_bytes=limit)


if __name__ == "__main__":
    unittest.main()
