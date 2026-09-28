/**
 * What the console audit holds about the `approvals` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { approvalDecisionApiPath } from "../../../src/pages/approvalsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Approvals.tsx approvalDecisionApiPath(suspensionId)": [
    at("POST /api/v1/approvals/{suspension_id}/decision", "approvalDecisionApiPath", approvalDecisionApiPath("sus-1")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/approvals/{suspension_id}/decision": {
    row: t("test_suspension_store", "test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart", true),
    audit: t("test_suspension_store", "test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart", true),
    behaviour: t("test_suspension_store", "test_an_approved_suspension_is_what_resume_reads_and_a_rejected_one_is_not_run", true),
  },
};
