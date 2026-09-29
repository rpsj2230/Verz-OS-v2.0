/**
 * What the console audit holds about the `review` module, Access review and Elevation requests: the
 * writes its screens send, each mapped to the routes it reaches, and the tests that follow each route
 * to its row, its ledger entry and what it changes. `support/consoleAudit.ts` collects this file and
 * says why each claim is shaped as it is.
 *
 * Task ids: none
 */

import { ELEVATION_REQUESTS_API_PATH, elevationDecisionApiPath, REVIEW_DECISION_API_PATH, REVIEW_DECISIONS_API_PATH } from "../../../src/pages/governPeopleQuery";
import { CERTIFICATION_EXPORT_API_PATH } from "../../../src/pages/review/CertificationExport";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER = t(
  "test_elevation_store",
  "test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not",
  true,
);

const THE_REPORT_IS_RECORDED_WITH_ITS_LEDGER_ENTRY = t(
  "test_access_request_handled",
  "test_a_certification_report_is_recorded_as_a_readable_export_with_its_ledger_entry",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/review/ReviewActs.tsx REVIEW_DECISION_API_PATH": [
    at("POST /api/v1/govern/access-review/decision", "REVIEW_DECISION_API_PATH", REVIEW_DECISION_API_PATH),
  ],
  "src/pages/review/ReviewActs.tsx REVIEW_DECISIONS_API_PATH": [
    at("POST /api/v1/govern/access-review/decisions", "REVIEW_DECISIONS_API_PATH", REVIEW_DECISIONS_API_PATH),
  ],
  "src/pages/review/CertificationExport.tsx CERTIFICATION_EXPORT_API_PATH": [
    at("POST /api/v1/govern/access-review/export", "CERTIFICATION_EXPORT_API_PATH", CERTIFICATION_EXPORT_API_PATH),
  ],
  "src/pages/review/ElevationActs.tsx ELEVATION_REQUESTS_API_PATH": [
    at("POST /api/v1/govern/elevation/requests", "ELEVATION_REQUESTS_API_PATH", ELEVATION_REQUESTS_API_PATH),
  ],
  "src/pages/review/ElevationActs.tsx elevationDecisionApiPath(chosen.row.request_id)": [
    at(
      "POST /api/v1/govern/elevation/requests/{request_id}/decision",
      "elevationDecisionApiPath",
      elevationDecisionApiPath("11111111-2222-3333-4444-555555555555"),
    ),
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
  // The report's record and its `publish` entry are one insert and its trigger; what the file
  // holds is the review's own rows, which the route test holds against the review's decision.
  "POST /api/v1/govern/access-review/export": {
    row: THE_REPORT_IS_RECORDED_WITH_ITS_LEDGER_ENTRY,
    audit: THE_REPORT_IS_RECORDED_WITH_ITS_LEDGER_ENTRY,
    behaviour: t("test_certification_export_routes", "test_a_reviewer_exports_exactly_the_holdings_they_may_decide_and_it_is_recorded_first"),
  },
  "POST /api/v1/govern/elevation/requests": {
    row: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    audit: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    behaviour: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
  },
  "POST /api/v1/govern/elevation/requests/{request_id}/decision": {
    row: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    audit: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    behaviour: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
  },
};
