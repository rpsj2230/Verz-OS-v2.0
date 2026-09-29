/**
 * What the console audit holds about the `audit` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as
 * it is. A subject's access changes are read when its view opens, which its page case observes.
 *
 * Task ids: none
 */

import { VERIFICATION_API_PATH } from "../../../src/pages/auditQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/audit/VerifyPage.tsx VERIFICATION_API_PATH": [
    at("POST /api/v1/audit/verification", "VERIFICATION_API_PATH", VERIFICATION_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/audit/verification": {
    row: { notApplicable: "Walking the ledger reads it and writes nothing." },
    audit: { notApplicable: "A verification changes nothing, so there is nothing to record." },
    behaviour: t("test_chain_check", "test_a_truncated_ledger_is_reported_through_the_route"),
  },
};
