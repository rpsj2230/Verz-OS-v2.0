/**
 * What the console audit holds about the `me` module: the writes its screens send, each mapped to
 * the routes it reaches, and the tests that follow each route to its row, its ledger entry and what
 * it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as it
 * is.
 *
 * Task ids: none
 */

import { myCodeApiPath, myUnbindApiPath } from "../../../src/pages/channelsQuery";
import { myConsentPath, myDisconnectPath } from "../../../src/pages/connectors/consentAtVendor";
import { LEARNING_UNDO_API_PATH } from "../../../src/pages/learningUndoQuery";
import { MY_DELETION_API_PATH } from "../../../src/pages/myDeletionQuery";
import {
  END_MY_DEVICE_API_PATH,
  askForAgentApiPath,
  shareApiPath,
  unshareApiPath,
} from "../../../src/pages/myAccountQuery";
import { EDIT_API_PATH, FORGET_ALL_API_PATH, FORGET_API_PATH } from "../../../src/pages/myWorkspaceQuery";
import { LEARNING_API_PATH, QUIET_API_PATH, REACH_API_PATH } from "../../../src/pages/myPreferencesQuery";
import {
  PROJECTS_API_PATH,
  addItemApiPath,
  archiveApiPath,
  removeItemApiPath,
  renameApiPath,
} from "../../../src/pages/myProjectsQuery";
import { uploadPath } from "../../../src/pages/knowledgeQuery";
import { A_BINDING_CHANGE_IS_AUDITED, at, type Proofs, t, type WriteRoute } from "../auditClaims";

/** A project id to build the addresses with; the routes take a UUID. */
const A_PROJECT = "3a0f5c2e-1b4d-4e6f-8a9b-0c1d2e3f4a5b";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/components/MyChannels.tsx myCodeApiPath(row.channel)": [
    at("POST /api/v1/me/channels/{name}/code", "myCodeApiPath", myCodeApiPath("webhook")),
  ],
  "src/components/MyChannels.tsx myUnbindApiPath(row.channel)": [
    at("POST /api/v1/me/channels/{name}/unbind", "myUnbindApiPath", myUnbindApiPath("webhook")),
  ],
  "src/components/MyAccounts.tsx myConsentPath(row.connector)": [
    at("POST /api/v1/me/accounts/{connector}/consent", "myConsentPath", myConsentPath("xero")),
  ],
  "src/components/MyDeletion.tsx MY_DELETION_API_PATH": [
    at("POST /api/v1/me/deletion-request", "MY_DELETION_API_PATH", MY_DELETION_API_PATH),
  ],
  "src/components/MyAccounts.tsx myDisconnectPath(row.connector)": [
    at("POST /api/v1/me/accounts/{connector}/disconnect", "myDisconnectPath", myDisconnectPath("xero")),
  ],
  "src/components/MyPreferences.tsx LEARNING_API_PATH": [
    at("POST /api/v1/me/preferences/learning", "LEARNING_API_PATH", LEARNING_API_PATH),
  ],
  "src/components/MyPreferences.tsx REACH_API_PATH": [
    at("POST /api/v1/me/preferences/reach", "REACH_API_PATH", REACH_API_PATH),
  ],
  "src/components/MyPreferences.tsx QUIET_API_PATH": [
    at("POST /api/v1/me/preferences/quiet-hours", "QUIET_API_PATH", QUIET_API_PATH),
  ],
  "src/components/MyAccountCards.tsx shareApiPath(artifactId)": [
    at("POST /api/v1/me/artifacts/{artifact_id}/share", "shareApiPath", shareApiPath("art_1")),
  ],
  "src/components/MyAccountCards.tsx unshareApiPath(artifactId)": [
    at("POST /api/v1/me/artifacts/{artifact_id}/unshare", "unshareApiPath", unshareApiPath("art_1")),
  ],
  "src/components/MyAccountCards.tsx askForAgentApiPath(agentId)": [
    at("POST /api/v1/me/agents/{agent_id}/request", "askForAgentApiPath", askForAgentApiPath("a_1")),
  ],
  "src/components/MyAccountCards.tsx END_MY_DEVICE_API_PATH": [
    at("POST /api/v1/me/devices/end", "END_MY_DEVICE_API_PATH", END_MY_DEVICE_API_PATH),
  ],
  "src/components/MyProjects.tsx PROJECTS_API_PATH": [
    at("POST /api/v1/me/projects", "PROJECTS_API_PATH", PROJECTS_API_PATH),
  ],
  "src/components/MyProjects.tsx archiveApiPath(projectId)": [
    at("POST /api/v1/me/projects/{project_id}/archive", "archiveApiPath", archiveApiPath(A_PROJECT)),
  ],
  "src/components/MyProjects.tsx addItemApiPath(projectId)": [
    at("POST /api/v1/me/projects/{project_id}/items", "addItemApiPath", addItemApiPath(A_PROJECT)),
  ],
  "src/pages/Ask.tsx addItemApiPath(project)": [
    at("POST /api/v1/me/projects/{project_id}/items", "addItemApiPath", addItemApiPath(A_PROJECT)),
  ],
  // `send` takes the address of a rename or of taking one thing out, and the card passes one of
  // the two functions below at each call.
  "src/components/MyProjects.tsx path": [
    at("POST /api/v1/me/projects/{project_id}/rename", "renameApiPath", renameApiPath(A_PROJECT)),
    at("POST /api/v1/me/projects/{project_id}/items", "addItemApiPath", addItemApiPath(A_PROJECT)),
    at("POST /api/v1/me/projects/{project_id}/items/remove", "removeItemApiPath", removeItemApiPath(A_PROJECT)),
  ],
  'src/components/MyProjects.tsx uploadPath(kind, "personal", "")': [
    at("POST /api/v1/knowledge/uploads", "uploadPath", uploadPath("sop", "personal", "").split("?")[0] ?? ""),
  ],
  "src/pages/MyWorkspace.tsx FORGET_API_PATH": [
    at("POST /api/v1/me/memory/forget", "FORGET_API_PATH", FORGET_API_PATH),
  ],
  "src/pages/MyWorkspace.tsx FORGET_ALL_API_PATH": [
    at("POST /api/v1/me/memory/forget-all", "FORGET_ALL_API_PATH", FORGET_ALL_API_PATH),
  ],
  "src/pages/MyWorkspace.tsx EDIT_API_PATH": [at("POST /api/v1/me/memory/edit", "EDIT_API_PATH", EDIT_API_PATH)],
  "src/pages/LearningUndo.tsx LEARNING_UNDO_API_PATH": [
    at("POST /api/v1/me/learning/undo", "LEARNING_UNDO_API_PATH", LEARNING_UNDO_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/me/deletion-request": {
    row: t(
      "test_acceptance_checks_member_deletion",
      "test_the_deletion_check_passes_on_an_install_and_leaves_nothing",
      true,
    ),
    audit: {
      notApplicable:
        "Asking changes nothing the system holds: the row is the record that a person asked, and it is " +
        "kept when they are erased. The act with a consequence is the erasure the retention owner files, " +
        "which migration 0060's trigger records as a ledger entry; test_member_deletion holds that " +
        "asking files nothing in the queue.",
    },
    behaviour: t(
      "test_member_deletion",
      "test_asking_records_the_ask_and_deletes_nothing",
    ),
  },
  "POST /api/v1/me/accounts/{connector}/disconnect": {
    row: {
      notApplicable:
        "The change is the removal of one vault slot, the person's own refresh token, and no table row: " +
        "the route reads the slot's metadata, asks the vendor to revoke, then removes it, which " +
        "test_person_token_revoker holds in that order against a recording vendor and vault.",
    },
    audit: {
      notApplicable:
        "A credential removal is recorded by the vault's own audit log, which names the slot and the " +
        "token that removed it; the application keeps no ledger row for a removal, and the route logs " +
        "only the source name. test_member_accounts holds that a failed revocation removes nothing.",
    },
    behaviour: t(
      "test_member_accounts",
      "test_a_person_disconnects_their_own_account_and_the_revoker_is_asked_for_their_slot",
    ),
  },
  "POST /api/v1/me/accounts/{connector}/consent": {
    row: t(
      "test_connector_consent",
      "test_a_consent_is_answered_as_the_kind_it_was_started_as_and_the_kind_never_changes",
      true,
    ),
    audit: {
      notApplicable:
        "Starting a person's own consent keeps no credential and changes no connection: it holds one " +
        "ops.oauth_consent row for that person, which only they can take, once. The ledger entry is the " +
        "refresh token's credential write when the vendor answers, which test_connector_consent_routes holds.",
    },
    behaviour: t(
      "test_connector_consent_routes",
      "test_a_reader_starts_their_own_consent_and_a_person_without_the_capability_is_refused_alike",
    ),
  },
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
  // A person's own setting is a row in `auth.member_preference` that the person alone may write,
  // and what it changes is read where a memory is formed, a message is sent and a card is planned,
  // so the install check follows each to that place. It writes no ledger entry: a setting about how
  // the person is reached is not a change to what anybody may see or do.
  "POST /api/v1/me/preferences/learning": {
    row: t("test_acceptance_checks_member_preferences", "test_every_member_preference_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "A person's own setting about being reached changes nobody's access and is not written to the ledger." },
    behaviour: t("test_acceptance_checks_member_preferences", "test_a_person_learnt_from_after_switching_it_off_fails_the_learning_check", true),
  },
  "POST /api/v1/me/preferences/reach": {
    row: t("test_acceptance_checks_member_preferences", "test_every_member_preference_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "A person's own setting about being reached changes nobody's access and is not written to the ledger." },
    behaviour: t("test_acceptance_checks_member_preferences", "test_a_card_sent_to_an_approver_who_chose_the_console_fails_the_approval_check", true),
  },
  "POST /api/v1/me/preferences/quiet-hours": {
    row: t("test_acceptance_checks_member_preferences", "test_every_member_preference_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "A person's own setting about being reached changes nobody's access and is not written to the ledger." },
    behaviour: t("test_acceptance_checks_member_preferences", "test_a_digest_sent_inside_quiet_hours_fails_the_held_digest_check", true),
  },
  // A member ending their own sign-in is the Sessions screen's ending through the same store, with
  // the ownership question asked under the row's lock, so its database proof follows the row and the
  // ledger entry; the install check follows the route itself.
  // A share is a row the sharer writes and may withdraw, admitting nobody: what it changes is read at
  // the colleague's own read, so the install check follows it from the row to the file. It writes no
  // ledger entry; the read it leads to does.
  "POST /api/v1/me/artifacts/{artifact_id}/share": {
    row: t("test_acceptance_checks_member_share", "test_the_share_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "A share changes nobody's access; opening what was shared is written down as the read it is." },
    behaviour: t("test_acceptance_checks_member_share", "test_a_share_with_somebody_who_cannot_open_it_fails_the_check", true),
  },
  "POST /api/v1/me/artifacts/{artifact_id}/unshare": {
    row: t("test_acceptance_checks_member_share", "test_the_share_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "Taking a share back changes nobody's access; it only removes a row that admitted nobody." },
    behaviour: t("test_acceptance_checks_member_share", "test_the_share_check_passes_on_an_install_and_leaves_nothing", true),
  },
  // A request is a row the asker writes once and nobody updates, and what it does is tell the
  // department's lead, so the install check follows it from the row to the message.
  "POST /api/v1/me/agents/{agent_id}/request": {
    row: t("test_acceptance_checks_member_agent_request", "test_the_request_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "A request changes nobody's access; what a department decides is written where audiences are changed." },
    behaviour: t("test_acceptance_checks_member_agent_request", "test_a_lead_told_every_time_fails_the_check", true),
  },
  "POST /api/v1/me/devices/end": {
    row: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    audit: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    behaviour: t(
      "test_acceptance_checks_member_account",
      "test_every_member_account_check_passes_on_an_install_and_leaves_nothing",
      true,
    ),
  },
  // A forget is the Learning screen's undo written for the person the memory is about, through the
  // same store, so the same database test follows it to the row, the ledger and the next recall.
  "POST /api/v1/me/memory/forget": {
    row: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    audit: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    behaviour: t("test_mine_routes", "test_a_member_forgets_a_memory_formed_from_their_own_words"),
  },
  // Undo all is that same forget once per memory the page lists, so the same database test follows
  // it to the row, the ledger and the next recall.
  "POST /api/v1/me/memory/forget-all": {
    row: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    audit: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    behaviour: t(
      "test_mine_routes",
      "test_undo_all_forgets_what_the_page_shows_about_the_person_and_nothing_of_anybody_elses",
    ),
  },
  // The digest's undo is the same forget on the person's sign-in alone, through the same store, so
  // the same database test follows it to the row, the ledger and the next recall.
  "POST /api/v1/me/learning/undo": {
    row: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    audit: t("test_memory_store", "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next", true),
    behaviour: t("test_mine_routes", "test_a_person_holding_no_grant_at_all_undoes_what_was_learnt_from_them"),
  },
  "POST /api/v1/me/memory/edit": {
    row: t("test_memory_store", "test_an_edit_reaches_the_rows_the_ledger_and_what_is_recalled_next", true),
    audit: t("test_memory_store", "test_an_edit_reaches_the_rows_the_ledger_and_what_is_recalled_next", true),
    behaviour: t(
      "test_mine_routes",
      "test_a_member_edits_a_memory_and_the_replacement_changes_the_words_and_nothing_else",
    ),
  },
  // A person's own project is a row only they may read or change, and what a question inside it
  // reads is decided at the reach the run holds, so the install check follows each write to the
  // row, to what a colleague is told, and to what is read.
  "POST /api/v1/me/projects": {
    row: t("test_acceptance_checks_member_projects", "test_the_project_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "A project is a person's own list of their own conversations and documents; it changes nobody's access and is not written to the ledger." },
    behaviour: t("test_project_routes", "test_a_person_makes_names_fills_and_puts_away_a_project_of_their_own"),
  },
  "POST /api/v1/me/projects/{project_id}/rename": {
    row: t("test_acceptance_checks_member_projects", "test_the_project_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "Renaming one's own project changes nobody's access and is not written to the ledger." },
    behaviour: t("test_project_routes", "test_somebody_elses_project_is_answered_as_one_never_made_on_every_route"),
  },
  "POST /api/v1/me/projects/{project_id}/archive": {
    row: t("test_acceptance_checks_member_projects", "test_the_project_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "Putting one's own project away changes nobody's access and is not written to the ledger; its items stay where they are." },
    behaviour: t("test_project_routes", "test_a_person_makes_names_fills_and_puts_away_a_project_of_their_own"),
  },
  "POST /api/v1/me/projects/{project_id}/items": {
    row: t("test_acceptance_checks_member_projects", "test_the_project_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "Listing one's own conversation or a document one may read in one's own project grants nothing: what a run reads is decided at its reach, every turn." },
    behaviour: t("test_project_context", "test_a_question_naming_a_project_brings_that_projects_files_read_by_the_document_tool"),
  },
  "POST /api/v1/me/projects/{project_id}/items/remove": {
    row: t("test_acceptance_checks_member_projects", "test_the_project_check_passes_on_an_install_and_leaves_nothing", true),
    audit: { notApplicable: "Taking something out of one's own project changes nobody's access and is not written to the ledger." },
    behaviour: t("test_project_routes", "test_with_the_switch_off_nothing_new_is_made_and_nothing_made_is_trapped"),
  },
};
