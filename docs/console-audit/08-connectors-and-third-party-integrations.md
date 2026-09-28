### Connectors and third-party integrations

- **Screens:** `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view`, `/channels`
- **Tables:** `auth.binding_code`, `ops.channel`, `ops.channel_delivery`, `ops.connector_connection`, `ops.connector_sync`, `proj.record`, `er.alias`, `er.canonical`, `er.identifier`, `er.link`
- **Installation values:** `INSTALL_LARK_USES`, `INSTALL_LARK_PLATFORM`, `INSTALL_LARK_BASE`
- **Measured here:** 25 routes, 2 called by no screen; 12 write routes, 10 with all three proofs; 6 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/channels` | `/channels` |
| `GET /api/v1/channels/{name}/bindings` | `/channels` |
| `GET /api/v1/channels/{name}/deliveries` | `/channels` |
| `GET /api/v1/channels/{name}/health` | `/channels` |
| `GET /api/v1/connectors` | `/`, `/connectors`, `/connectors/:connector`, `/connectors/:connector/:view` |
| `GET /api/v1/connectors/lark-app` | `/connectors` |
| `GET /api/v1/console/channels/{name}/stats` | **no screen** |
| `GET /api/v1/console/connectors` | `/connectors` |
| `GET /api/v1/console/connectors/{connector}` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `GET /api/v1/console/connectors/{connector}/export` | `/connectors/:connector` |
| `GET /api/v1/console/connectors/{connector}/stats` | `/connectors`, `/connectors/:connector` |
| `GET /api/v1/me/channels` | `/me` |
| `POST /api/v1/channels/{name}/bindings/unbind` | `/channels` |
| `POST /api/v1/channels/{name}/events` | **no screen** |
| `POST /api/v1/channels/{name}/switch` | `/channels` |
| `POST /api/v1/channels/{name}/test` | `/channels` |
| `POST /api/v1/connectors` | `/connectors/:connector`, `/connectors/:connector/:view`, `/first-run` |
| `POST /api/v1/connectors/lark-app` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/connectors/lark-app/test` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/connectors/{connector}/disconnect` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/connectors/{connector}/edit` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/connectors/{connector}/key` | `/connectors/:connector`, `/connectors/:connector/:view` |
| `POST /api/v1/me/channels/{name}/code` | `/me` |
| `POST /api/v1/me/channels/{name}/unbind` | `/me` |
| `PUT /api/v1/channels/{name}` | `/channels` |

- **Gap.** A connected source is read and kept, and no question is answered from what is kept. Recorded: No row tool is registered for a connected source's records: brain.tools.startup.classification_for is keyed on the entity alone and Xero and HubSpot both project contact, which that module records as the limit to change first. brain.ops.connector_admin.WHAT_CONNECTING_A_SOURCE_STARTS says so in the connect confirmation.
- **Gap.** A connection cannot be tested from the console yet: only the worker reads a source's key, and a successful probe has no outcome ops.connector_sync can hold without claiming a full read. Open leaf `M27.15.8`.
- **Gap.** HubSpot can be connected and is not read. Recorded: brain.ops.limits records no verified call ceiling for it and brain.connectors.throttle.limits_for refuses to invent one; its row carries brain.ops.connector_sync.NO_VERIFIED_CEILING.
- **Gap.** Google Drive and the Laravel views cannot be connected from a screen. Recorded: Each needs a visibility rule, a department declaration with an answerable person, or a key file the form cannot collect, which brain.ops.connectable.NOT_FROM_THE_CONSOLE says for each. Freshdesk is connected from the screen with its address and the one department that reads it (brain.connectors.freshdesk.ONE_DEPARTMENT_READS_A_CONNECTED_HELPDESK).
- **Gap.** Connect Lark switches knowledge from Wiki and Base on, and no question is answered from Lark yet. Recorded: The Lark knowledge connector that keeps the minimal index and reads pages and records live is still to be built over the settings Connect Lark writes; brain.ops.lark_connect.KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED says so on the screen.
- **Gap.** A Lark account is linked to a person with a one-time code only once the binding store is wired. Recorded: The chat channel receives, verifies and answers Lark's events at /api/v1/channels/lark/events, and offers a code sent in a direct message to brain.channels.inbound.ChatBinder; the store that mints the code in a web session and keeps the binding is the channel binding package's, and until it is wired every sender is answered as unbound, brain.channels.inbound.NOBODY_IS_BOUND_UNTIL_A_BINDING_IS_KEPT.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/channels/{name}/bindings/unbind` | `/channels` | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_an_administrator_lists_who_is_bound_and_unbinds_one_and_a_stranger_is_told_nothing` in `tests/unit/test_channel_binding.py` |
| `POST /api/v1/channels/{name}/switch` | `/channels` | `test_the_stores_keep_one_row_per_channel_and_switch_only_the_one_named` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_each_set_up_and_switch_leaves_one_attributed_entry_and_the_chain_verifies` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_switching_one_channel_off_stops_it_receiving_and_sending_and_leaves_another_alone` in `tests/unit/test_channel_pipeline.py` |
| `POST /api/v1/channels/{name}/test` | `/channels` | `test_a_test_message_is_sent_once_per_record_and_destination` in `tests/unit/test_channel_pipeline.py` | **None.** A test message is recorded in ops.operation under its key and in ops.channel_delivery with its outcome, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION. | `test_a_test_message_is_sent_once_per_record_and_destination` in `tests/unit/test_channel_pipeline.py` |
| `POST /api/v1/connectors` | `/connectors/:connector`, `/connectors/:connector/:view`, `/first-run` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again` in `tests/unit/test_connector_sync_run.py` (database, in CI) |
| `POST /api/v1/connectors/lark-app` | `/connectors/:connector`, `/connectors/:connector/:view` | `test_a_save_keeps_one_credential_in_each_uses_slot_and_switches_them_on` in `tests/unit/test_lark_connect.py` | **None.** The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry. | `test_after_a_save_each_use_says_where_it_stands` in `tests/unit/test_lark_connect.py` |
| `POST /api/v1/connectors/lark-app/test` | `/connectors/:connector`, `/connectors/:connector/:view` | Not applicable: A Lark test writes no row here or in Lark: every request after the token exchange is a read, which the fake Lark server records. | Not applicable: Nothing is written, so there is nothing for the ledger to record, and the secret is never logged. | `test_the_test_route_reports_each_use_and_writes_nothing` in `tests/unit/test_lark_connect.py` |
| `POST /api/v1/connectors/{connector}/disconnect` | `/connectors/:connector`, `/connectors/:connector/:view` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again` in `tests/unit/test_connector_sync_run.py` (database, in CI) |
| `POST /api/v1/connectors/{connector}/edit` | `/connectors/:connector`, `/connectors/:connector/:view` | `test_an_edit_leaves_two_rows_one_live_two_ledger_entries_and_no_key_write` in `tests/unit/test_connector_store.py` (database, in CI) | `test_an_edit_leaves_two_rows_one_live_two_ledger_entries_and_no_key_write` in `tests/unit/test_connector_store.py` (database, in CI) | `test_an_edit_leaves_two_rows_one_live_and_the_key_where_it_was` in `tests/unit/test_connector_routes.py` |
| `POST /api/v1/connectors/{connector}/key` | `/connectors/:connector`, `/connectors/:connector/:view` | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record` in `tests/unit/test_connector_store.py` (database, in CI) | `test_a_replaced_key_is_a_credential_write_and_changes_no_connection` in `tests/unit/test_connector_routes.py` |
| `POST /api/v1/me/channels/{name}/code` | `/me` | `test_a_code_is_kept_spent_once_and_never_brought_back_by_the_application` in `tests/unit/test_channel_binding.py` (database, in CI) | Not applicable: A code binds nothing until its person sends it from a chat, and the binding it then makes is the channel_binding entry 0118's trigger appends; minting one changes nobody's access. | `test_a_person_mints_a_code_in_my_workspace_sends_it_and_is_answered_as_themself` in `tests/unit/test_channel_binding.py` |
| `POST /api/v1/me/channels/{name}/unbind` | `/me` | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies` in `tests/unit/test_channel_binding.py` (database, in CI) | `test_a_person_unbinds_their_own_chat_and_it_is_recorded_as_theirs` in `tests/unit/test_channel_binding.py` |
| `PUT /api/v1/channels/{name}` | `/channels` | `test_the_stores_keep_one_row_per_channel_and_switch_only_the_one_named` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_each_set_up_and_switch_leaves_one_attributed_entry_and_the_chain_verifies` in `tests/unit/test_channel_pipeline.py` (database, in CI) | `test_a_channel_is_set_up_with_its_secret_kept_in_the_vault_and_never_sent_back` in `tests/unit/test_channel_pipeline.py` |
