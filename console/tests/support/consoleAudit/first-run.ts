/**
 * What the console audit holds about the `first-run` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes, and the reads it makes only once somebody acts.
 * `support/consoleAudit.ts` collects this file and says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import {
  REGISTRATION_PATH as STAFF_LIST_REGISTRATION_PATH,
  SIGN_IN_PATH as STAFF_LIST_SIGN_IN_PATH,
  TRIAL_PATH as STAFF_LIST_TRIAL_PATH,
} from "../../../src/setup/staffList";
import { APPOINTMENT_PATH, FINISH_PATH } from "../../../src/setup/wizard";
import { at, type Proofs, type ReadAfterAnAction, t, type WriteRoute } from "../auditClaims";

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  "GET /setup/staff-source/registration": {
    screen: "/first-run",
    spelled: "REGISTRATION_PATH",
    built: STAFF_LIST_REGISTRATION_PATH,
    versioned: false,
  },
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/FirstRun.tsx FINISH_PATH": [at("POST /setup/sign-in", "FINISH_PATH", FINISH_PATH, false)],
  "src/pages/FirstRun.tsx APPOINTMENT_PATH": [at("POST /setup/appointment", "APPOINTMENT_PATH", APPOINTMENT_PATH, false)],
  "src/components/StaffListCheck.tsx SIGN_IN_PATH": [
    at("POST /setup/staff-source/sign-in", "SIGN_IN_PATH", STAFF_LIST_SIGN_IN_PATH, false),
  ],
  "src/components/StaffListCheck.tsx TRIAL_PATH": [
    at("POST /setup/staff-source/trial", "TRIAL_PATH", STAFF_LIST_TRIAL_PATH, false),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /setup/sign-in": {
    row: t("test_sign_in_routes", "test_the_finishing_screen_binds_the_installers_sign_in_to_the_first_administrator"),
    audit: t("test_sign_in_routes", "test_the_finishing_screen_binds_the_first_administrator_once_against_the_database", true),
    behaviour: t("test_setup_routes", "test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone", true),
  },
  "POST /setup/appointment": {
    row: t("test_setup_routes", "test_the_setup_code_holder_appoints_the_first_administrator_and_is_sent_to_finish"),
    audit: t("test_first_administrator", "test_the_first_administrator_is_a_live_person_holding_administration_everywhere", true),
    behaviour: t("test_setup_routes", "test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone", true),
  },
  "POST /setup/staff-source/sign-in": {
    row: { notApplicable: "It answers the directory's own sign-in page for the setup code's holder and writes nothing." },
    audit: { notApplicable: "Nothing changes when a sign-in page is asked for, so there is nothing to record." },
    behaviour: t("test_setup_staff_routes", "test_a_directory_is_chosen_signed_in_to_and_its_list_pulled"),
  },
  "POST /setup/staff-source/trial": {
    row: t("test_setup_staff_routes", "test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync"),
    audit: t("test_setup_staff_routes", "test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync"),
    behaviour: t("test_setup_staff_routes", "test_a_directory_is_chosen_signed_in_to_and_its_list_pulled"),
  },
};
