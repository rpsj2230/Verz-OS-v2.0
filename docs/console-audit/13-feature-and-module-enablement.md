### Feature and module enablement

- **Screens:** `/features`
- **Tables:** `ops.coordinated_run`, `ops.fanout_gate`, `ops.migration_record`, `ops.plugin_install`, `ops.plugin_version`
- **Installation values:** none
- **Measured here:** 23 routes, 9 called by no screen; 10 write routes, 1 with all three proofs; 6 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/install/features` | `/features` |
| `GET /api/v1/install/plugins` | `/features` |
| `GET /api/v1/migration` | `/features` |
| `GET /api/v1/orchestration/coordinated-runs` | **no screen** |
| `GET /api/v1/orchestration/weighed-plans` | `/features` |
| `POST /api/v1/install/features/{name}` | `/features` |
| `POST /api/v1/install/plugins` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/disable` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/enable` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/plan` | **no screen** |
| `POST /api/v1/install/plugins/{plugin_id}/remove` | `/features` |
| `POST /api/v1/install/plugins/{plugin_id}/rollback` | **no screen** |
| `POST /api/v1/install/plugins/{plugin_id}/upgrade` | **no screen** |
| `POST /api/v1/migration/availability` | **no screen** |
| `POST /api/v1/migration/carry` | **no screen** |
| `POST /api/v1/migration/cutover/complete` | `/features` |
| `POST /api/v1/migration/learning` | **no screen** |
| `POST /api/v1/migration/skills/convert` | **no screen** |
| `POST /api/v1/orchestration/coordinated-runs` | **no screen** |
| `POST /api/v1/orchestration/weighed-plans` | `/features` |
| `PUT /api/v1/migration/cutover` | `/features` |
| `PUT /api/v1/migration/parallel` | `/features` |
| `PUT /api/v1/migration/register` | `/features` |

- **Gap.** A recorded plugin is not loaded: switching one on changes its record and nothing runs. Recorded: The points that take code run it in a sidecar or a sandbox and neither runner exists, so the panel says no_plugin_is_loaded; M29.2.4 (a drain on upgrade) and M29.2.5 (an isolation tier enforced by a host) wait on one.
- **Gap.** A weighed plan starts nothing, and a request split between a coordinating agent's specialists has no page. Recorded: The panel says nothing_is_started because weighing is a rehearsal; splitting a request, running the specialists and listing the runs kept are POST and GET /orchestration/coordinated-runs (brain.coordination_routes), behind the multi_agent_coordination switch, and no page draws them yet (M18.5.3).
- **Gap.** Nothing in a migration reaches the old system: a revocation, a job stopped and an act done are recorded as a person says they are. Recorded: brain.migration.decommission says nothing here can check any of them, so a cutover is refused only while an act with a security consequence is unrecorded; the exporter and the old system's side of the comparison are a plugin that does not exist (M37.1.2, M37.1.3.1).
- **Gap.** A saved migration document is not an entry in the audit ledger. Recorded: ops.migration_record keeps a version per save with who saved it, appended and never edited, and a save changes nobody's access and no configuration.
- **Gap.** A weighed plan is not an entry in the audit ledger. Recorded: ops.fanout_gate is its own record of who weighed what and when (numbers and a verdict, written in the session's own name and never edited), and weighing a plan changes nobody's access and no configuration.
- **Gap.** A plugin's install, enable, upgrade, rollback or removal is not an entry in the audit ledger. Recorded: ops.plugin_install has no trigger that appends one, and adding it is a migration that widens the ledger's action list and subject grammar; the route logs who pressed it and the row keeps its history of versions.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/install/features/{name}` | `/features` | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused` in `tests/unit/test_console_controls_reach_behaviour.py` |
| `POST /api/v1/install/plugins` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/install/plugins/{plugin_id}/disable` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/install/plugins/{plugin_id}/enable` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/install/plugins/{plugin_id}/remove` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) | **None.** ops.plugin_install has no audit trigger, so a plugin's change leaves no ledger entry; the route logs who pressed it and the row keeps the versions it ran. A trigger is a migration that widens the ledger's action list. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_plugin_registry.py` (database, in CI) |
| `POST /api/v1/migration/cutover/complete` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) | **None.** ops.migration_record keeps a version per save with who saved it, appended and never edited; a save changes nobody's access and no configuration, so no ledger entry is appended. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) |
| `POST /api/v1/orchestration/weighed-plans` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_orchestration_rehearsal.py` (database, in CI) | **None.** ops.fanout_gate is its own record of who weighed which plan and when, written in the session's own name and never edited; weighing a plan changes nobody's access and no configuration, so no ledger entry is appended. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_orchestration_rehearsal.py` (database, in CI) |
| `PUT /api/v1/migration/cutover` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) | **None.** ops.migration_record keeps a version per save with who saved it, appended and never edited; a save changes nobody's access and no configuration, so no ledger entry is appended. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) |
| `PUT /api/v1/migration/parallel` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) | **None.** ops.migration_record keeps a version per save with who saved it, appended and never edited; a save changes nobody's access and no configuration, so no ledger entry is appended. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) |
| `PUT /api/v1/migration/register` | `/features` | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) | **None.** ops.migration_record keeps a version per save with who saved it, appended and never edited; a save changes nobody's access and no configuration, so no ledger entry is appended. | `test_every_check_passes_on_an_install_and_leaves_nothing` in `tests/unit/test_acceptance_checks_migration_workspace.py` (database, in CI) |
