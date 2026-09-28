/**
 * What the console audit holds about the `connectors` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes, and the reads it makes only once somebody acts.
 * `support/consoleAudit.ts` collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import { CONNECTORS_API_PATH, disconnectApiPath } from "../../../src/pages/connectorsQuery";
import { editApiPath, exportApiPath, keyApiPath } from "../../../src/pages/connectors/connectorSources";
import { LARK_API_PATH, LARK_TEST_API_PATH } from "../../../src/pages/larkConnectQuery";
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
  "src/components/ConnectSource.tsx CONNECTORS_API_PATH": [at("POST /api/v1/connectors", "CONNECTORS_API_PATH", CONNECTORS_API_PATH)],
  "src/components/ConnectLark.tsx LARK_TEST_API_PATH": [
    at("POST /api/v1/connectors/lark-app/test", "LARK_TEST_API_PATH", LARK_TEST_API_PATH),
  ],
  "src/components/ConnectLark.tsx LARK_API_PATH": [at("POST /api/v1/connectors/lark-app", "LARK_API_PATH", LARK_API_PATH)],
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
    row: { notApplicable: "A Lark test writes no row here or in Lark: every request after the token exchange is a read, which the fake Lark server records." },
    audit: { notApplicable: "Nothing is written, so there is nothing for the ledger to record, and the secret is never logged." },
    behaviour: t("test_lark_connect", "test_the_test_route_reports_each_use_and_writes_nothing"),
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
};
