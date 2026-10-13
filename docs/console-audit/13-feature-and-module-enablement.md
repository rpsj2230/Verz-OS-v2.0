### Feature and module enablement

- **Screens:** `/features`
- **Tables:** `ops.plugin_install`, `ops.plugin_version`
- **Installation values:** none
- **Measured here:** 10 routes, 3 called by no screen; 5 write routes, 1 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/install/features` | `/features` |
| `GET /api/v1/install/plugins` | `/features` |
| `POST /api/v1/install/features/{name}` | `/features` |
| `POST /api/v1/install/plugins` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/disable` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/enable` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/plan` | **no screen** |
| `POST /api/v1/install/plugins/{plugin_id}/remove` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/rollback` | **no screen** |
| `POST /api/v1/install/plugins/{plugin_id}/upgrade` | **no screen** |

- **Gap.** A recorded plugin is not loaded: switching one on changes its record and nothing runs. Recorded: The points that take code run it in a sidecar or a sandbox and neither runner exists, so the panel says no_plugin_is_loaded; M29.2.4 (a drain on upgrade) and M29.2.5 (an isolation tier enforced by a host) wait on one.
- **Gap.** A plugin's install, enable, upgrade, rollback or removal is not an entry in the audit ledger. Recorded: ops.plugin_install has no trigger that appends one, and adding it is a migration that widens the ledger's action list and subject grammar; the route logs who pressed it and the row keeps its history of versions.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/install/features/{name}` | `/features` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/install/plugins` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/install/plugins/{plugin_id}/disable` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/install/plugins/{plugin_id}/enable` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/install/plugins/{plugin_id}/remove` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
