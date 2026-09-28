/**
 * What the console audit holds about the `referrals` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { handledApiPath } from "../../../src/pages/referralsQuery";
import { at, COMPLIANCE_CASE, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Referrals.tsx handledApiPath(chosen.referral_id)": [
    at("POST /api/v1/me/referrals/{referral_id}/handled", "handledApiPath", handledApiPath(COMPLIANCE_CASE)),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/me/referrals/{referral_id}/handled": {
    row: t("test_compliance_store", "test_a_referral_is_filed_without_content_and_read_only_by_its_person", true),
    audit: {
      none: "Marking a referral handled writes handled_at and handled_by on its row and no ledger entry: an entry that only a sensitive question writes is the disclosure brain.audit.compliance.intercept argues against.",
    },
    behaviour: t("test_compliance_routes", "test_a_referral_marked_handled_is_shown_handled"),
  },
};
