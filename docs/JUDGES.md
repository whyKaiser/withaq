# WITHAQ — judge demonstration

**Browser trial:** [Try WITHAQ](https://withaq-demo.onrender.com/), choose Try WITHAQ, then Create full experiment. No installation or account. Each visitor has an isolated temporary workspace. Public application is simulated; real packet trials require the local lab below. Source pushes to main redeploy automatically after build/tests. Free hosting can take longer to wake after inactivity. Read [deployment limits](DEPLOYMENT.md).

Start using README's PostgreSQL + `--packets` commands. Log in with the locally generated operator token. No real personal data or provider key is needed.

1. **Create a full experiment.** The API creates independent S1/S2/S3 roots, T1/T3, an unknown artifact held as C-D, and a queued T2 summary. The HTTP worker publishes T2 with its sealed input manifest and S1 root closure.
2. **Record the separable incident.** The worker computes `{a,b}`; the separate validator checks both contracts. Select isolated real packets, then run the plan. Wait for `LAB_CONFIRMED`, not merely QUEUED. Inspect each measured contract, established-session denial and the signed raw receipt in exported JSON. The disposable lab terminates afterward; this is a completed measurement trial.
3. **Compare failure and uncertainty.** Record shared-channel or unknown-evidence incidents. INFEASIBLE/UNKNOWN must prevent application. The model explorer below provides graph comparisons, including full quarantine breaking functions.
4. **Revoke during a model call.** Select T1, enable the five-second delay and start a new run. Revoke the matching S1 root promptly after the MODEL job becomes LEASED. The late result must become REJECTED. If revocation happens after publication, the artifact still becomes unreadable; record the actual ordering instead of claiming a late-publication test.
5. **Preserve and rebuild.** T3 stays ACTIVE; C-D stays HELD. Select the approved S2 input and a revoked T2 as replacement. Start recovery with a new identity. The replacement inherits S2 only; S1 remains REVOKED.
6. **Inspect exact disclosure.** Select an active artifact, inspect mock://review, review exact bytes, approve the bound request and dispatch. The gateway produces MOCK_SENT with zero external bytes. Add a synthetic source containing `password` for BLOCK; use `fake@example.test` for SANITIZE, which keeps lineage. Never enter real secrets or IDs.
7. **Export evidence.** Download current state JSON. It includes IDs, manifests, root versions, plans, independent reports, leases, admission states, packet measurements and hashes; ordinary artifact bytes and tokens are omitted.

For interruption and restore qualification run `python -m pytest tests/test_processes.py` and `python scripts/restore_qualification.py`. The latter creates two new disposable PostgreSQL databases, restores an intentionally older dump, verifies the newer signed barrier before resuming, and removes only its own test databases.

The raw 300-setting comparison is **model-only**, not 300 network trials. This is a computer-lab prototype, with the remaining engineering-guide scope disclosed in [traceability](POSTER-TRACEABILITY.md). Public GitHub access is source/evidence access, not a hosted runtime.
