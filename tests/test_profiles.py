import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from device_profiles import (
    DEFAULT_PROFILE_PATH, check_profile_identity, load_profile, require_operation,
)


class DeviceProfileTests(unittest.TestCase):
    def setUp(self):
        self.original = load_profile()
        self.candidate = load_profile(ROOT / "profiles/qn75qn85ddfxza-2130.0.json")

    def test_original_profile_retains_existing_operations(self):
        self.assertEqual(DEFAULT_PROFILE_PATH.name, "un75u8000ffxza-1300.9.json")
        self.assertEqual(self.original["support_status"], "case-study")
        check_profile_identity(self.original, "UN75U8000FFXZA", "T-KSU2EFAKUC-0090-1300.9")
        for operation in ("doctor", "root-check", "inventory", "framework-pull", "source-probe",
                          "snapshot", "backup-pull", "push", "pull", "exec", "cleanup"):
            with self.subTest(operation=operation):
                require_operation(self.original, operation)

    def test_exact_candidate_identity_only_enables_fixed_access_inventory(self):
        check_profile_identity(self.candidate, "QN75QN85DDFXZA", "T-PTMDAKUC-0090-2130.0")
        require_operation(self.candidate, "doctor")
        require_operation(self.candidate, "root-check")
        require_operation(self.candidate, "inventory")
        for operation in ("artwork-snapshot", "artwork-backup-pull", "artwork-install", "artwork-restore"):
            require_operation(self.candidate, operation)
            with self.assertRaisesRegex(ValueError, "case-study"):
                require_operation(self.original, operation)
        require_operation(self.candidate, "framework-pull")
        require_operation(self.candidate, "source-probe")
        require_operation(self.candidate, "snapshot")
        require_operation(self.candidate, "backup-pull")
        require_operation(self.candidate, "preview-install")
        require_operation(self.candidate, "preview-launch")
        require_operation(self.candidate, "preview-restore")
        require_operation(self.candidate, "home-route")
        require_operation(self.candidate, "home-restore")
        for operation in ("push", "pull", "exec", "cleanup"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "preview-validated"):
                    require_operation(self.candidate, operation)

    def test_identity_does_not_accept_related_models_or_normalize_firmware(self):
        for model, firmware in (
            ("QN55S90DAFXZA", self.candidate["firmware"]),
            ("QN75QN85D", self.candidate["firmware"]),
            (self.candidate["model"], "2130.0"),
            (self.candidate["model"], "T-PTMDAKUC-0090-2130.0 "),
            (self.candidate["model"], None),
        ):
            with self.subTest(model=model, firmware=firmware):
                with self.assertRaises(ValueError):
                    check_profile_identity(self.candidate, model, firmware)

    def test_candidate_records_preflight_without_mutation_targets(self):
        for field in ("was_cache",):
            with self.subTest(field=field):
                self.assertIsNone(self.candidate[field])
        self.assertEqual(self.candidate["os"], "Tizen 9.0.0")
        self.assertEqual(self.candidate["kernel"], "Linux 5.4.249 armv7l")
        self.assertEqual(self.candidate["runtime"], "6.0.9")
        self.assertEqual(self.candidate["registry"], "/opt/dbspace/.pkgmgr_parser.db")
        self.assertEqual(self.candidate["temporary_root_evidence"]["authenticated_uid_euid"], [0, 0])
        self.assertEqual(self.candidate["groups"], {})
        for field in ("stop_markers", "runtime_only_masks", "preferences"):
            self.assertEqual(self.candidate[field], [])

    def test_invalid_status_cannot_enable_operations_even_after_load(self):
        for status in (None, "", "supported", "CASE-STUDY", True, []):
            profile = copy.deepcopy(self.original)
            profile["support_status"] = status
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "support_status"):
                    require_operation(profile, "doctor")
                with self.assertRaisesRegex(ValueError, "support_status"):
                    require_operation(profile, "exec")
        profile = copy.deepcopy(self.original)
        del profile["support_status"]
        with self.assertRaisesRegex(ValueError, "support_status"):
            require_operation(profile, "doctor")

    def test_unknown_operations_fail_for_both_profiles(self):
        for profile in (self.original, self.candidate):
            for operation in ("install", "Doctor", "", None, []):
                with self.subTest(model=profile["model"], operation=operation):
                    with self.assertRaisesRegex(ValueError, "Unknown profile operation"):
                        require_operation(profile, operation)

    def test_loader_rejects_malformed_metadata(self):
        invalid = [[], None]
        for field, values in (
            ("profile_version", (None, True, 1.0, "1", 2)),
            ("model", (None, "", " QN75QN85DDFXZA", "MODEL\nOTHER")),
            ("firmware", (None, "", " ", "FW\x00OTHER")),
            ("support_status", (None, "", "verified", [])),
        ):
            for value in values:
                profile = copy.deepcopy(self.candidate)
                profile[field] = value
                invalid.append(profile)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            for profile in invalid:
                with self.subTest(profile=profile):
                    path.write_text(json.dumps(profile), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_profile(path)

    def test_conservative_transport_setting_cannot_raise_vendor_limit(self):
        self.assertEqual(self.candidate["diagnostic_transport"]["max_inline_bytes"], 400)
        for value in (0, 511, True, "400", None):
            profile = copy.deepcopy(self.candidate)
            profile["diagnostic_transport"]["max_inline_bytes"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "max_inline_bytes"):
                    require_operation(profile, "doctor")


if __name__ == "__main__":
    unittest.main()
