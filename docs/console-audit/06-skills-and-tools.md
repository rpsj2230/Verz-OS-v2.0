### Skills and tools

- **Screens:** `/skills`, `/skills/:name`, `/tools`
- **Tables:** `agent.skill`, `agent.skill_review`, `agent.skill_assignment`, `agent.tool_definition`, `agent.tool_switch`, `agent.skill_category`
- **Installation values:** `INSTALL_ACCEPTANCE_SKILL_SOURCE`
- **Measured here:** 10 routes, 1 called by no screen; 7 write routes, 7 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/skills/{skill_name}/stats` | **no screen** |
| `GET /api/v1/skills` | `/skills`, `/skills/:name` |
| `GET /api/v1/tools` | `/tools` |
| `POST /api/v1/skills` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/imports` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/{digest}/categories` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/{digest}/review` | `/skills`, `/skills/:name` |
| `POST /api/v1/skills/{digest}/versions` | `/skills`, `/skills/:name` |
| `POST /api/v1/tools/{name}/switch` | `/tools` |

- **Gap.** A skill cannot be removed from an agent from the console, only replaced by another version of it. Recorded: brain.console.agent_tabs.detach decides a removal and no route performs one; brain.skill_routes assigns and replaces.
- **Gap.** A skill that declares scripts cannot be added. Recorded: brain.tools.skills.Skill.digest covers a script's name and not its bytes, so an approval would not cover the code, and brain.tools.run_skill has no runner; brain.console.skill_library refuses one at the door.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/skills` | `/skills`, `/skills/:name` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/imports` | `/skills`, `/skills/:name` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_imports_a_skill_from_a_repository_at_a_commit_and_it_waits` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/assignments` | `/skills`, `/skills/:name` | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` | `test_the_database_refuses_an_unsaid_self_decision_and_an_assignment_nobody_approved` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/categories` | `/skills`, `/skills/:name` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_categories_set_on_a_skill_are_chips_that_filter_the_skills_in_use` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/review` | `/skills`, `/skills/:name` | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/skills/{digest}/versions` | `/skills`, `/skills/:name` | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_every_way_in_an_edit_a_self_approval_and_categories_reach_the_ledger` in `tests/unit/test_skill_store.py` (database, in CI) | `test_an_edit_waits_for_review_as_a_new_version_while_the_agent_keeps_its_pin` in `tests/unit/test_skill_routes.py` |
| `POST /api/v1/tools/{name}/switch` | `/tools` | `test_a_super_administrator_switches_a_tool_off_for_the_install` in `tests/unit/test_tool_routes.py` | `test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call` in `tests/unit/test_tool_routes.py` (database, in CI) | `test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call` in `tests/unit/test_tool_routes.py` (database, in CI) |
