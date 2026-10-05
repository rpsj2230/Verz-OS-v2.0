/**
 * What the console audit holds about the `audit` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped as
 * it is. A subject's access changes are read when its view opens, which its page case observes.
 *
 * Task ids: none
 */

import { VERIFICATION_API_PATH } from "../../../src/pages/auditQuery";
import { traceReadPath } from "../../../src/pages/traceQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/audit/VerifyPage.tsx VERIFICATION_API_PATH": [
    at("POST /api/v1/audit/verification", "VERIFICATION_API_PATH", VERIFICATION_API_PATH),
  ],
  "src/pages/audit/TracePage.tsx traceReadPath(id)": [
    at("POST /api/v1/traces/{trace_id}/read", "traceReadPath", traceReadPath("trace-0a1b2c")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/audit/verification": {
    row: { notApplicable: "Walking the ledger reads it and writes nothing." },
    audit: { notApplicable: "A verification changes nothing, so there is nothing to record." },
    behaviour: t("test_chain_check", "test_a_truncated_ledger_is_reported_through_the_route"),
  },
  "POST /api/v1/traces/{trace_id}/read": {
    row: t("test_trace_routes", "test_a_person_whose_token_carries_the_payload_role_reads_the_trace_after_its_row", true),
    audit: { notApplicable: "The read's own row in obs.trace_read is the record of who read the trace and why; reading changes nothing a ledger entry would record." },
    behaviour: t("test_trace_routes", "test_without_the_role_a_trace_is_answered_like_one_that_does_not_exist", true),
  },
};
