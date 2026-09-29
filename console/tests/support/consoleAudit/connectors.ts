/**
 * What the console audit holds about the `connectors` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes, and the reads it makes only once somebody acts.
 * `support/consoleAudit.ts` collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import { CONNECTORS_API_PATH, disconnectApiPath } from "../../../src/pages/connectorsQuery";
import { probeApiPath } from "../../../src/pages/connectors/connectorProbe";
import { acceptApiPath } from "../../../src/pages/connectors/DeclarationDrift";
import { editApiPath, exportApiPath, keyApiPath } from "../../../src/pages/connectors/connectorSources";
import {
  LARK_API_PATH,
  LARK_SWITCH_OFF_API_PATH,
  LARK_TEST_API_PATH,
  LARK_WIKI_SPACES_API_PATH,
} from "../../../src/pages/larkConnectQuery";
import {
  A_SETTING_ENTRY_NO_TEST_FOLLOWS,
  at,
  type Proofs,
  type ReadAfterAnAction,
  t,
  type WriteRoute,
} from "../auditClaims";

const CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER = t(
  "test_connector_store",
  "test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record",
  true,
);

const AN_EDIT_LEAVES_TWO_ROWS_AND_TWO_LEDGER_ENTRIES = t(
  "test_connector_store",
  "test_an_edit_leaves_two_rows_one_live_two_ledger_entries_and_no_key_write",
  true,
);

const A_CONNECTED_SOURCE_IS_READ_AND_A_DISCONNECTED_ONE_IS_NOT = t(
  "test_connector_sync_run",
  "test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again",
  true,
);

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  // A source's record is read when a person presses Export record on its page.
  "GET /api/v1/console/connectors/{connector}/export": {
    screen: "/connectors/:connector",
    spelled: "exportApiPath",
    built: exportApiPath("xero"),
  },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/connectors/SourceActs.tsx disconnectApiPath(name)": [
    at("POST /api/v1/connectors/{connector}/disconnect", "disconnectApiPath", disconnectApiPath("xero")),
  ],
  "src/pages/connectors/SourceActs.tsx editApiPath(name)": [
    at("POST /api/v1/connectors/{connector}/edit", "editApiPath", editApiPath("xero")),
  ],
  "src/pages/connectors/SourceActs.tsx keyApiPath(name)": [
    at("POST /api/v1/connectors/{connector}/key", "keyApiPath", keyApiPath("xero")),
  ],
  "src/pages/connectors/DeclarationDrift.tsx acceptApiPath(name)": [
    at("POST /api/v1/connectors/{connector}/accept", "acceptApiPath", acceptApiPath("xero")),
  ],
  "src/pages/connectors/TestConnection.tsx probeApiPath(name)": [
    at("POST /api/v1/connectors/{connector}/probe", "probeApiPath", probeApiPath("xero")),
  ],
  "src/components/ConnectSource.tsx CONNECTORS_API_PATH": [at("POST /api/v1/connectors", "CONNECTORS_API_PATH", CONNECTORS_API_PATH)],
  "src/pages/connectors/LarkFlow.tsx LARK_TEST_API_PATH": [
    at("POST /api/v1/connectors/lark-app/test", "LARK_TEST_API_PATH", LARK_TEST_API_PATH),
  ],
  "src/pages/connectors/LarkFlow.tsx LARK_API_PATH": [at("POST /api/v1/connectors/lark-app", "LARK_API_PATH", LARK_API_PATH)],
  "src/pages/connectors/WikiSpaces.tsx LARK_WIKI_SPACES_API_PATH": [
    at("POST /api/v1/connectors/lark-app/wiki-spaces", "LARK_WIKI_SPACES_API_PATH", LARK_WIKI_SPACES_API_PATH),
  ],
  "src/pages/connectors/LarkCard.tsx LARK_SWITCH_OFF_API_PATH": [
    at("POST /api/v1/connectors/lark-app/switch-off", "LARK_SWITCH_OFF_API_PATH", LARK_SWITCH_OFF_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/connectors": {
    row: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    audit: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    behaviour: A_CONNECTED_SOURCE_IS_READ_AND_A_DISCONNECTED_ONE_IS_NOT,
  },
  "POST /api/v1/connectors/lark-app": {
    row: t("test_lark_connect", "test_a_save_keeps_one_credential_in_each_uses_slot_and_switches_them_on"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_lark_connect", "test_after_a_save_each_use_says_where_it_stands"),
  },
  "POST /api/v1/connectors/lark-app/test": {
    row: t("test_lark_connect", "test_a_test_records_when_it_ran_and_each_verdict_and_nothing_it_was_sent"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_lark_connect", "test_the_test_route_reports_each_use_and_writes_nothing"),
  },
  "POST /api/v1/connectors/lark-app/wiki-spaces": {
    row: t("test_lark_connect", "test_declared_spaces_are_kept_in_the_settings_table_and_read_back", true),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_lark_connect", "test_a_space_is_declared_by_its_link_or_its_id_with_the_declarer_as_steward"),
  },
  "POST /api/v1/connectors/lark-app/switch-off": {
    row: t("test_lark_connect", "test_switching_a_use_off_leaves_the_others_on_and_the_key_in_the_vault"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_lark_connect", "test_switching_the_chat_channel_off_switches_its_record_off_and_keeps_its_ids"),
  },
  "POST /api/v1/connectors/{connector}/accept": {
    row: t(
      "test_connector_store",
      "test_accepting_a_changed_declaration_keeps_its_text_and_the_ledger_names_both_digests",
      true,
    ),
    audit: t(
      "test_connector_store",
      "test_accepting_a_changed_declaration_keeps_its_text_and_the_ledger_names_both_digests",
      true,
    ),
    behaviour: t("test_connector_routes", "test_accepting_repins_the_declaration_and_the_source_is_read_again"),
  },
  "POST /api/v1/connectors/{connector}/disconnect": {
    row: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    audit: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    behaviour: A_CONNECTED_SOURCE_IS_READ_AND_A_DISCONNECTED_ONE_IS_NOT,
  },
  "POST /api/v1/connectors/{connector}/edit": {
    row: AN_EDIT_LEAVES_TWO_ROWS_AND_TWO_LEDGER_ENTRIES,
    audit: AN_EDIT_LEAVES_TWO_ROWS_AND_TWO_LEDGER_ENTRIES,
    behaviour: t("test_connector_routes", "test_an_edit_leaves_two_rows_one_live_and_the_key_where_it_was"),
  },
  "POST /api/v1/connectors/{connector}/key": {
    row: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    audit: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    behaviour: t("test_connector_routes", "test_a_replaced_key_is_a_credential_write_and_changes_no_connection"),
  },
  // A press is a request row the worker answers with an attempt row: both are asserted in the one
  // database test, and the ledger entry the press appends in the one built through every migration.
  "POST /api/v1/connectors/{connector}/probe": {
    row: t("test_connector_probe_run", "test_a_test_asked_for_is_made_once_with_the_workers_key_and_keeps_nothing", true),
    audit: t("test_connector_probe_run", "test_a_press_is_on_the_ledger_and_a_test_survives_the_downgrade", true),
    behaviour: t("test_connector_probe_run", "test_a_declined_key_is_recorded_on_the_sources_health_and_the_schedule_is_unmoved", true),
  },
};
