### Prompts and system instructions

- **Screens:** `/prompts`
- **Tables:** none
- **Installation values:** none
- **Measured here:** 3 routes, 0 called by no screen; 2 write routes, 2 with all three proofs; 0 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/prompts` | `/prompts` |
| `POST /api/v1/govern/prompts/{agent_id}` | `/prompts` |
| `POST /api/v1/govern/prompts/{agent_id}/give-back` | `/prompts` |

No gap recorded.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/govern/prompts/{agent_id}` | `/prompts` | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) |
| `POST /api/v1/govern/prompts/{agent_id}/give-back` | `/prompts` | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt` in `tests/unit/test_console_control_audit.py` (database, in CI) |
