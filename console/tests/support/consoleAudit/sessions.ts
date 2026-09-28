/**
 * What the console audit holds about the `sessions` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { END_SESSION_API_PATH, END_SESSIONS_API_PATH } from "../../../src/pages/sessionsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Sessions.tsx END_SESSION_API_PATH": [at("POST /api/v1/govern/sessions/end", "END_SESSION_API_PATH", END_SESSION_API_PATH)],
  "src/pages/Sessions.tsx END_SESSIONS_API_PATH": [
    at("POST /api/v1/govern/sessions/end-several", "END_SESSIONS_API_PATH", END_SESSIONS_API_PATH),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/sessions/end": {
    row: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    audit: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    behaviour: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
  },
  // Several endings are the single ending's store call once per session, which the route test holds;
  // what that call writes, records and refuses is the single ending's database proof.
  "POST /api/v1/govern/sessions/end-several": {
    row: t("test_session_routes", "test_several_sessions_are_ended_one_at_a_time_each_decided_by_the_single_endings_question"),
    audit: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    behaviour: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
  },
};
