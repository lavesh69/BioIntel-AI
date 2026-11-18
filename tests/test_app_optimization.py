import unittest, sys, pathlib, tempfile, sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.optimization.sqlite_optimizer import optimize_sqlite_db
from biointel.optimization.memory_cleaner import MemoryOptimizer


class TestAppOptimization(unittest.TestCase):
    def test_sqlite_optimizer(self) -> None:
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            db_path = pathlib.Path(temp_dir) / "test.sqlite3"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE t (id INT);")
            conn.close()

            res = optimize_sqlite_db(db_path)
            self.assertEqual(res["status"], "optimized")
            self.assertEqual(res["journal_mode"].lower(), "wal")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_memory_optimizer(self) -> None:
        res = MemoryOptimizer.collect()
        self.assertIn("unreachable_objects_freed", res)
        MemoryOptimizer.trim_heap()


if __name__ == "__main__":
    unittest.main()
