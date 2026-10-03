# Evidence and acceptance mapping

Source: Build & Operations edition 2.0, pp. 43–44 and 59. The source defines a broader system than this initial simulation.

| Check | Current evidence | Qualification |
|---|---|---|
| AT01 separable containment | Hand-derived 16-subset oracle, planner + validator | Logical model only; no packet confirmation |
| AT02 inseparable channel | shared-channel INFEASIBLE test | Implemented for finite fixture |
| AT03 unknown dependency | evidence-complete guard and UNKNOWN test | Implemented for finite fixture |
| AT04 tampered/stale plan | Version/action/cost tamper cases; hash recheck at apply | Implemented locally |
| AT05 established sessions | None | NOT IMPLEMENTED; real lab required |
| AT06 late result after revoke | Captured S1 version rejected at simulated publication admission | Model completion simulated; no durable worker yet |
| AT07 T1/T2/T3/C-D effects | Read denial and held/independent fixture checks | Fixed lineage; general lineage engine pending |
| AT08 recovery | New T2b rooted only in S2 | Deterministic alternative; quality evaluation pending |
| AT09 changed disclosure | Exact-byte hash and root/approval checks | Mock provider and limited keyword policy |
| AT10 revoke before/after admission | Root recheck before synchronous mock admission; pre-admission denial tested | No in-flight external send/cancellation qualification |
| AT11 restart behavior | Local SQLite state persists on store reopen | Distributed worker/fencing/restore NOT IMPLEMENTED |
| AT12 controller loss | None | NOT IMPLEMENTED; no real controller or automatic unblocking |

Network-level direct-provider bypass prevention is also unimplemented; the current adapter performs no external sends.

## Delivery gates

- **D1 partial:** reproducible source/dependencies/local identity exist; authoritative PostgreSQL migrations and lab identity remain.
- **D2 model baseline:** bounded planner, independent checks and oracle cases implemented. Exhaustive correctness across arbitrary supplied models is not claimed.
- **D3 fixture baseline:** local revocation and recovery guards; general lineage, real concurrent workers and durable jobs remain.
- **D4 mock baseline:** frozen-request approval, guarded admission and simulated unknown outcomes; isolated gateway and external provider qualification remain.
- **D5 initial console:** Arabic/English labels and end-to-end manual scenario; broader management screens and automated browser suite remain.
- **D6 not started:** real lab enforcement and session probes.
- **D7 partial:** reproducible synthetic evidence and runbook; qualified restore and comparative study remain.

Changes to an acceptance row require a linked test or raw evidence. Passing a build does not advance an unrelated gate.
