import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from plan_cleanup import read_rows, make_sql


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "synthetic.db"
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript("""
            CREATE TABLE package_app_info (
              app_id TEXT, app_disable TEXT, app_onboot TEXT, app_autorestart TEXT,
              unrelated TEXT
            );
            INSERT INTO package_app_info VALUES ('example.optional','false','true','false','keep');
            INSERT INTO package_app_info VALUES ('example.core','false','true','true','keep');
        """)
        self.rows = read_rows(self.path, ["example.optional"])

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_round_trip_preserves_unrelated_changes(self):
        self.conn.executescript(make_sql(self.rows))
        self.assertEqual(self.conn.execute("SELECT app_disable,app_onboot,app_autorestart "
                         "FROM package_app_info WHERE app_id='example.optional'").fetchone(),
                         ("true", "false", "false"))
        self.conn.execute("UPDATE package_app_info SET unrelated='new app metadata'")
        self.conn.execute("UPDATE package_app_info SET app_onboot='false' WHERE app_id='example.core'")
        self.conn.commit()
        self.conn.executescript(make_sql(self.rows, restore=True))
        self.assertEqual(self.conn.execute("SELECT app_disable,app_onboot,app_autorestart,unrelated "
                         "FROM package_app_info WHERE app_id='example.optional'").fetchone(),
                         ("false", "true", "false", "new app metadata"))
        self.assertEqual(self.conn.execute("SELECT app_onboot FROM package_app_info "
                         "WHERE app_id='example.core'").fetchone(), ("false",))

    def test_apply_refuses_target_field_drift(self):
        self.conn.execute("UPDATE package_app_info SET app_autorestart='true' WHERE app_id='example.optional'")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.executescript(make_sql(self.rows))
        self.conn.rollback()
        self.assertEqual(self.conn.execute("SELECT app_disable FROM package_app_info "
                         "WHERE app_id='example.optional'").fetchone(), ("false",))

    def test_restore_refuses_target_field_drift(self):
        self.conn.executescript(make_sql(self.rows))
        self.conn.execute("UPDATE package_app_info SET app_onboot='true' WHERE app_id='example.optional'")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.executescript(make_sql(self.rows, restore=True))
        self.conn.rollback()

    def test_all_guards_run_before_any_update(self):
        rows = read_rows(self.path, ["example.optional", "example.core"])
        self.conn.execute("DELETE FROM package_app_info WHERE app_id='example.core'")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.executescript(make_sql(rows))
        self.conn.rollback()
        self.assertEqual(self.conn.execute("SELECT app_disable FROM package_app_info").fetchone(), ("false",))

    def test_apply_and_restore_refuse_new_duplicate_with_different_flags(self):
        for restore in (False, True):
            with self.subTest(restore=restore):
                if restore:
                    self.conn.executescript(make_sql(self.rows))
                self.conn.execute("INSERT INTO package_app_info VALUES "
                                  "('example.optional','false','false','true','new duplicate')")
                self.conn.commit()
                before = self.conn.execute("SELECT * FROM package_app_info ORDER BY rowid").fetchall()
                with self.assertRaises(sqlite3.IntegrityError):
                    self.conn.executescript(make_sql(self.rows, restore=restore))
                self.conn.rollback()
                self.assertEqual(self.conn.execute("SELECT * FROM package_app_info ORDER BY rowid").fetchall(),
                                 before)
                self.conn.execute("DELETE FROM package_app_info WHERE unrelated='new duplicate'")
                self.conn.commit()

    def test_missing_and_duplicate_rows_fail(self):
        with self.assertRaises(ValueError):
            read_rows(self.path, ["missing.app"])
        self.conn.execute("INSERT INTO package_app_info SELECT * FROM package_app_info WHERE app_id='example.optional'")
        self.conn.commit()
        with self.assertRaises(ValueError):
            read_rows(self.path, ["example.optional"])

    def test_unknown_boolean_and_sql_injection_fail(self):
        self.conn.execute("UPDATE package_app_info SET app_disable='yes'")
        self.conn.commit()
        with self.assertRaises(ValueError):
            read_rows(self.path, ["example.optional"])
        with self.assertRaises(ValueError):
            read_rows(self.path, ["example'; DROP TABLE package_app_info;--"])

    def test_null_original_value_round_trip(self):
        self.conn.execute("UPDATE package_app_info SET app_onboot=NULL WHERE app_id='example.optional'")
        self.conn.commit()
        rows = read_rows(self.path, ["example.optional"])
        self.conn.executescript(make_sql(rows))
        self.conn.executescript(make_sql(rows, restore=True))
        self.assertIsNone(self.conn.execute("SELECT app_onboot FROM package_app_info "
                          "WHERE app_id='example.optional'").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
