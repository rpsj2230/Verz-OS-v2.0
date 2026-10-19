### Scheduled jobs and background work

- **Screens:** `/jobs`, `/jobs/:name`, `/jobs/:name/:view`, `/runs`
- **Tables:** `ops.control_run`, `ops.operation`, `ops.acceptance_result`, `ops.acceptance_run`, `ops.dead_letter`
- **Installation values:** none
- **Measured here:** 10 routes, 0 called by no screen; 4 write routes, 4 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/jobs` | `/jobs` |
| `GET /api/v1/jobs/dead` | `/jobs` |
| `GET /api/v1/jobs/{name}` | `/jobs/:name`, `/jobs/:name/:view` |
| `GET /api/v1/jobs/{name}/runs` | `/jobs/:name` |
| `GET /api/v1/operate/runs` | `/runs` |
| `GET /api/v1/operations/interrupted` | `/runs` |
| `POST /api/v1/jobs/dead/{job_id}/redrive` | `/jobs` |
| `POST /api/v1/jobs/{name}/pause` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` |
| `POST /api/v1/jobs/{name}/run` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` |

- **Gap.** A run in progress cannot be stopped. Recorded: The route says no_run_can_be_stopped: a control runs to its end inside the worker's tick and there is nothing to signal.
- **Gap.** A person cannot mark an interrupted action resolved by their word, and nothing sends one again. Recorded: An action whose result is unknown leaves that state only by being checked against the system it went to (brain.ops.idempotency.UNKNOWN_IS_NOT_FAILED). Whether a person's word may stand in for that check is the owner's question (needs-rupash 188, item 5), and it is not decided here.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/jobs/dead/{job_id}/redrive` | `/jobs` | `test_pressing_run_again_writes_the_instant_the_worker_reads_and_says_who_pressed` in `tests/unit/test_redrive_routes.py` | `test_pressing_run_again_on_a_set_aside_job_reaches_the_row_and_the_ledger` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_persons_ask_puts_one_job_back_through_the_drivers_retry_and_is_answered_once` in `tests/unit/test_dead_letter.py` (database, in CI) |
| `POST /api/v1/jobs/{name}/pause` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/run` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
