"""Exercise Linux-bound file bytes and SQLite lifetimes on the host."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "vendor"))
import plan_cleanup
from samsung_tv_root import archive_root
from samsung_tv_root.sdb import SdbClient


class WindowsPortabilityTests(unittest.TestCase):
    def test_snapshot_connection_closed_on_success_and_error(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "snapshot.db"
            with sqlite3.connect(database) as writer:
                writer.execute("CREATE TABLE package_app_info (app_id TEXT, "
                               "app_disable TEXT, app_onboot TEXT, app_autorestart TEXT)")
                writer.execute("INSERT INTO package_app_info VALUES ('example.app', 'false', 'true', 'false')")
            writer.close()
            connect = sqlite3.connect
            for app_id in ("example.app", "missing.app"):
                connections = []
                def tracked_connect(*args, **kwargs):
                    connection = connect(*args, **kwargs)
                    connections.append(connection)
                    return connection
                with patch.object(plan_cleanup.sqlite3, "connect", side_effect=tracked_connect):
                    if app_id == "missing.app":
                        with self.assertRaises(ValueError):
                            plan_cleanup.read_rows(database, [app_id])
                    else:
                        self.assertEqual(len(plan_cleanup.read_rows(database, [app_id])), 1)
                self.assertEqual(len(connections), 1)
                with self.assertRaises(sqlite3.ProgrammingError):
                    connections[0].execute("SELECT 1")

    def test_generated_cleanup_files_have_lf_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile.json"
            profile.write_text(json.dumps({"model": "test", "firmware": "test",
                "groups": {"optional": {"app_ids": ["example.app"]}}}), encoding="utf-8")
            output = root / ".local" / "plan"
            argv = ["plan_cleanup", "--snapshot", str(root / "synthetic.db"),
                    "--profile", str(profile), "--groups", "optional", "--output", str(output)]
            rows = [("example.app", ("false", "true", "false"))]
            with patch.object(plan_cleanup, "ROOT", root), patch.object(sys, "argv", argv), \
                    patch.object(plan_cleanup, "read_rows", return_value=rows):
                plan_cleanup.main()
            for action in ("apply", "restore"):
                for suffix in ("sql", "sh"):
                    data = (output / f"{action}.{suffix}").read_bytes()
                    self.assertIn(b"\n", data)
                    self.assertNotIn(b"\r", data)

    def test_staged_capture_script_has_lf_bytes(self):
        client = Mock()
        captured = []
        client.push.side_effect = lambda local, remote: captured.append(local.read_bytes())
        SdbClient._stage_script(client, "printf 'first\\nsecond\\n'")
        self.assertEqual(len(captured), 1)
        self.assertNotIn(b"\r", captured[0])
        self.assertTrue(captured[0].endswith(b"printf 'first\\nsecond\\n'\n"))

    def test_archive_passwd_has_lf_bytes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(archive_root, "_openssl"):
            root = Path(directory)
            archive_root._prepare_artifacts(root, "6.0", "synthetic-test", "192.0.2.1", 1234, b"x" * 32)
            self.assertEqual((root / "passwd").read_bytes(),
                             b"owner:x:0:0:owner:/home/owner:/bin/sh\n")


if __name__ == "__main__":
    unittest.main()
