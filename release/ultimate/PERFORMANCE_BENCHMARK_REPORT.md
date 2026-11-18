# Performance and Capacity Report

BioIntel uses bounded previews, lazy imports/loading, persistent background workers, caching, SQLite WAL where appropriate, chunked/streamed file handling, process-tree cancellation and supervisor health checks. Heavy external engines and large scientific assets are isolated from ordinary navigation.

## Preserved measured engineering evidence

The shipped Step20 benchmark report records the following measurements from its original benchmark environment:

- 160,000-row full CSV path: 0.586319 seconds and 146.16 MB measured dataframe footprint.
- 100-row bounded preview: 0.004277 seconds and 0.0918 MB measured dataframe footprint.
- Integrity cache: 0.164908 seconds cold and 0.001625 seconds warm (101.48x measured speedup).
- Model load: 2.569613 seconds uncached and 0.000244 seconds cached (10,539.93x measured speedup).

The current builder also completed the mobile Vite production build after transforming 30 modules. These measurements are engineering regression evidence from specific build environments, not throughput guarantees or scientific-performance claims. The RDKit-dependent benchmark was not re-executed in the current minimal builder because RDKit is not installed here.

Scientific workload performance depends on file size, selected algorithms, external engine versions, reference databases, CPU/RAM/disk and optional GPU availability.

Before a production deployment, run representative workloads under the intended Windows hardware and record peak RAM, disk growth, elapsed time, cancellation latency, restart recovery and output equivalence. See `docs/runbooks/PERFORMANCE_AND_CAPACITY.md`.
