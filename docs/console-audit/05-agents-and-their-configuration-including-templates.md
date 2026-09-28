### Agents and their configuration, including templates

- **Screens:** `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/agent-templates`, `/agent-templates/:templateId`, `/approvals`, `/approvals/:suspensionId`
- **Tables:** `agent.agent`, `agent.template_instance`, `agent.template_version`, `agent.upgrade_decline`, `agent.browser_envelope`, `gate.suspension`
- **Installation values:** none
- **Measured here:** 18 routes, 2 called by no screen; 8 write routes, 7 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/agent-templates` | `/agent-templates` |
| `GET /api/v1/agent-templates/{template_id}` | `/agent-templates/:templateId` |
| `GET /api/v1/agent-templates/{template_id}/versions/{version}` | `/agent-templates/:templateId` |
| `GET /api/v1/agents` | `/`, `/agents`, `/department` |
| `GET /api/v1/agents/{agent_id}/about` | **no screen** |
| `GET /api/v1/agents/{agent_id}/lifecycle` | **no screen** |
| `GET /api/v1/agents/{agent_id}/workspace` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `GET /api/v1/approvals` | `/approvals` |
| `GET /api/v1/approvals/{suspension_id}` | `/approvals/:suspensionId` |
| `GET /api/v1/console/agents/{agent_id}/stats` | `/agents`, `/agents/:agentId` |
| `POST /api/v1/agent-templates/{template_id}/versions/{version}/install` | `/agent-templates/:templateId` |
| `POST /api/v1/agents/{agent_id}/archive` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` |
| `POST /api/v1/agents/{agent_id}/disable` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` |
| `POST /api/v1/agents/{agent_id}/duplicate` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` |
| `POST /api/v1/agents/{agent_id}/enable` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` |
| `POST /api/v1/agents/{agent_id}/transfer` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` |
| `PUT /api/v1/agents/{agent_id}/model-pin` | `/agents/:agentId`, `/agents/:agentId/:tab` |

- **Gap.** An agent cannot be created from scratch, and its manifest, leash and procedure cannot be edited. Recorded: components/ManifestForm.tsx and components/ProcedureCanvas.tsx are built and tested and rendered by no registered page, and no route writes a template version from the console.
- **Gap.** A published template version cannot be installed from the console. Recorded: brain.agent_lifecycle_routes serves the version and its install, and the Agent templates page has no button that presses it yet; switching on and off, archiving, duplicating and handing on are pressed from the Agents pages.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/agent-templates/{template_id}/versions/{version}/install` | `/agent-templates/:templateId` | `test_an_installed_version_starts_disabled_and_at_shadow_on_every_target` in `tests/unit/test_agent_lifecycle_routes.py` | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_an_installed_version_starts_disabled_and_at_shadow_on_every_target` in `tests/unit/test_agent_lifecycle_routes.py` |
| `POST /api/v1/agents/{agent_id}/archive` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_disable_then_archive_each_move_the_agent_once_and_name_the_person` in `tests/unit/test_agent_lifecycle_routes.py` |
| `POST /api/v1/agents/{agent_id}/disable` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_disable_then_archive_each_move_the_agent_once_and_name_the_person` in `tests/unit/test_agent_lifecycle_routes.py` |
| `POST /api/v1/agents/{agent_id}/duplicate` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_a_duplicate_is_a_new_disabled_agent_from_the_same_version_with_the_same_ceiling` in `tests/unit/test_agent_lifecycle_routes.py` |
| `POST /api/v1/agents/{agent_id}/enable` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_a_disabled_agent_is_enabled_and_the_store_is_told_who_did_it` in `tests/unit/test_agent_lifecycle_routes.py` |
| `POST /api/v1/agents/{agent_id}/transfer` | `/agent-templates/:templateId`, `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/department` | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_each_move_pressed_reaches_its_row_and_one_ledger_entry_naming_the_person` in `tests/unit/test_agent_lifecycle_store.py` (database, in CI) | `test_a_transfer_hands_the_agent_to_somebody_here_and_names_who_handed_it` in `tests/unit/test_agent_lifecycle_routes.py` |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` in `tests/unit/test_suspension_store.py` (database, in CI) | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` in `tests/unit/test_suspension_store.py` (database, in CI) | `test_an_approved_suspension_is_what_resume_reads_and_a_rejected_one_is_not_run` in `tests/unit/test_suspension_store.py` (database, in CI) |
| `PUT /api/v1/agents/{agent_id}/model-pin` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_an_administrator_pins_a_model_a_rung_serves_and_it_is_written_to_the_agent` in `tests/unit/test_agent_model_routes.py` | **None.** An agent's pin is logged and not written to the audit ledger in this release. Leaf `M5.7.3`. | `test_a_pinned_model_is_tried_first_even_from_another_tier` in `tests/unit/test_model_calls.py` |
