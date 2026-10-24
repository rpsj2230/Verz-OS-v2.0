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
import { LOGO_UPLOAD_PATH } from "../../../src/setup/logo";
import { APPOINTMENT_PATH, DRAFT_PATH, DRAFT_READ_PATH, FINISH_PATH } from "../../../src/setup/wizard";
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
  "src/pages/FirstRun.tsx DRAFT_PATH": [at("POST /setup/draft", "DRAFT_PATH", DRAFT_PATH, false)],
  "src/pages/FirstRun.tsx DRAFT_READ_PATH": [
    at("POST /setup/draft/read", "DRAFT_READ_PATH", DRAFT_READ_PATH, false),
  ],
  "src/components/LogoUpload.tsx LOGO_UPLOAD_PATH": [
    at("POST /setup/logo", "LOGO_UPLOAD_PATH", LOGO_UPLOAD_PATH, false),
  ],
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
  "POST /setup/draft": {
    row: { notApplicable: "It keeps a file of the screens answered so far and writes no row." },
    audit: { notApplicable: "A draft is not a change to the install, so nothing is recorded in the ledger." },
    behaviour: t("test_setup_draft", "test_what_was_answered_is_kept_and_read_back_and_the_next_screen_is_the_first_unanswered"),
  },
  "POST /setup/draft/read": {
    row: { notApplicable: "It reads a file and writes nothing." },
    audit: { notApplicable: "Nothing changes when a draft is read, so there is nothing to record." },
    behaviour: t("test_setup_draft", "test_what_was_answered_is_kept_and_read_back_and_the_next_screen_is_the_first_unanswered"),
  },
  "POST /setup/logo": {
    row: { notApplicable: "It puts one image file beside the wizard's draft and writes no row." },
    audit: {
      notApplicable:
        "A file kept before an administrator exists is not a change to the install, and the appointment that points the logo setting at it is recorded as the appointment.",
    },
    behaviour: t("test_logo_upload", "test_an_uploaded_logo_is_kept_and_served_with_headers_that_stop_it_running"),
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
