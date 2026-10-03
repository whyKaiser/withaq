# WITHAQ: five-minute judge walkthrough

## What this release proves

A bounded decision model, independent validation, and application-level synthetic data guards execute in real code. The network and provider are simulated. No graph animation is presented as packet enforcement, and no real-world safety or detection accuracy is claimed.

## Reproduce

Follow the root README bootstrap and startup commands. The first installation needs internet; the installed simulation needs no model API key. Enter the locally generated token, then:

1. **Separable incident / WITHAQ:** create a run. Expect `OPTIMAL`, `{a,b}`, cost 2, 16 examined, 3 feasible. Check independent per-function verdicts. Authorize simulated application; the state must say `SIMULATED_CONFIRMED`.
2. **Full quarantine comparison:** create a separate run with the quarantine policy. Both attack paths are denied in the model but both critical functions fail; application is disabled and the server rejects bypass attempts.
3. **Conflict/uncertainty:** select shared-channel to see `INFEASIBLE`; select unknown-evidence to see `UNKNOWN`. These are intentionally different outcomes.
4. **Source impact:** return to separable. Revoke S1. T1/T2 become REVOKED, T3 remains ACTIVE, C-D remains HELD. Check a late result; admission is rejected. Rebuild T2b; its only root is S2 and S1 stays revoked.
5. **Disclosure:** inspect T2b. Review exact synthetic bytes, approve, then simulate dispatch. A new request can simulate a lost response; it becomes `OUTCOME_UNKNOWN` and cannot be sent again. Adding `national_id=TEST` or `رقم الهوية: تجربة` produces BLOCKED under the deliberately limited fixture policy.
6. Export JSON evidence; inspect sequence, versions, plan/snapshot hashes, and the explicit simulation label.

## Independent verification

Run Python tests and `scripts/export_evidence.py`. [Sample evidence](evidence/demo-evidence.json) is synthetic and identifies its code commit. The full blueprint and unimplemented requirements remain visible in [acceptance](acceptance.md), [status](../vault/02-STATUS.md) and [backlog](../vault/06-BACKLOG.md).

GitHub is the source repository, not a hosted runtime. The local development token is not needed to read this repository; each evaluator generates their own by starting the application.
