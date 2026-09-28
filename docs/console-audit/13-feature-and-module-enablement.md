### Feature and module enablement

- **Screens:** `/features`
- **Tables:** `ops.plugin_install`, `ops.plugin_version`
- **Installation values:** none
- **Measured here:** 2 routes, 0 called by no screen; 1 write routes, 1 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/install/features` | `/features` |
| `POST /api/v1/install/features/{name}` | `/features` |

- **Gap.** A plugin cannot be installed or enabled. Recorded: Nothing loads a plugin yet: the Features screen says plugins_have_no_loader, and ops.plugin_install has no writer a route calls.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/install/features/{name}` | `/features` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
