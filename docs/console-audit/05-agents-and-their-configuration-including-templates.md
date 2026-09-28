### Agents and their configuration, including templates

- **Screens:** `/agents`, `/agents/:agentId`, `/agents/:agentId/:tab`, `/agent-templates`, `/approvals`, `/approvals/:suspensionId`
- **Tables:** `agent.agent`, `agent.template_instance`, `agent.template_version`, `agent.upgrade_decline`, `agent.browser_envelope`, `gate.suspension`
- **Installation values:** none
- **Measured here:** 9 routes, 1 called by no screen; 2 write routes, 1 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/agent-templates` | `/agent-templates` |
| `GET /api/v1/agents` | `/agents`, `/department` |
| `GET /api/v1/agents/{agent_id}/about` | **no screen** |
| `GET /api/v1/agents/{agent_id}/workspace` | `/agents/:agentId`, `/agents/:agentId/:tab` |
| `GET /api/v1/approvals` | `/approvals` |
| `GET /api/v1/approvals/{suspension_id}` | `/approvals/:suspensionId` |
| `GET /api/v1/console/agents/{agent_id}/stats` | `/agents`, `/agents/:agentId` |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` |
| `PUT /api/v1/agents/{agent_id}/model-pin` | `/agents/:agentId`, `/agents/:agentId/:tab` |

- **Gap.** An agent cannot be created, and its manifest, leash and procedure cannot be edited. Recorded: components/ManifestForm.tsx and components/ProcedureCanvas.tsx are built and tested and rendered by no registered page, and no route writes agent.agent or a template version from the console.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/approvals/{suspension_id}/decision` | `/approvals`, `/approvals/:suspensionId` | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` in `tests/unit/test_suspension_store.py` (database, in CI) | `test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart` in `tests/unit/test_suspension_store.py` (database, in CI) | `test_an_approved_suspension_is_what_resume_reads_and_a_rejected_one_is_not_run` in `tests/unit/test_suspension_store.py` (database, in CI) |
| `PUT /api/v1/agents/{agent_id}/model-pin` | `/agents/:agentId`, `/agents/:agentId/:tab` | `test_an_administrator_pins_a_model_a_rung_serves_and_it_is_written_to_the_agent` in `tests/unit/test_agent_model_routes.py` | **None.** An agent's pin is logged and not written to the audit ledger in this release. Leaf `M5.7.3`. | `test_a_pinned_model_is_tried_first_even_from_another_tier` in `tests/unit/test_model_calls.py` |
