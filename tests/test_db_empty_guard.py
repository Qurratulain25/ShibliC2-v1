"""Refuse initializing a truncated/empty SQLCipher file with a new key."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.core.db_engine import connect, refuse_empty_database


class EmptyDatabaseGuardTests(unittest.TestCase):
    def test_zero_byte_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "shibli_c2.db"
            db.write_bytes(b"")
            with self.assertRaises(RuntimeError) as ctx:
                refuse_empty_database(db)
            self.assertIn("0 bytes", str(ctx.exception))
            self.assertIn("recover_runtime.py", str(ctx.exception))

    def test_connect_does_not_mint_new_db_on_empty_file(self) -> None:
        os.environ["SHIBLI_DB_KEY"] = "unit-test-key-not-a-secret"
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "shibli_c2.db"
            db.write_bytes(b"")
            with self.assertRaises(RuntimeError):
                connect(db)
            self.assertEqual(db.stat().st_size, 0)

    def test_missing_file_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            refuse_empty_database(Path(tmp) / "missing.db")


if __name__ == "__main__":
    unittest.main()
