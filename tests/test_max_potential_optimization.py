import unittest, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.optimization.max_lru_cache import MaxLRUCache, MAX_APP_CACHE
from biointel.optimization.fast_serializer import FastSerializer
from biointel.optimization.thread_pool_tuner import HardwareThreadPoolTuner


class TestMaxPotentialOptimization(unittest.TestCase):
    def test_max_lru_cache(self) -> None:
        cache = MaxLRUCache(maxsize=3, default_ttl_sec=10.0)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        self.assertEqual(cache.get("k1"), "v1")
        self.assertEqual(cache.get("k2"), "v2")

        cache.set("k3", "v3")
        cache.set("k4", "v4")  # k1 will be evicted if least recently used, or k2
        self.assertIsNotNone(cache.get("k4"))

    def test_fast_serializer(self) -> None:
        data = {"gene": "TP53", "score": 99.8, "tags": ["cancer", "tumor"]}
        s = FastSerializer.dumps(data)
        d = FastSerializer.loads(s)
        self.assertEqual(d["gene"], "TP53")
        self.assertEqual(d["score"], 99.8)

    def test_thread_pool_tuner(self) -> None:
        workers_io = HardwareThreadPoolTuner.get_optimal_worker_count(io_bound=True)
        workers_cpu = HardwareThreadPoolTuner.get_optimal_worker_count(io_bound=False)
        self.assertGreaterEqual(workers_io, 4)
        self.assertGreaterEqual(workers_cpu, 2)

        executor = HardwareThreadPoolTuner.create_executor("test_worker")
        future = executor.submit(lambda x: x * 2, 21)
        self.assertEqual(future.result(), 42)
        executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
