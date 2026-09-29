### The audit trail: who changed what, and when

- **Screens:** `/audit`, `/requirement-checks`
- **Tables:** `obs.audit_entry`, `ops.sensitive_read`, `ops.requirement_check`, `agent.browser_session`, `obs.trace_step`, `obs.trace_read`
- **Installation values:** none
- **Measured here:** 5 routes, 0 called by no screen; 2 write routes, 1 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/audit` | `/`, `/audit`, `/models/:provider`, `/models/:provider/:view` |
| `GET /api/v1/audit/history` | `/audit` |
| `GET /api/v1/requirements/checks` | `/requirement-checks` |
| `POST /api/v1/audit/verification` | `/audit` |
| `POST /api/v1/requirements/checks` | `/requirement-checks` |

- **Gap.** A run's trace graph is stored masked and read only under its own role, and no screen reads it: TraceGraph draws a completed run and no route serves one. Open leaf `M20.2.1`.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/audit/verification` | `/audit` | Not applicable: Walking the ledger reads it and writes nothing. | Not applicable: A verification changes nothing, so there is nothing to record. | `test_a_truncated_ledger_is_reported_through_the_route` in `tests/unit/test_chain_check.py` |
| `POST /api/v1/requirements/checks` | `/requirement-checks` | `test_the_store_keeps_every_check_and_reads_back_the_newest_per_requirement` in `tests/unit/test_requirement_check_routes.py` (database, in CI) | **None.** A check is an append-only row attributed to the person who recorded it, and is not written to the ledger: brain.tables.requirement_check argues why. | `test_a_check_is_recorded_as_the_person_asking_on_the_running_release_and_read_back` in `tests/unit/test_requirement_check_routes.py` |
