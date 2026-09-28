/**
 * What the console audit holds about the `me` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { myCodeApiPath, myUnbindApiPath } from "../../../src/pages/channelsQuery";
import { A_BINDING_CHANGE_IS_AUDITED, at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/components/MyChannels.tsx myCodeApiPath(row.channel)": [
    at("POST /api/v1/me/channels/{name}/code", "myCodeApiPath", myCodeApiPath("webhook")),
  ],
  "src/components/MyChannels.tsx myUnbindApiPath(row.channel)": [
    at("POST /api/v1/me/channels/{name}/unbind", "myUnbindApiPath", myUnbindApiPath("webhook")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/me/channels/{name}/code": {
    row: t(
      "test_channel_binding",
      "test_a_code_is_kept_spent_once_and_never_brought_back_by_the_application",
      true,
    ),
    audit: {
      notApplicable: "A code binds nothing until its person sends it from a chat, and the binding it then makes is the channel_binding entry 0118's trigger appends; minting one changes nobody's access.",
    },
    behaviour: t(
      "test_channel_binding",
      "test_a_person_mints_a_code_in_my_workspace_sends_it_and_is_answered_as_themself",
    ),
  },
  "POST /api/v1/me/channels/{name}/unbind": {
    row: A_BINDING_CHANGE_IS_AUDITED,
    audit: A_BINDING_CHANGE_IS_AUDITED,
    behaviour: t("test_channel_binding", "test_a_person_unbinds_their_own_chat_and_it_is_recorded_as_theirs"),
  },
};
