/**
 * What the console audit holds about the `elevation` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { ELEVATION_REQUESTS_API_PATH, elevationDecisionApiPath } from "../../../src/pages/governPeopleQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER = t(
  "test_elevation_store",
  "test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not",
  true,
);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Elevation.tsx ELEVATION_REQUESTS_API_PATH": [
    at("POST /api/v1/govern/elevation/requests", "ELEVATION_REQUESTS_API_PATH", ELEVATION_REQUESTS_API_PATH),
  ],
  "src/pages/Elevation.tsx elevationDecisionApiPath(chosen.row.request_id)": [
    at(
      "POST /api/v1/govern/elevation/requests/{request_id}/decision",
      "elevationDecisionApiPath",
      elevationDecisionApiPath("11111111-2222-3333-4444-555555555555"),
    ),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
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
