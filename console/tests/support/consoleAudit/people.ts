/**
 * What the console audit holds about the `people` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import { agentPreviewApiPath } from "../../../src/pages/agents/agentCapabilitiesQuery";
import { STEWARD_API_PATH } from "../../../src/pages/dataStewardQuery";
import {
  DISABLE_API_PATH,
  ENABLE_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  REVIEW_DECISION_API_PATH,
} from "../../../src/pages/governPeopleQuery";
import {
  DIRECTORY_API_PATH,
  GRANTS_API_PATH,
  PACK_ASSIGNMENT_API_PATH,
  REMOVAL_API_PATH,
  SEVERAL_GRANTS_API_PATH,
  transferApiPath as personTransferApiPath,
  workEmailApiPath,
} from "../../../src/pages/people/peopleQuery";
import { END_SESSION_API_PATH, END_SESSIONS_API_PATH } from "../../../src/pages/sessionsQuery";
import { LINK_API_PATH, UNLINK_API_PATH } from "../../../src/pages/signInLinksQuery";
import { at, audited, type Proofs, t, type WriteRoute } from "../auditClaims";

const GRANTS_PRESSED = audited("test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach");

const SEVERAL_PRESSED = audited("test_a_grant_to_several_is_written_for_everybody_or_for_nobody_against_postgresql");

const PERSON_ADDED_BY_HAND = t(
  "test_directory_routes",
  "test_a_person_added_by_hand_is_recorded_and_then_listed_with_what_they_hold",
  true,
);

const DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN = t(
  "test_principal_state",
  "test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/people/PersonPreview.tsx agentPreviewApiPath(agent)": [
    at("POST /api/v1/agents/{agent_id}/preview", "agentPreviewApiPath", agentPreviewApiPath("quote-helper")),
  ],
  "src/pages/people/PersonPlacements.tsx MEMBERSHIP_API_PATH": [
    at("POST /api/v1/govern/departments/membership", "MEMBERSHIP_API_PATH", MEMBERSHIP_API_PATH),
  ],
  "src/pages/people/PersonPlacements.tsx LEAD_API_PATH": [
    at("POST /api/v1/govern/departments/lead", "LEAD_API_PATH", LEAD_API_PATH),
  ],
  "src/pages/people/PersonGrants.tsx REMOVAL_API_PATH": [at("POST /api/v1/govern/grants/removal", "REMOVAL_API_PATH", REMOVAL_API_PATH)],
  "src/pages/people/PersonGrants.tsx REVIEW_DECISION_API_PATH": [
    at("POST /api/v1/govern/access-review/decision", "REVIEW_DECISION_API_PATH", REVIEW_DECISION_API_PATH),
  ],
  "src/pages/people/GrantDrawers.tsx GRANTS_API_PATH": [at("POST /api/v1/govern/grants", "GRANTS_API_PATH", GRANTS_API_PATH)],
  "src/pages/people/GrantDrawers.tsx SEVERAL_GRANTS_API_PATH": [
    at("POST /api/v1/govern/grants/several", "SEVERAL_GRANTS_API_PATH", SEVERAL_GRANTS_API_PATH),
  ],
  "src/pages/people/GrantDrawers.tsx PACK_ASSIGNMENT_API_PATH": [
    at("POST /api/v1/govern/packs/assignment", "PACK_ASSIGNMENT_API_PATH", PACK_ASSIGNMENT_API_PATH),
  ],
  "src/pages/people/GrantDrawers.tsx DIRECTORY_API_PATH": [at("POST /api/v1/govern/directory", "DIRECTORY_API_PATH", DIRECTORY_API_PATH)],
  "src/pages/people/PersonDetailPage.tsx disable ? DISABLE_API_PATH : ENABLE_API_PATH": [
    at("POST /api/v1/govern/people/disable", "DISABLE_API_PATH", DISABLE_API_PATH),
    at("POST /api/v1/govern/people/enable", "ENABLE_API_PATH", ENABLE_API_PATH),
  ],
  "src/pages/people/WorkEmail.tsx workEmailApiPath(principalId)": [
    at("POST /api/v1/govern/directory/{principal_id}/work-email", "workEmailApiPath", workEmailApiPath("u_first")),
  ],
  "src/pages/people/PersonOverview.tsx transferApiPath(waiting.agentId)": [
    at("POST /api/v1/govern/staff_sources/transfers/{agent_id}", "transferApiPath", personTransferApiPath("a_quotes")),
  ],
  "src/pages/people/PersonSessions.tsx LINK_API_PATH": [at("POST /api/v1/sign-ins", "LINK_API_PATH", LINK_API_PATH)],
  "src/pages/people/PersonSessions.tsx END_SESSION_API_PATH": [
    at("POST /api/v1/govern/sessions/end", "END_SESSION_API_PATH", END_SESSION_API_PATH),
  ],
  "src/pages/people/PersonSessions.tsx END_SESSIONS_API_PATH": [
    at("POST /api/v1/govern/sessions/end-several", "END_SESSIONS_API_PATH", END_SESSIONS_API_PATH),
  ],
  "src/pages/people/PersonSessions.tsx UNLINK_API_PATH": [
    at("POST /api/v1/govern/sign-ins/unlink", "UNLINK_API_PATH", UNLINK_API_PATH),
  ],
  "src/components/DataStewardCard.tsx STEWARD_API_PATH": [
    at("POST /api/v1/govern/data-steward", "STEWARD_API_PATH", STEWARD_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/directory/{principal_id}/work-email": {
    row: t("test_work_email", "test_the_list_person_who_holds_nothing_is_joined_retired_and_recorded", true),
    audit: t("test_work_email", "test_the_list_person_who_holds_nothing_is_joined_retired_and_recorded", true),
    behaviour: t(
      "test_work_email",
      "test_a_list_person_somebody_granted_something_is_joined_only_after_the_page_asks",
      true,
    ),
  },
  "POST /api/v1/govern/directory": {
    row: PERSON_ADDED_BY_HAND,
    audit: PERSON_ADDED_BY_HAND,
    behaviour: PERSON_ADDED_BY_HAND,
  },
  "POST /api/v1/govern/people/disable": {
    row: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    audit: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    behaviour: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
  },
  "POST /api/v1/govern/people/enable": {
    row: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    audit: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    behaviour: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
  },
  "POST /api/v1/govern/grants/removal": {
    row: GRANTS_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: GRANTS_PRESSED,
  },
  "POST /api/v1/govern/grants": {
    row: GRANTS_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: GRANTS_PRESSED,
  },
  // Each row of a grant to several is the single grant's insert, so its ledger entry is the one the
  // single grant's database test follows; what is its own is that all of them land or none do.
  "POST /api/v1/govern/grants/several": {
    row: SEVERAL_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: SEVERAL_PRESSED,
  },
  "POST /api/v1/govern/data-steward": {
    row: t(
      "test_data_steward_routes",
      "test_an_administrator_names_themselves_steward_over_http_once_and_is_told_why_not_twice",
      true,
    ),
    audit: t("test_data_steward", "test_every_steward_grant_leaves_a_ledger_entry_naming_who_made_it", true),
    behaviour: t(
      "test_data_steward",
      "test_a_steward_named_at_setup_grants_a_source_s_read_on_and_the_administrator_cannot",
      true,
    ),
  },
  "POST /api/v1/sign-ins": {
    row: t("test_sign_in_binding", "test_binding_the_same_subject_twice_writes_one_row", true),
    audit: t("test_sign_in_routes", "test_an_administrators_binding_is_in_the_ledger_naming_them_their_reach_and_the_request", true),
    behaviour: t("test_sign_in_binding", "test_a_valid_token_is_refused_until_its_subject_is_bound_and_accepted_after", true),
  },
  "POST /api/v1/govern/sign-ins/unlink": {
    row: t("test_sign_in_links", "test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after", true),
    audit: t("test_sign_in_links", "test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after", true),
    behaviour: t("test_sign_in_links", "test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after", true),
  },
  "POST /api/v1/govern/packs/assignment": {
    row: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
    audit: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
    behaviour: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
  },
};
