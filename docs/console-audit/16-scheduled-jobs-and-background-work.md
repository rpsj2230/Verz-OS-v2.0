### Scheduled jobs and background work

- **Screens:** `/jobs`, `/jobs/:name`, `/jobs/:name/:view`, `/runs`
- **Tables:** `ops.control_run`, `ops.operation`, `ops.acceptance_result`
- **Installation values:** none
- **Measured here:** 7 routes, 0 called by no screen; 3 write routes, 3 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/jobs` | `/jobs` |
| `GET /api/v1/jobs/{name}` | `/jobs/:name`, `/jobs/:name/:view` |
| `GET /api/v1/jobs/{name}/runs` | `/jobs/:name` |
| `GET /api/v1/operate/runs` | `/runs` |
| `POST /api/v1/jobs/{name}/pause` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` |
| `POST /api/v1/jobs/{name}/run` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` |

- **Gap.** A run in progress cannot be stopped. Recorded: The route says no_run_can_be_stopped: a control runs to its end inside the worker's tick and there is nothing to signal.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/jobs/{name}/pause` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/resume` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/jobs/{name}/run` | `/jobs`, `/jobs/:name`, `/jobs/:name/:view` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
