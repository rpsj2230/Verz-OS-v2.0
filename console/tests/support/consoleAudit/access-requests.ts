/**
 * What the console audit holds about the `access-requests` module: the writes its screens send,
 * each mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim is
 * shaped as it is.
 *
 * Task ids: none
 */

import { ACCESS_REQUESTS_API_PATH, handledApiPath } from "../../../src/pages/accessRequestsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/access-requests/AccessRequestsPage.tsx ACCESS_REQUESTS_API_PATH": [
    at("POST /api/v1/access-requests", "ACCESS_REQUESTS_API_PATH", ACCESS_REQUESTS_API_PATH),
  ],
  "src/pages/access-requests/AccessRequestsPage.tsx handledApiPath(row.request_id)": [
    at(
      "POST /api/v1/access-requests/{request_id}/handled",
      "handledApiPath",
      handledApiPath("11111111-2222-3333-4444-555555555555"),
    ),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/access-requests": {
    row: t("test_access_request_store", "test_a_request_is_stored_and_its_owner_reads_it_back_as_the_application_role", true),
    audit: {
      notApplicable:
        "A request changes nothing anybody holds: it is a row addressed to its owner, and a decision is a grant written on the Roles screen, which is recorded there.",
    },
    behaviour: t("test_access_request_routes", "test_the_owner_reads_the_requests_addressed_to_them_and_nobody_else_does"),
  },
  "POST /api/v1/access-requests/{request_id}/handled": {
    row: t("test_access_request_handled", "test_the_owner_marks_a_request_handled_once_and_nobody_else_may", true),
    audit: {
      notApplicable:
        "Marking a request handled changes nothing anybody holds, as sending it did not: the row keeps who marked it and when, and a decision is a grant written on the People or Roles screens, which is recorded there.",
    },
    behaviour: t("test_access_request_routes", "test_the_owner_marks_a_request_handled_once_and_nobody_else_may"),
  },
};
