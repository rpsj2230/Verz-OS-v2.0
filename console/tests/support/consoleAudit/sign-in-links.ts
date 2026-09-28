/**
 * What the console audit holds about the `sign-in-links` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { LINK_API_PATH, UNLINK_API_PATH } from "../../../src/pages/signInLinksQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/SignInLinks.tsx LINK_API_PATH": [at("POST /api/v1/sign-ins", "LINK_API_PATH", LINK_API_PATH)],
  "src/pages/SignInLinks.tsx UNLINK_API_PATH": [at("POST /api/v1/govern/sign-ins/unlink", "UNLINK_API_PATH", UNLINK_API_PATH)],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
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
};
