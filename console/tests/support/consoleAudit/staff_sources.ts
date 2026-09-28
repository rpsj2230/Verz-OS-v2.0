/**
 * What the console audit holds about the `staff_sources` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes, and the reads it makes only once somebody acts.
 * `support/consoleAudit.ts` collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import {
  APPLY_FIRST_SYNC_API_PATH,
  CONNECT_API_PATH,
  CONNECTION_TEST_API_PATH,
  CREDENTIAL_API_PATH,
  FIRST_SYNC_API_PATH,
  transferApiPath,
  TRIAL_API_PATH,
} from "../../../src/pages/staffSourcesQuery";
import { at, type Proofs, type ReadAfterAnAction, t, type WriteRoute } from "../auditClaims";

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  "GET /api/v1/govern/staff_sources/trial": { screen: "/staff_sources", spelled: "TRIAL_API_PATH", built: TRIAL_API_PATH },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/StaffSources.tsx CREDENTIAL_API_PATH": [
    at("PUT /api/v1/govern/staff_sources/credential", "CREDENTIAL_API_PATH", CREDENTIAL_API_PATH),
  ],
  "src/pages/StaffSources.tsx transferApiPath(agentId)": [
    at("POST /api/v1/govern/staff_sources/transfers/{agent_id}", "transferApiPath", transferApiPath("a_quotes")),
  ],
  "src/components/ConnectStaffSource.tsx path": [
    at("POST /api/v1/govern/staff_sources/test", "CONNECTION_TEST_API_PATH", CONNECTION_TEST_API_PATH),
    at("POST /api/v1/govern/staff_sources/first-sync", "FIRST_SYNC_API_PATH", FIRST_SYNC_API_PATH),
  ],
  "src/components/ConnectStaffSource.tsx CONNECT_API_PATH": [
    at("POST /api/v1/govern/staff_sources/connect", "CONNECT_API_PATH", CONNECT_API_PATH),
  ],
  "src/components/ConnectStaffSource.tsx APPLY_FIRST_SYNC_API_PATH": [
    at("POST /api/v1/govern/staff_sources/first-sync/apply", "APPLY_FIRST_SYNC_API_PATH", APPLY_FIRST_SYNC_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/govern/staff_sources/credential": {
    row: t("test_staff_sync_routes", "test_the_credential_is_replaced_into_its_slot_recorded_and_never_sent_back"),
    audit: t(
      "test_credential_writes",
      "test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds",
      true,
    ),
    behaviour: t("test_staff_sync_run", "test_a_scheduled_run_reads_lark_with_the_kept_credential_and_applies_the_plan"),
  },
  "POST /api/v1/govern/staff_sources/transfers/{agent_id}": {
    row: t(
      "test_staff_sync_routes",
      "test_taking_a_leavers_agent_moves_the_owner_starts_it_again_and_never_widens_its_reach",
    ),
    audit: t("test_staff_connect", "test_the_owner_change_trigger_writes_the_details_the_recorder_writes"),
    behaviour: t(
      "test_staff_sync_routes",
      "test_taking_a_leavers_agent_moves_the_owner_starts_it_again_and_never_widens_its_reach",
    ),
  },
  "POST /api/v1/govern/staff_sources/test": {
    row: { notApplicable: "A connection test keeps nothing: no setting, no credential and no member is written." },
    audit: { notApplicable: "A connection test is not a change to the system, so there is nothing to record." },
    behaviour: t("test_staff_connect", "test_the_test_route_keeps_nothing_and_never_sends_the_secret_back"),
  },
  "POST /api/v1/govern/staff_sources/connect": {
    row: t(
      "test_staff_connect",
      "test_connecting_keeps_the_credential_in_its_slot_saves_two_settings_and_echoes_nothing",
    ),
    audit: t(
      "test_credential_writes",
      "test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds",
      true,
    ),
    behaviour: t(
      "test_staff_sync_run",
      "test_a_source_saved_on_the_screen_is_the_source_the_worker_reads_with_no_server_edit",
    ),
  },
  "POST /api/v1/govern/staff_sources/first-sync": {
    row: { notApplicable: "The first sync's dry run reads the directory and the roster and writes nothing." },
    audit: { notApplicable: "A dry run is not a change to the system, so there is nothing to record." },
    behaviour: t(
      "test_staff_connect",
      "test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed",
    ),
  },
  "POST /api/v1/govern/staff_sources/first-sync/apply": {
    row: t(
      "test_staff_connect",
      "test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed",
    ),
    audit: {
      notApplicable:
        "Applying the first sync is the nightly run started now, and a run is recorded on its own row in auth.staff_sync_run, which the screen lists; no ledger member records a roster run.",
    },
    behaviour: t(
      "test_staff_sync_store",
      "test_the_night_that_marks_a_leaver_stops_their_agents_and_nobody_elses",
      true,
    ),
  },
};
