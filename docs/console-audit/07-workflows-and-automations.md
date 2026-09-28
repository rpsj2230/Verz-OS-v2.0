### Workflows and automations

- **Screens:** `/agents/:agentId/:tab`
- **Tables:** `agent.automation`, `agent.automation_run`, `agent.automation_schedule`, `gate.automation_owner`
- **Installation values:** none
- **Measured here:** 6 routes, 0 called by no screen; 3 write routes, 3 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/agents/{agent_id}/automation-templates` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automation-templates/{template_id}/preview` | `/agents/:agentId/:tab` |
| `GET /api/v1/agents/{agent_id}/automations` | `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/start` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop` | `/agents/:agentId`, `/agents/:agentId/:tab` |

- **Gap.** An installed automation cannot be changed or removed, only started and stopped. Recorded: brain.automation_schedule_routes starts and stops one and brain.console.agent_automations.remove decides a removal that no route performs; 0067 grants an update of the next run alone.
- **Gap.** Three of the four automation templates cannot be started on any install. Recorded: brain.ops.automation_run.TASKS says what work_summary, source_freshness and approvals_waiting each still need, and the Automations tab shows that sentence instead of a Start control.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/agents/{agent_id}/automations` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` | `test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither` in `tests/unit/test_agent_automation_store.py` (database, in CI) | `test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context` in `tests/unit/test_automation_gallery_routes.py` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/start` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_a_confirmed_start_is_written_as_the_approver_and_a_stale_one_writes_nothing` in `tests/unit/test_automation_schedule_routes.py` |
| `POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who` in `tests/unit/test_automation_run_store.py` (database, in CI) | `test_the_owner_stops_their_own_without_approval_and_a_bystander_cannot` in `tests/unit/test_automation_schedule_routes.py` |
