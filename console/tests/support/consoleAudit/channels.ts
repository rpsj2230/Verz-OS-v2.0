/**
 * What the console audit holds about the `channels` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import {
  channelApiPath,
  deliveriesApiPath,
  switchApiPath,
  testApiPath,
  unbindApiPath,
} from "../../../src/pages/channelsQuery";
import {
  A_BINDING_CHANGE_IS_AUDITED,
  at,
  type Proofs,
  type ReadAfterAnAction,
  t,
  type WriteRoute,
} from "../auditClaims";

const A_CHANNEL_RECORD_IS_KEPT_AND_SWITCHED = t(
  "test_channel_pipeline",
  "test_the_stores_keep_one_row_per_channel_and_switch_only_the_one_named",
  true,
);

const A_CHANNEL_CHANGE_IS_AUDITED = t(
  "test_channel_pipeline",
  "test_each_set_up_and_switch_leaves_one_attributed_entry_and_the_chain_verifies",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/channels/ChannelProfile.tsx channelApiPath(row.channel)": [
    at("PUT /api/v1/channels/{name}", "channelApiPath", channelApiPath("webhook")),
  ],
  "src/pages/channels/ChannelDetailPage.tsx switchApiPath(row.channel)": [
    at("POST /api/v1/channels/{name}/switch", "switchApiPath", switchApiPath("webhook")),
  ],
  "src/pages/channels/ChannelProfile.tsx testApiPath(row.channel)": [
    at("POST /api/v1/channels/{name}/test", "testApiPath", testApiPath("webhook")),
  ],
  "src/pages/channels/ChannelDashboard.tsx unbindApiPath(row.channel)": [
    at("POST /api/v1/channels/{name}/bindings/unbind", "unbindApiPath", unbindApiPath("webhook")),
  ],
};

export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = {
  // A channel's newest deliveries are read when a person opens its About view.
  "GET /api/v1/channels/{name}/deliveries": {
    screen: "/channels/:name/:view",
    spelled: "deliveriesApiPath",
    built: deliveriesApiPath("webhook"),
  },
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/channels/{name}": {
    row: A_CHANNEL_RECORD_IS_KEPT_AND_SWITCHED,
    audit: A_CHANNEL_CHANGE_IS_AUDITED,
    behaviour: t(
      "test_channel_pipeline",
      "test_a_channel_is_set_up_with_its_secret_kept_in_the_vault_and_never_sent_back",
    ),
  },
  "POST /api/v1/channels/{name}/switch": {
    row: A_CHANNEL_RECORD_IS_KEPT_AND_SWITCHED,
    audit: A_CHANNEL_CHANGE_IS_AUDITED,
    behaviour: t(
      "test_channel_pipeline",
      "test_switching_one_channel_off_stops_it_receiving_and_sending_and_leaves_another_alone",
    ),
  },
  "POST /api/v1/channels/{name}/test": {
    row: t("test_channel_pipeline", "test_a_test_message_is_sent_once_per_record_and_destination"),
    audit: {
      none: "A test message is recorded in ops.operation under its key and in ops.channel_delivery with its outcome, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION.",
    },
    behaviour: t("test_channel_pipeline", "test_a_test_message_is_sent_once_per_record_and_destination"),
  },
  "POST /api/v1/channels/{name}/bindings/unbind": {
    row: A_BINDING_CHANGE_IS_AUDITED,
    audit: A_BINDING_CHANGE_IS_AUDITED,
    behaviour: t(
      "test_channel_binding",
      "test_an_administrator_lists_who_is_bound_and_unbinds_one_and_a_stranger_is_told_nothing",
    ),
  },
};
