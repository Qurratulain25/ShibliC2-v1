"""Automatic DB backups only for real migrations, with retention."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.db_engine import MAX_AUTOMATIC_BACKUPS, backup_database, _prune_automatic_backups


class BackupPolicyTests(unittest.TestCase):
    def test_backup_writes_to_central_dir_not_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "shibli_c2.db"
            db.write_bytes(b"sqlcipher-placeholder")
            backup_root = root / "backups"
            with patch("app.core.paths.backups_dir", return_value=backup_root):
                dest = backup_database(db, reason="schema-v3")
            self.assertTrue(dest.exists())
            self.assertEqual(dest.parent, backup_root)
            self.assertNotEqual(dest.parent, db.parent)
            self.assertTrue(dest.name.startswith("shibli_c2_schema-v3_"))
            self.assertEqual(len(list(db.parent.glob("shibli_c2_backup_*.db"))), 0)

    def test_prune_keeps_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for i in range(8):
                p = dest / f"shibli_c2_test_{i}.db"
                p.write_bytes(b"x")
            _prune_automatic_backups(dest, keep=MAX_AUTOMATIC_BACKUPS)
            self.assertEqual(len(list(dest.glob("shibli_c2_*.db"))), MAX_AUTOMATIC_BACKUPS)

    def test_empty_db_is_not_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "shibli_c2.db"
            db.write_bytes(b"")
            with self.assertRaises(FileNotFoundError):
                backup_database(db, reason="startup")


if __name__ == "__main__":
    unittest.main()
