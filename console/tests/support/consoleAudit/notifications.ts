/**
 * What the console audit holds about the `notifications` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import {
  noticeApiPath,
  PASSWORD_API_PATH as RELAY_PASSWORD_API_PATH,
  RELAY_API_PATH,
  REMOVAL_API_PATH as RELAY_REMOVAL_API_PATH,
  TRIAL_API_PATH as RELAY_TRIAL_API_PATH,
} from "../../../src/pages/notificationsQuery";
import { A_SETTING_ENTRY_NO_TEST_FOLLOWS, at, type Proof, type Proofs, t, type WriteRoute } from "../auditClaims";

const NO_TRIAL_LEDGER: Proof = {
  none: "A test message is recorded in ops.operation under its key, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION.",
};

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/notifications/RelayActs.tsx noticeApiPath(row.kind)": [
    at("POST /api/v1/notifications/notices/{kind}", "noticeApiPath", noticeApiPath("evening_digest")),
  ],
  "src/pages/notifications/RelayActs.tsx RELAY_API_PATH": [at("POST /api/v1/notifications/relay", "RELAY_API_PATH", RELAY_API_PATH)],
  "src/pages/notifications/RelayActs.tsx REMOVAL_API_PATH": [
    at("POST /api/v1/notifications/relay/removal", "REMOVAL_API_PATH", RELAY_REMOVAL_API_PATH),
  ],
  "src/pages/notifications/RelayActs.tsx PASSWORD_API_PATH": [
    at("POST /api/v1/notifications/relay/password", "PASSWORD_API_PATH", RELAY_PASSWORD_API_PATH),
  ],
  "src/pages/notifications/RelayActs.tsx TRIAL_API_PATH": [
    at("POST /api/v1/notifications/relay/test", "TRIAL_API_PATH", RELAY_TRIAL_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/notifications/notices/{kind}": {
    row: t("test_notification_routes", "test_switching_a_notice_off_writes_its_row_with_the_writer_and_the_next_read_sees_it"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_notices", "test_switched_off_a_re_verification_run_records_nothing_and_switched_on_it_does", true),
  },
  "POST /api/v1/notifications/relay": {
    row: t("test_notification_routes", "test_a_relay_is_saved_as_five_rows_with_its_writer_and_read_back_configured"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_notification_routes", "test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password"),
  },
  "POST /api/v1/notifications/relay/removal": {
    row: t(
      "test_notification_routes",
      "test_removing_the_relay_retires_its_rows_names_who_did_and_the_next_read_is_unconfigured",
    ),
    audit: t(
      "test_console_control_audit",
      "test_removing_the_relay_retires_its_rows_as_the_application_and_names_the_remover",
      true,
    ),
    behaviour: t(
      "test_notification_routes",
      "test_removing_the_relay_retires_its_rows_names_who_did_and_the_next_read_is_unconfigured",
    ),
  },
  "POST /api/v1/notifications/relay/password": {
    row: t("test_notification_routes", "test_a_password_is_kept_at_its_slot_recorded_and_never_answered"),
    audit: t("test_notification_routes", "test_a_password_is_kept_at_its_slot_recorded_and_never_answered"),
    behaviour: t("test_notification_routes", "test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password"),
  },
  "POST /api/v1/notifications/relay/test": {
    row: t("test_mail", "test_pressing_the_test_button_twice_sends_one_message"),
    audit: NO_TRIAL_LEDGER,
    behaviour: t("test_notification_routes", "test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password"),
  },
};
