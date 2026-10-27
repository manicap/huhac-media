# Normalizer N3 performance verification

**Verified:** 2026-10-27 on the Windows development host.

The reproducible benchmark is `tests/media_desk/benchmark_n3.py`. It creates one
synthetic public workspace, publishes a real N1 Normalizer snapshot, then measures
the same 1,000-asset dataset with the integration disabled and enabled. Each mode
performs 30 API batch requests. `tracemalloc` records peak Python allocations, so
startup timings include its instrumentation overhead and are not a production SLA.

Command:

```powershell
.\.venv\Scripts\python.exe tests\media_desk\benchmark_n3.py --assets 1000 --requests 30
```

| Metric | Normalizer off | Normalizer on | Exact facet, no match |
|---|---:|---:|---:|
| startup | 2779.484 ms | 5198.778 ms | 4855.581 ms |
| peak Python allocation | 5.275 MiB | 19.633 MiB | 19.560 MiB |
| batch p50 | 11.405 ms | 13.482 ms | 4.944 ms |
| batch p95 | 34.322 ms | 21.961 ms | 5.997 ms |

The final adapter validates all asset documents once at startup, retains compact
facet/completeness/event projections plus the original validated JSON bytes, and
decodes the full result from memory only for detail responses. This reduced the
measured Normalizer-on peak from the pre-optimization 29.579 MiB to 19.633 MiB.
Scrolling and batch requests perform no additional Normalizer filesystem reads.
The remaining startup cost is the explicit validation and hashing of 1,000 immutable
result documents; no claim is made for production storage or 10k scale here.
