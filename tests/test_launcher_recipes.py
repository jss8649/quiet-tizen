import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "example.quiet-home-host"


class LauncherRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.conn = sqlite3.connect(self.directory / "live.db")
        self.conn.executescript(f"""
          CREATE TABLE package_app_info(app_id TEXT, app_disable TEXT, app_onboot TEXT,
                                        app_autorestart TEXT, other TEXT);
          INSERT INTO package_app_info VALUES
            ('{CONTAINER}','true','true','true','keep'),
            ('unrelated.app','true','true','true','keep');
        """)
        with sqlite3.connect(self.directory / ".pkgmgr_parser.db") as snapshot:
            self.conn.backup(snapshot)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def sql(self, recipe):
        script = (ROOT / "recipes" / recipe).read_text()
        sql = re.search(r"<<SQL\n(.*?)\nSQL", script, re.S).group(1)
        sql = sql.replace("$D", str(self.directory)).replace("$container", CONTAINER)
        self.assertNotIn("$", sql)  # every shell variable in the SQL is accounted for
        return sql

    def rows(self):
        return self.conn.execute("SELECT * FROM package_app_info ORDER BY app_id").fetchall()

    def test_install_enables_only_the_container_and_restore_returns_its_flags(self):
        self.conn.executescript(self.sql("install-launcher.sh"))
        self.assertEqual(self.rows(), [(CONTAINER, "false", "false", "false", "keep"),
                                       ("unrelated.app", "true", "true", "true", "keep")])
        self.conn.execute("UPDATE package_app_info SET other='updated'")
        self.conn.commit()
        self.conn.executescript(self.sql("restore-launcher.sh"))
        self.assertEqual(self.rows(), [(CONTAINER, "true", "true", "true", "updated"),
                                       ("unrelated.app", "true", "true", "true", "updated")])

    def test_missing_container_refuses_install(self):
        self.conn.execute(f"DELETE FROM package_app_info WHERE app_id='{CONTAINER}'")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.executescript(self.sql("install-launcher.sh"))
        self.conn.rollback()
        self.assertEqual(self.rows(), [("unrelated.app", "true", "true", "true", "keep")])

    def preflight_passes(self, recipe, first_change):
        script = (ROOT / "recipes" / recipe).read_text()
        block = re.search(r"^for db in .*?^done$", script, re.S | re.M)
        self.assertLess(block.start(), script.index(first_change))  # nothing is changed before it
        check = block.group(0).replace("/opt/dbspace/.pkgmgr_parser.db", str(self.directory / "live.db"))
        check = check.replace("$container", CONTAINER)
        return subprocess.run(["sh", "-euc", check], env={"D": str(self.directory), "PATH": "/usr/bin:/bin"},
                              capture_output=True).returncode == 0

    def test_container_row_is_checked_before_any_change(self):
        for recipe, first_change in [("install-launcher.sh", 'mkdir "$S/unpacked"'),
                                     ("restore-launcher.sh", '"$D/Probe.dll" set-home')]:
            self.assertTrue(self.preflight_passes(recipe, first_change))
            self.conn.execute(f"INSERT INTO package_app_info (app_id) VALUES ('{CONTAINER}')")
            self.conn.commit()
            self.assertFalse(self.preflight_passes(recipe, first_change))  # duplicate row
            self.conn.execute(f"DELETE FROM package_app_info WHERE app_id='{CONTAINER}'")
            self.conn.commit()
            self.assertFalse(self.preflight_passes(recipe, first_change))  # missing row
            self.conn.execute(f"INSERT INTO package_app_info VALUES ('{CONTAINER}','true','true','true','keep')")
            self.conn.commit()

if __name__ == "__main__":
    unittest.main()
