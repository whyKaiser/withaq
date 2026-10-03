# Evidence and acceptance mapping — release 0.2

Build & Operations edition 2.0, pp. 43–44/59, defines broader production gates. These rows qualify the executed computer lab only.

| Check | Evidence | Scope / remaining qualification |
|---|---|---|
| AT01 separable containment | 16-subset oracle; signed packet receipt; per-event monitor/alert observations | G/X/P/M/A synthetic topology; no persistent production rules |
| AT02 inseparable channel | shared-channel INFEASIBLE after complete search | Finite declared model |
| AT03 uncertainty | missing evidence/probes UNKNOWN | General dependency management still open |
| AT04 tampered/stale plans | validator tests, hash/version guards, unsupported PEP models | Local operator/service identities |
| AT05 established sessions | TCP session established before nftables deny; five subsequent records blocked | Actual packets in isolated container |
| AT06 late publication | complete manifest root guard; cross-process race; delayed HTTP worker flow | Mock model computation, real publication barrier |
| AT07 dependent/independent/unknown | General lineage tests: T1/T2 denied, T3 active, unknown artifact held | All inputs explicitly registered; physical deletion not claimed |
| AT08 recovery | Independent roots, new immutable identity, quality guard, promotion | Deterministic mock quality, not semantic LLM evaluation |
| AT09 exact approval | Payload/account/purpose/destination mutation tests; policy/expiry/root guards | Mock provider; bounded disclosure corpus |
| AT10 admission boundary | pre-admission revoke denial; post-admission cancellation limit recorded | External sends not attempted |
| AT11 restart/restore | actual worker kill/restart, fence increment, deduped output; old PostgreSQL dump + newer signed ledger | Operator selects latest ledger; automatic replicated ledger not implemented |
| AT12 controller absence | installed rules persist after rule-installer exit; no reopening during packet probe | Partial: persistent controller reconciliation/failure drills remain |

`tests/test_engine.py` runs the same safety cases on SQLite and PostgreSQL. `tests/test_processes.py` starts real API, validator, worker and gateway processes, kills a model worker, resumes the job with a higher fence and tests unknown-send non-retry. `tests/test_pep.py` verifies role/model rejection without Docker execution. The executed packet and restore reports are under [evidence](evidence/README.md).

## Gates

D1: local PostgreSQL/migration/version/identity gate executed; institutional identity remains.
D2: finite decisions and logical/process-independent validation executed.
D3: general lineage/manifests/barriers, race and recovery executed with synthetic inputs.
D4: four-decision disclosure and separate gateway executed in mock mode; production network bypass prevention remains.
D5: operational console integrated and manually reviewed; automated browser tests and member reproduction remain.
D6: declared packet topology executed, including established flow denial; broader always-on deployment/real device coverage remains.
D7: 300 model settings and old-backup restore qualification executed; independent reproduction and production operations qualification remain.

A build, screenshot or mock receipt cannot close an unrelated gate. See [poster traceability](POSTER-TRACEABILITY.md).
