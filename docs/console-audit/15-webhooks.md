### Webhooks

- **Screens:** `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view`
- **Tables:** `ops.webhook_subscriber`, `ops.webhook_change`
- **Installation values:** none
- **Measured here:** 4 routes, 0 called by no screen; 3 write routes, 3 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/webhooks` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` |
| `POST /api/v1/webhooks/subscribers` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/secret` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` |

- **Gap.** No vendor platform's webhook is received, only the company's own signed webhook. Recorded: Only brain.channels.webhook has a wire in this release, and the WhatsApp and Lark checks are not written; each channel's About view says whether its check is written, from brain.ops.inbound_webhooks.INBOUND as the Webhooks route serves it.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/webhooks/subscribers` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` | `test_a_registration_is_written_with_the_reader_as_its_creator_and_its_secret_kept` in `tests/unit/test_webhook_routes.py` | `test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_a_due_event_is_signed_received_verified_and_recorded_delivered` in `tests/unit/test_webhook_delivery.py` (database, in CI) |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/secret` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` | `test_replacing_a_secret_writes_the_new_one_and_a_switched_off_subscriber_is_refused` in `tests/unit/test_webhook_routes.py` | `test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_the_worker_reads_the_secret_at_the_path_the_console_writes_it_to` in `tests/unit/test_webhook_delivery.py` |
| `POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off` | `/webhooks`, `/webhooks/:id`, `/webhooks/:id/:view` | `test_switching_off_records_who_did_it_and_a_second_switch_off_is_refused` in `tests/unit/test_webhook_routes.py` | `test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_registering_replacing_and_switching_off_reach_the_rows_and_the_fan_out` in `tests/unit/test_webhook_store.py` (database, in CI) |
