### Notifications and email

- **Screens:** `/subscribers`, `/notifications`
- **Tables:** `ops.outbox_event`, `ops.outbox_delivery`
- **Installation values:** `INSTALL_SENDER_ADDRESS`
- **Measured here:** 7 routes, 0 called by no screen; 5 write routes, 2 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/govern/subscribers` | `/subscribers` |
| `GET /api/v1/notifications` | `/notifications` |
| `POST /api/v1/notifications/notices/{kind}` | `/notifications` |
| `POST /api/v1/notifications/relay` | `/notifications` |
| `POST /api/v1/notifications/relay/password` | `/notifications` |
| `POST /api/v1/notifications/relay/removal` | `/notifications` |
| `POST /api/v1/notifications/relay/test` | `/notifications` |

- **Gap.** No notice is sent to a person yet. Recorded: Every notice but the re-verification request is composed and called by nothing, and that one reaches webhook subscribers; the Notifications screen says so per notice from brain.ops.notices, and a sender added for any of them asks its switch.
- **Gap.** INSTALL_SENDER_ADDRESS is read by nothing that sends. Recorded: The relay's sender address is saved on the Notifications screen, and the install value is only shown on the Install screen.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/notifications/notices/{kind}` | `/notifications` | `test_switching_a_notice_off_writes_its_row_with_the_writer_and_the_next_read_sees_it` in `tests/unit/test_notification_routes.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_switched_off_a_re_verification_run_records_nothing_and_switched_on_it_does` in `tests/unit/test_notices.py` (database, in CI) |
| `POST /api/v1/notifications/relay` | `/notifications` | `test_a_relay_is_saved_as_five_rows_with_its_writer_and_read_back_configured` in `tests/unit/test_notification_routes.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password` in `tests/unit/test_notification_routes.py` |
| `POST /api/v1/notifications/relay/password` | `/notifications` | `test_a_password_is_kept_at_its_slot_recorded_and_never_answered` in `tests/unit/test_notification_routes.py` | `test_a_password_is_kept_at_its_slot_recorded_and_never_answered` in `tests/unit/test_notification_routes.py` | `test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password` in `tests/unit/test_notification_routes.py` |
| `POST /api/v1/notifications/relay/removal` | `/notifications` | `test_removing_the_relay_retires_its_rows_names_who_did_and_the_next_read_is_unconfigured` in `tests/unit/test_notification_routes.py` | `test_removing_the_relay_retires_its_rows_as_the_application_and_names_the_remover` in `tests/unit/test_console_control_audit.py` (database, in CI) | `test_removing_the_relay_retires_its_rows_names_who_did_and_the_next_read_is_unconfigured` in `tests/unit/test_notification_routes.py` |
| `POST /api/v1/notifications/relay/test` | `/notifications` | `test_pressing_the_test_button_twice_sends_one_message` in `tests/unit/test_mail.py` | **None.** A test message is recorded in ops.operation under its key, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION. | `test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password` in `tests/unit/test_notification_routes.py` |
