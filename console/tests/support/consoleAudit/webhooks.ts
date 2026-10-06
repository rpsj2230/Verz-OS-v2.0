/**
 * What the console audit holds about the `webhooks` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { REGISTER_API_PATH, replayApiPath, secretApiPath, switchOffApiPath, switchOnApiPath } from "../../../src/pages/webhooksQuery";
import { at, audited, type Proofs, t, type WriteRoute } from "../auditClaims";

const WEBHOOK_LEDGER = audited("test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author");

const SWITCHED_ON_AND_REPLAYED = t(
  "test_webhook_store",
  "test_switched_back_on_and_a_given_up_delivery_replayed_once_reach_the_rows",
  true,
);

const A_WEBHOOK_IS_DELIVERED = t(
  "test_webhook_delivery",
  "test_a_due_event_is_signed_received_verified_and_recorded_delivered",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/webhooks/WebhookActs.tsx REGISTER_API_PATH": [at("POST /api/v1/webhooks/subscribers", "REGISTER_API_PATH", REGISTER_API_PATH)],
  "src/pages/webhooks/WebhookActs.tsx secretApiPath(subscriberId)": [
    at("POST /api/v1/webhooks/subscribers/{subscriber_id}/secret", "secretApiPath", secretApiPath("billing_bridge")),
  ],
  "src/pages/webhooks/WebhookActs.tsx switchOffApiPath(subscriberId)": [
    at("POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off", "switchOffApiPath", switchOffApiPath("billing_bridge")),
  ],
  "src/pages/webhooks/WebhookActs.tsx switchOnApiPath(subscriberId)": [
    at("POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-on", "switchOnApiPath", switchOnApiPath("billing_bridge")),
  ],
  'src/pages/webhooks/WebhookActs.tsx replayApiPath(subscriberId, delivery.replay ?? "")': [
    at(
      "POST /api/v1/webhooks/subscribers/{subscriber_id}/deliveries/{handle}/replay",
      "replayApiPath",
      replayApiPath("billing_bridge", "0123456789abcdef0123456789abcdef"),
    ),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/webhooks/subscribers": {
    row: t("test_webhook_routes", "test_a_registration_is_written_with_the_reader_as_its_creator_and_its_secret_kept"),
    audit: WEBHOOK_LEDGER,
    behaviour: A_WEBHOOK_IS_DELIVERED,
  },
  "POST /api/v1/webhooks/subscribers/{subscriber_id}/secret": {
    row: t("test_webhook_routes", "test_replacing_a_secret_writes_the_new_one_and_a_switched_off_subscriber_is_refused"),
    audit: WEBHOOK_LEDGER,
    behaviour: t("test_webhook_delivery", "test_the_worker_reads_the_secret_at_the_path_the_console_writes_it_to"),
  },
  "POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off": {
    row: t("test_webhook_routes", "test_switching_off_records_who_did_it_and_a_second_switch_off_is_refused"),
    audit: WEBHOOK_LEDGER,
    behaviour: t("test_webhook_store", "test_registering_replacing_and_switching_off_reach_the_rows_and_the_fan_out", true),
  },
  "POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-on": {
    row: t("test_webhook_routes", "test_switching_back_on_records_who_did_it_and_a_subscriber_already_on_is_refused"),
    audit: SWITCHED_ON_AND_REPLAYED,
    behaviour: SWITCHED_ON_AND_REPLAYED,
  },
  "POST /api/v1/webhooks/subscribers/{subscriber_id}/deliveries/{handle}/replay": {
    row: t("test_webhook_routes", "test_a_delivery_given_up_is_replayed_once_by_the_name_the_screen_was_given"),
    audit: SWITCHED_ON_AND_REPLAYED,
    behaviour: SWITCHED_ON_AND_REPLAYED,
  },
};
