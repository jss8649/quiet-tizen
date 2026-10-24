import asyncio
import base64
import gzip
import hashlib
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tv import check_identity, decode_pull, private_path, PROFILE


class AccessTests(unittest.TestCase):
    def test_target_identity_gate(self):
        check_identity(PROFILE["model"], PROFILE["firmware"])
        with self.assertRaises(ValueError):
            check_identity("ANOTHER_MODEL", PROFILE["firmware"])
        with self.assertRaises(ValueError):
            check_identity(PROFILE["model"], "ANOTHER_FIRMWARE")
        with self.assertRaises(ValueError):
            check_identity(PROFILE["model"], None)

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

    def test_access_probe_applies_profile_transport_limit(self):
        from samsung_tv_root.archive_root import probe
        with patch("samsung_tv_root.archive_root.find_sdb", return_value=Path("sdb")), \
                patch("samsung_tv_root.archive_root.SdbClient") as client, \
                patch("samsung_tv_root.archive_root._check_target", side_effect=RuntimeError("stop")):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                asyncio.run(probe("192.0.2.10", max_appinstall_bytes=400))
        self.assertEqual(client.call_args.kwargs["max_appinstall_bytes"], 400)

    def test_staged_framework_read_checks_source_hash_and_keeps_file_private(self):
        from samsung_tv_root.archive_root import _read_staged_files
        from samsung_tv_root.root_agent import RootAgentFile
        data = b"synthetic framework reference"
        digest = hashlib.sha256(data).hexdigest()
        connection = Mock()
        connection.execute = AsyncMock(side_effect=[
            Mock(exit_code=0, timed_out=False),
            Mock(exit_code=0, timed_out=False, stdout=f"{digest}  original"),
        ])
        connection.read_file = AsyncMock(return_value=RootAgentFile(1, data, digest))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = asyncio.run(_read_staged_files(
                connection, PurePosixPath("/stage"), (("Tizen.dll", "/system/Tizen.dll"),), output, 30))
            self.assertEqual((output / "Tizen.dll").read_bytes(), data)
            self.assertEqual(evidence[0]["sha256"], digest)
            self.assertEqual(connection.read_file.call_args.args[0], "/stage/Tizen.dll")


if __name__ == "__main__":
    unittest.main()
