"""Exact device identities and evidence-based limits for Quiet Tizen profiles."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = ROOT / "profiles/un75u8000ffxza-1300.9.json"
SUPPORT_STATUSES = frozenset(("case-study", "inventory-only", "access-evaluation", "access-validated",
                              "backup-validated", "preview-validated"))
OPERATIONS = frozenset(("doctor", "root-check", "inventory", "framework-pull", "source-probe",
                        "snapshot", "backup-pull", "preview-install", "preview-launch", "preview-restore",
                        "home-route", "home-restore", "artwork-snapshot", "artwork-backup-pull",
                        "artwork-install", "artwork-restore",
                        "push", "pull", "exec", "cleanup"))
QN85DD_ARTWORK_OPERATIONS = frozenset(("artwork-snapshot", "artwork-backup-pull",
                                        "artwork-install", "artwork-restore"))


def _validate_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("Device profile must be a JSON object.")
    version = profile.get("profile_version")
    if type(version) is not int or version != 1:
        raise ValueError("Unsupported device profile_version; expected integer 1.")
    for field in ("model", "firmware"):
        value = profile.get(field)
        if (not isinstance(value, str) or not value or value != value.strip()
                or any(ord(char) < 32 for char in value)):
            raise ValueError(f"Profile {field} must be a nonempty, exact single-line string.")
    status = profile.get("support_status")
    if not isinstance(status, str) or status not in SUPPORT_STATUSES:
        raise ValueError("Unknown profile support_status.")
    transport = profile.get("diagnostic_transport")
    if transport is not None:
        if not isinstance(transport, dict):
            raise ValueError("Profile diagnostic_transport must be an object.")
        limit = transport.get("max_inline_bytes")
        if type(limit) is not int or not 300 <= limit <= 510:
            raise ValueError("Diagnostic max_inline_bytes must be an integer from 300 to 510.")
    return profile


def load_profile(path=DEFAULT_PROFILE_PATH):
    """Load a profile without inferring support from its model or firmware name."""
    return _validate_profile(json.loads(Path(path).read_text(encoding="utf-8")))


def check_profile_identity(profile, model, firmware):
    """Require the observed model and operator-read firmware to match exactly."""
    _validate_profile(profile)
    if model != profile["model"]:
        raise ValueError(
            f"Observed model {model!r} does not match profile model {profile['model']!r}. "
            "Stop and investigate the correct device profile."
        )
    if firmware != profile["firmware"]:
        raise ValueError(
            "Supply --firmware with the exact version read from About This TV. "
            f"This profile requires {profile['firmware']!r}; do not guess or substitute it."
        )


def require_operation(profile, operation):
    """Permit only operations established by this profile's evidence stage."""
    _validate_profile(profile)
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError(f"Unknown profile operation: {operation!r}.")
    status = profile["support_status"]
    allowed = {
        "inventory-only": {"doctor"},
        "access-evaluation": {"doctor", "root-check"},
        "access-validated": {"doctor", "root-check", "inventory", "framework-pull", "source-probe",
                             "snapshot", "backup-pull"},
        "backup-validated": {"doctor", "root-check", "inventory", "framework-pull", "source-probe",
                             "snapshot", "backup-pull", "preview-install", "preview-launch", "preview-restore"},
        "preview-validated": {"doctor", "root-check", "inventory", "framework-pull", "source-probe",
                              "snapshot", "backup-pull", "preview-install", "preview-launch", "preview-restore",
                              "home-route", "home-restore", "artwork-snapshot", "artwork-backup-pull",
                              "artwork-install", "artwork-restore"},
        "case-study": OPERATIONS - QN85DD_ARTWORK_OPERATIONS,
    }[status]
    if operation not in allowed:
        raise ValueError(
            f"Profile {profile['model']} / {profile['firmware']} is {status}. "
            f"Operation {operation!r} requires a supported evaluation stage. "
            "Inventory and access checks do not authorize transfers, arbitrary execution, or cleanup."
        )
