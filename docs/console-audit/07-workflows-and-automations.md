### Workflows and automations

- **Screens:** `/agents/:agentId/:tab`, `/automations`, `/automations/:automationId`, `/automations/:automationId/:view`
- **Tables:** `agent.automation`, `agent.automation_run`, `agent.automation_schedule`, `agent.automation_change`, `gate.automation_owner`
- **Installation values:** none
- **Measured here:** 14 routes, 0 called by no screen; 8 write routes, 8 with all three proofs; 3 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/agents/{agent_id}/automation-templates` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automation-templates/{template_id}/preview` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automations` | `/agents/:agentId` |
| `GET /api/v1/console/automations` | `/automations` |
| `GET /api/v1/console/automations/{automation_id}` | `/automations/:automationId`, `/automations/:automationId/:view` |
| `GET /api/v1/console/automations/{automation_id}/stats` | `/automations/:automationId` |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/start` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/automations/{automation_id}/adopt` | `/automations/:automationId`, `/automations/:automationId/:view` |
| `POST /api/v1/automations/{automation_id}/pause` | `/automations/:automationId`, `/automations/:automationId/:view` |
| `POST /api/v1/automations/{automation_id}/remove` | `/automations/:automationId`, `/automations/:automationId/:view` |
| `POST /api/v1/automations/{automation_id}/reschedule` | `/automations/:automationId`, `/automations/:automationId/:view` |
| `POST /api/v1/automations/{automation_id}/resume` | `/automations/:automationId`, `/automations/:automationId/:view` |

- **Gap.** A removed automation cannot be brought back, and installing the same outcome again for the same agent and person is refused. Recorded: A removal is a final row in agent.automation_change (brain.console.automations.A_REMOVAL_IS_FINAL_AND_KEEPS_ITS_HISTORY) and 0055's one-install-per-agent-template-and-person constraint still reads the removed install; the page draws Bring back as not available yet.
- **Gap.** An automation registered to call the tool route with its own credential (gate.automation_owner) is not listed or adoptable on a screen. Recorded: Nothing on an install writes that registration yet: brain.ops.automation_owner_store.StoredAutomations.put has no caller, so there is no row to list; its adopt is kept for when one exists.
- **Gap.** Three of the four automation templates cannot be started on any install. Recorded: brain.ops.automation_run.TASKS says what work_summary, source_freshness and approvals_waiting each still need, and the Automations tab shows that sentence instead of a Start control.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` | `test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither` in `tests/unit/test_agent_automation_store.py` (database, in CI) | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/start` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_a_confirmed_start_is_written_as_the_approver_and_a_stale_one_writes_nothing` in `tests/unit/test_automation_schedule_routes.py` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_owner_stops_their_own_without_approval_and_a_bystander_cannot` in `tests/unit/test_automation_schedule_routes.py` |
| `POST /api/v1/automations/{automation_id}/adopt` | `/automations/:automationId`, `/automations/:automationId/:view` | `test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_an_ownerless_automation_is_adopted_in_the_adopters_name_and_stays_paused` in `tests/unit/test_automations_routes.py` |
| `POST /api/v1/automations/{automation_id}/pause` | `/automations/:automationId`, `/automations/:automationId/:view` | `test_a_paused_automation_does_not_run_on_the_next_tick_and_the_ledger_says_who` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_a_paused_automation_does_not_run_on_the_next_tick_and_the_ledger_says_who` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_a_paused_automation_does_not_run_on_the_next_tick_and_the_ledger_says_who` in `tests/unit/test_automation_change_store.py` (database, in CI) |
| `POST /api/v1/automations/{automation_id}/remove` | `/automations/:automationId`, `/automations/:automationId/:view` | `test_a_removed_automation_never_runs_again_and_cannot_be_started_from_its_agent` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_a_removed_automation_never_runs_again_and_cannot_be_started_from_its_agent` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_a_removed_automation_never_runs_again_and_cannot_be_started_from_its_agent` in `tests/unit/test_automation_change_store.py` (database, in CI) |
| `POST /api/v1/automations/{automation_id}/reschedule` | `/automations/:automationId`, `/automations/:automationId/:view` | `test_a_schedule_change_moves_the_next_run_and_the_runner_keeps_to_the_new_cadence` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_a_schedule_change_moves_the_next_run_and_the_runner_keeps_to_the_new_cadence` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_a_schedule_change_moves_the_next_run_and_the_runner_keeps_to_the_new_cadence` in `tests/unit/test_automation_change_store.py` (database, in CI) |
| `POST /api/v1/automations/{automation_id}/resume` | `/automations/:automationId`, `/automations/:automationId/:view` | `test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter` in `tests/unit/test_automation_change_store.py` (database, in CI) | `test_an_ownerless_automation_stops_and_waits_and_once_adopted_runs_as_the_adopter` in `tests/unit/test_automation_change_store.py` (database, in CI) |
