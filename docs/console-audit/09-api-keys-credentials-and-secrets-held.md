### API keys, credentials and secrets, held in the vault and never displayed

- **Screens:** `/credentials`, `/credentials/:family/:name`, `/credentials/:family/:name/:view`, `/webhooks`, `/vault`, `/models`
- **Tables:** `ops.credential_write`, `ops.vault_access`
- **Installation values:** none
- **Measured here:** 4 routes, 0 called by no screen; 1 write routes, 1 with all three proofs; 0 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/credentials` | `/credentials` |
| `GET /api/v1/credentials/{family}/{name}` | `/credentials/:family/:name`, `/credentials/:family/:name/:view` |
| `GET /api/v1/vault` | `/vault` |
| `PUT /api/v1/credentials/{family}/{name}` | `/credentials/:family/:name`, `/credentials/:family/:name/:view`, `/models` |

No gap recorded.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `PUT /api/v1/credentials/{family}/{name}` | `/credentials/:family/:name`, `/credentials/:family/:name/:view`, `/models` | `test_setting_a_key_writes_the_slot_and_answers_that_it_is_held_and_when` in `tests/unit/test_credential_routes.py` | `test_a_key_set_from_the_console_is_recorded_as_its_setter_with_their_reach_and_trace` in `tests/unit/test_credential_routes.py` | `test_a_key_kept_here_is_handed_to_this_process_unless_the_environment_outranks_it` in `tests/unit/test_credentials.py` |
