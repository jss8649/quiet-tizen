import base64
import gzip
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tv import check_identity, decode_pull, private_path, script_command, PROFILE


class AccessTests(unittest.TestCase):
    def test_target_identity_gate(self):
        check_identity(PROFILE["model"], PROFILE["firmware"])
        with self.assertRaises(ValueError):
            check_identity("ANOTHER_MODEL", PROFILE["firmware"])
        with self.assertRaises(ValueError):
            check_identity(PROFILE["model"], "ANOTHER_FIRMWARE")
        with self.assertRaises(ValueError):
            check_identity(PROFILE["model"], None)

    def test_script_reaches_shell_decoded_with_arguments(self):
        script = b'#!/bin/sh\nprintf "%s|" "$@"\n'
        command = script_command(script, ["home-01", "two words", "it's"])
        result = subprocess.run(["sh", "-c", command], check=True, capture_output=True)
        self.assertEqual(result.stdout, b"home-01|two words|it's|")

    def test_transfer_integrity(self):
        payload = b"synthetic contents only" * 100
        digest = hashlib.sha256(payload).hexdigest()
        body = base64.encodebytes(gzip.compress(payload)).decode()
        self.assertEqual(decode_pull(digest + "\n" + body), payload)
        with self.assertRaises(ValueError):
            decode_pull("0" * 64 + "\n" + body)
        with self.assertRaises(Exception):
            decode_pull(digest + "\n" + body[:-12])

    def test_private_outputs_cannot_escape_checkout_private_directory(self):
        with self.assertRaises(ValueError):
            private_path(ROOT / "public-backup.json")
        with self.assertRaises(ValueError):
            private_path(ROOT / ".local/../public-backup.json")

    def test_runtime_fallback_is_narrow(self):
        from samsung_tv_root.archive_root import _check_target, ArchiveRootError
        from unittest.mock import Mock
        client = Mock()
        capabilities = ("/usr/bin/dotnet cap_setgid,cap_sys_admin=ep\n"
                        "/usr/sbin/sdbd-tarlauncher cap_setgid,cap_setuid=ep")
        with patch("samsung_tv_root.archive_root._capture", side_effect=[
            capabilities, ArchiveRootError("Unknown option --list-runtimes"),
            "Microsoft.NETCore.App 6.0.9 [/usr/share/runtime/6.0.9]",
            "--to-command=COMMAND", "synthetic hash",
        ]) as capture:
            self.assertEqual(_check_target(client).runtime, "6.0")
            self.assertIn("System.Private.CoreLib.dll", capture.call_args_list[2].args[1])
        with patch("samsung_tv_root.archive_root._capture", side_effect=[
            capabilities, ArchiveRootError("permission denied"),
        ]):
            with self.assertRaises(ArchiveRootError):
                _check_target(client)


if __name__ == "__main__":
    unittest.main()
