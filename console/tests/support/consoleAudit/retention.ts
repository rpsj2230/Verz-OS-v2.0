/**
 * What the console audit holds about the `retention` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import {
  ERASURES_API_PATH,
  HOLD_API_PATH,
  LIFT_API_PATH,
  RELEASE_API_PATH,
  WITHDRAWAL_API_PATH,
} from "../../../src/pages/retentionQuery";
import { at, audited, type Proofs, t, type WriteRoute } from "../auditClaims";

const HOLDS_SWEPT = audited("test_a_hold_placed_through_the_store_keeps_its_rows_from_the_sweep_and_lifted_releases_them");

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Retention.tsx path": [
    at("POST /api/v1/govern/retention/release", "RELEASE_API_PATH", RELEASE_API_PATH),
    at("POST /api/v1/govern/retention/withdrawal", "WITHDRAWAL_API_PATH", WITHDRAWAL_API_PATH),
    at("POST /api/v1/govern/legal-holds", "HOLD_API_PATH", HOLD_API_PATH),
    at("POST /api/v1/govern/legal-holds/lift", "LIFT_API_PATH", LIFT_API_PATH),
    at("POST /api/v1/govern/erasures", "ERASURES_API_PATH", ERASURES_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/retention/release": {
    row: t("test_retention_store", "test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: t("test_worker_schedule", "test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report", true),
  },
  "POST /api/v1/govern/retention/withdrawal": {
    row: t("test_retention_store", "test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: t("test_worker_schedule", "test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report", true),
  },
  "POST /api/v1/govern/legal-holds": {
    row: t("test_retention_store", "test_a_hold_is_placed_lifted_once_and_kept", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: HOLDS_SWEPT,
  },
  "POST /api/v1/govern/legal-holds/lift": {
    row: t("test_retention_store", "test_a_hold_is_placed_lifted_once_and_kept", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: HOLDS_SWEPT,
  },
  "POST /api/v1/govern/erasures": {
    row: t("test_erasure_store", "test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished", true),
    audit: t("test_erasure_store", "test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished", true),
    behaviour: t("test_erasure_store", "test_the_queue_carries_a_request_out_and_writes_what_each_store_did_and_what_it_could_not", true),
  },
};
