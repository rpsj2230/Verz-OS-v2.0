### The audit trail: who changed what, and when

- **Screens:** `/audit`, `/audit/verify`, `/audit/trace`, `/audit/trace/:traceId`, `/audit/subject/:kind/:id`, `/audit/subject/:kind/:id/:view`, `/requirement-checks`
- **Tables:** `obs.audit_entry`, `ops.sensitive_read`, `ops.requirement_check`, `agent.browser_session`, `obs.trace_step`, `obs.trace_read`
- **Installation values:** none
- **Measured here:** 6 routes, 1 called by no screen; 3 write routes, 2 with all three proofs; 0 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/audit` | `/`, `/audit`, `/audit/subject/:kind/:id`, `/audit/subject/:kind/:id/:view`, `/models/:provider`, `/models/:provider/:view` |
| `GET /api/v1/audit/history` | `/audit/subject/:kind/:id/:view` |
| `GET /api/v1/requirements/checks` | `/requirement-checks` |
| `POST /api/v1/audit/verification` | `/audit`, `/audit/subject/:kind/:id`, `/audit/subject/:kind/:id/:view`, `/audit/verify` |
| `POST /api/v1/requirements/checks` | `/requirement-checks` |
| `POST /api/v1/traces/{trace_id}/read` | **no screen** |

No gap recorded.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/audit/verification` | `/audit`, `/audit/subject/:kind/:id`, `/audit/subject/:kind/:id/:view`, `/audit/verify` | Not applicable: Walking the ledger reads it and writes nothing. | Not applicable: A verification changes nothing, so there is nothing to record. | `test_a_truncated_ledger_is_reported_through_the_route` in `tests/unit/test_chain_check.py` |
| `POST /api/v1/requirements/checks` | `/requirement-checks` | `test_the_store_keeps_every_check_and_reads_back_the_newest_per_requirement` in `tests/unit/test_requirement_check_routes.py` (database, in CI) | **None.** A check is an append-only row attributed to the person who recorded it, and is not written to the ledger: brain.tables.requirement_check argues why. | `test_a_check_is_recorded_as_the_person_asking_on_the_running_release_and_read_back` in `tests/unit/test_requirement_check_routes.py` |
| `POST /api/v1/traces/{trace_id}/read` | **no screen** | `test_a_person_whose_token_carries_the_payload_role_reads_the_trace_after_its_row` in `tests/unit/test_trace_routes.py` (database, in CI) | Not applicable: The read's own row in obs.trace_read is the record of who read the trace and why; reading changes nothing a ledger entry would record. | `test_without_the_role_a_trace_is_answered_like_one_that_does_not_exist` in `tests/unit/test_trace_routes.py` (database, in CI) |
