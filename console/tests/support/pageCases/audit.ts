/**
 * The page cases for `/audit`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { AUDIT, UNBROKEN, type PageCase } from "../pageFixtures";

/** The ledger's page with the names of its people, which the Who column and filter draw. */
const LEDGER = { ...AUDIT, people: { [UNBROKEN]: UNBROKEN } };

/** One subject's access changes, as `brain.audit_routes.PermissionHistoryView` sends them. */
const HISTORY = {
  subject_kind: "principal",
  subject_id: UNBROKEN,
  events: [{ at: "2019-03-04T09:00:00Z", action: "grant", actor_id: UNBROKEN, details: { capability: UNBROKEN } }],
  full: false,
  people: { [UNBROKEN]: UNBROKEN },
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Audit. The actor is drawn in the table and as an option in the Who filter, which is outside
  // anything that scrolls.
  "/audit": {
    address: "/audit",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/audit": LEDGER },
  },
  "/audit/verify": { address: "/audit/verify", signedIn: true, drawsValues: false, answers: {} },
  // Reading a trace: a form, and nothing asked until it is sent.
  "/audit/trace": { address: "/audit/trace", signedIn: true, drawsValues: false, answers: {} },
  "/audit/trace/:traceId": { address: "/audit/trace/trace-0a1b2c", signedIn: true, drawsValues: false, answers: {} },
  // One subject's page: every entry about it, and a person's access changes as its second view.
  "/audit/subject/:kind/:id": {
    address: "/audit/subject/principal/u_wide",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/audit": LEDGER },
  },
  "/audit/subject/:kind/:id/:view": {
    address: "/audit/subject/principal/u_wide/permissions",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/audit": LEDGER, "/api/v1/audit/history": HISTORY },
  },
};
