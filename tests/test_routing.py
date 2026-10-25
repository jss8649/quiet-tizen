import re
import sqlite3
import tempfile
from pathlib import Path
import unittest
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.conn = sqlite3.connect(self.directory / "live.db")
        self.conn.executescript("""
          CREATE TABLE key_filter(appid TEXT, key TEXT, target_selector TEXT, args TEXT, other TEXT);
          INSERT INTO key_filter VALUES
            ('com.samsung.tv.quicklaunch','XF86More','package:com.samsung.tv.quicklaunch','original-more','keep'),
            ('org.tizen.menu','XF86SysMenu','package:org.tizen.menu','original-menu','keep'),
            ('unrelated.app','Other','package:unrelated.app','unrelated','keep');
        """)
        with closing(sqlite3.connect(self.directory / ".app-context.db")) as snapshot:
            self.conn.backup(snapshot)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def sql(self, recipe):
        script = (ROOT / "recipes" / recipe).read_text()
        sql = re.search(r"<<SQL\n(.*?)\nSQL", script, re.S).group(1)
        return sql.replace("$D", str(self.directory))

    def test_round_trip_preserves_new_metadata(self):
        self.conn.executescript(self.sql("install-settings-bridge.sh"))
        self.conn.execute("DETACH before")
        self.conn.execute("UPDATE key_filter SET other='updated'")
        self.conn.commit()
        self.conn.executescript(self.sql("restore-settings-bridge.sh"))
        self.assertEqual(self.conn.execute("SELECT target_selector,args,other FROM key_filter "
                         "WHERE appid='org.tizen.menu'").fetchone(),
                         ("package:org.tizen.menu", "original-menu", "updated"))
        self.assertEqual(self.conn.execute("SELECT args FROM key_filter "
                         "WHERE appid='unrelated.app'").fetchone(), ("unrelated",))

    def test_changed_rule_refuses_apply(self):
        self.conn.execute("UPDATE key_filter SET args='vendor-update' WHERE appid='org.tizen.menu'")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.executescript(self.sql("install-settings-bridge.sh"))
        self.conn.rollback()
        self.assertEqual(self.conn.execute("SELECT args FROM key_filter "
                         "WHERE appid='com.samsung.tv.quicklaunch'").fetchone(), ("original-more",))

    def test_changed_rule_refuses_restore(self):
        self.conn.executescript(self.sql("install-settings-bridge.sh"))
        self.conn.execute("DETACH before")
        self.conn.execute("UPDATE key_filter SET args='new vendor route' WHERE appid='org.tizen.menu'")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.executescript(self.sql("restore-settings-bridge.sh"))
        self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
