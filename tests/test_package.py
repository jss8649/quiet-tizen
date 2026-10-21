import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fetch_artwork import convert, destination


class PackageTests(unittest.TestCase):
    def test_catalog_assets_exist_and_ids_are_unique(self):
        catalog = json.loads((ROOT / "launcher/assets/apps.json").read_text())
        self.assertEqual(len({a["Id"] for a in catalog}), len(catalog))
        for entry in catalog:
            asset = entry["Asset"]
            self.assertNotIn("..", asset)
            self.assertTrue((ROOT / "launcher/assets" / asset).is_file(), asset)
        self.assertEqual(sum(bool(a.get("Utility")) for a in catalog), 1)

    def test_profiles_have_no_duplicate_app_ids_or_essential_containers(self):
        for path in sorted((ROOT / "profiles").glob("*.json")):
            with self.subTest(profile=path.name):
                profile = json.loads(path.read_text())
                ids = [app for group in profile.get("groups", {}).values() for app in group["app_ids"]]
                self.assertEqual(len(ids), len(set(ids)))
                essentials = ["org.tizen.menu", "com.samsung.tv.quicklaunch"]
                if "launcher" in profile:
                    # Quiet Home replaces this container's entry assembly; never a cleanup target.
                    self.assertRegex(profile["launcher"]["app_id"], r"^[A-Za-z0-9_.-]+$")
                    self.assertRegex(profile["launcher"]["dll"], r"^[A-Za-z0-9_.-]+\.dll$")
                    essentials.append(profile["launcher"]["app_id"])
                for essential in essentials:
                    self.assertNotIn(essential, ids)

    def test_shell_syntax(self):
        for path in (ROOT / "recipes").glob("*.sh"):
            subprocess.run(["sh", "-n", str(path)], check=True, capture_output=True)

    def test_artwork_destinations_and_active_svg_rejected(self):
        with self.assertRaises(ValueError):
            destination("../elsewhere.svg")
        entry = {"name": "Example", "asset": "app-icons/example.svg",
                 "catalog": {"Width": 100, "Height": 50}}
        valid = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><path d="M0 0"/></svg>'
        self.assertEqual(ET.fromstring(convert(valid, entry)).get("width"), "100")
        for data in [
            b'<svg><script>alert(1)</script></svg>',
            b'<svg><image href="https://example.com/image.png"/></svg>',
            b'<svg onload="alert(1)"/>',
            b'<!DOCTYPE svg [<!ENTITY x "x">]><svg/>',
        ]:
            with self.assertRaises(ValueError):
                convert(data, entry)

    def test_relative_document_links_resolve(self):
        for doc in [ROOT / "README.md", ROOT / "NOTICE.md", *sorted((ROOT / "docs").glob("*.md"))]:
            for link in re.findall(r"\[[^\]]*\]\(([^ )]+)(?: [^)]*)?\)", doc.read_text()):
                if "://" in link or link.startswith("#"):
                    continue
                path = link.split("#", 1)[0]
                self.assertTrue((doc.parent / path).exists(), f"{doc.name}: {link}")


if __name__ == "__main__":
    unittest.main()
