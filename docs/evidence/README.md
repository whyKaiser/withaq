# Evidence index

All committed input values are synthetic. Read the mode, source commit, recording time and dirty-tree marker before drawing a conclusion.

| Bundle | Meaning |
|---|---|
| `benchmark-v0.2.json` / `.csv` | 300 model settings; 60 complete seeded snapshots; five explicit project policies; every rejection/unknown retained |
| `packet-lab-v0.2.json` | Actual TCP/nftables trial inside a network-none container; individual monitor/alert and attack records, rules/counters, routes and runtime versions |
| `restore-v0.2.json` | Executed PostgreSQL old-dump/newer-ledger qualification in disposable databases; tamper/read/resume checks |
| `system-v0.2.json` | Token-free operational state: PostgreSQL, sealed manifests, actual worker jobs, delayed publication rejection, new-identity recovery and signed packet receipt |
| `verification-v0.2.json` | Release check commands, results and scope |
| `demo-evidence.json`, `verification.json` | Historical 0.1 fixture evidence; not proof of the newer distributed state or packet implementation |

`LAB_CONFIRMED` means a completed ephemeral packet trial on synthetic endpoints. The raw signed receipt is bound to its candidate and snapshot hashes. It does not describe ongoing protection of a real facility. `MOCK_SENT` does not transmit bytes to an external AI service. The comparison is **model-only**, not 300 field experiments.

The fresh benchmark, standalone packet and restore bundles were regenerated from clean source commit `c70d693fad024a08bdeb3018b7e22c9d47ffbc1a`. The system bundle retains earlier session history: its export commit does not establish a source commit for every historical job. After that source commit and service restart, the console executed fresh `separable` (`a+b`, cost 2) and `bounded-dependency` (`a+d`, cost 3) plans. Both returned `LAB_CONFIRMED`, with every declared critical function measured PASS. Their exact IDs and verification provenance are in `verification-v0.2.json`.

For reproducing the bundles, run the scripts in README. Defaults write into ignored `artifacts/`; publication is a deliberate selection step so private runtime data does not enter Git automatically.
