/**
 * What the console audit holds about the `access_review` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { REVIEW_DECISION_API_PATH, REVIEW_DECISIONS_API_PATH } from "../../../src/pages/governPeopleQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/AccessReview.tsx REVIEW_DECISION_API_PATH": [
    at("POST /api/v1/govern/access-review/decision", "REVIEW_DECISION_API_PATH", REVIEW_DECISION_API_PATH),
  ],
  "src/pages/AccessReview.tsx REVIEW_DECISIONS_API_PATH": [
    at("POST /api/v1/govern/access-review/decisions", "REVIEW_DECISIONS_API_PATH", REVIEW_DECISIONS_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/access-review/decision": {
    row: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
    audit: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
    behaviour: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
  },
  // Several decisions are the single decision's store call once per holding, which the route test
  // holds; what that call writes, records and changes is the single decision's database proof.
  "POST /api/v1/govern/access-review/decisions": {
    row: t("test_govern_people_routes", "test_several_holdings_are_decided_one_at_a_time_each_by_the_single_decisions_question"),
    audit: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
    behaviour: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
  },
};
