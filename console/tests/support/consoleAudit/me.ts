/**
 * What the console audit holds about the `me` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { myCodeApiPath, myUnbindApiPath } from "../../../src/pages/channelsQuery";
import { EDIT_API_PATH, FORGET_API_PATH } from "../../../src/pages/myWorkspaceQuery";
import { A_BINDING_CHANGE_IS_AUDITED, at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/components/MyChannels.tsx myCodeApiPath(row.channel)": [
    at("POST /api/v1/me/channels/{name}/code", "myCodeApiPath", myCodeApiPath("webhook")),
  ],
  "src/components/MyChannels.tsx myUnbindApiPath(row.channel)": [
    at("POST /api/v1/me/channels/{name}/unbind", "myUnbindApiPath", myUnbindApiPath("webhook")),
  ],
  "src/pages/MyWorkspace.tsx FORGET_API_PATH": [
    at("POST /api/v1/me/memory/forget", "FORGET_API_PATH", FORGET_API_PATH),
  ],
  "src/pages/MyWorkspace.tsx EDIT_API_PATH": [at("POST /api/v1/me/memory/edit", "EDIT_API_PATH", EDIT_API_PATH)],
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
  // A forget is the Learning screen's undo written for the person the memory is about, through the
  // same store, so the same database test follows it to the row, the ledger and the next recall.
  "POST /api/v1/me/memory/forget": {
    row: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    audit: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    behaviour: t("test_mine_routes", "test_a_member_forgets_a_memory_formed_from_their_own_words"),
  },
  "POST /api/v1/me/memory/edit": {
    row: t("test_memory_store", "test_an_edit_reaches_the_rows_the_ledger_and_what_is_recalled_next", true),
    audit: t("test_memory_store", "test_an_edit_reaches_the_rows_the_ledger_and_what_is_recalled_next", true),
    behaviour: t(
      "test_mine_routes",
      "test_a_member_edits_a_memory_and_the_replacement_changes_the_words_and_nothing_else",
    ),
  },
};
