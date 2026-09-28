/**
 * What the console audit holds about the `access-requests` module: the writes its screens send,
 * each mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { ACCESS_REQUESTS_API_PATH } from "../../../src/pages/accessRequestsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/AccessRequests.tsx ACCESS_REQUESTS_API_PATH": [
    at("POST /api/v1/access-requests", "ACCESS_REQUESTS_API_PATH", ACCESS_REQUESTS_API_PATH),
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
};
