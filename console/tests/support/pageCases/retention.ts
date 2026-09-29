/**
 * The page cases for `/retention`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, RUNG_ID, UNBROKEN } from "../pageFixtures";

const REPORT = {
    report: {
      report_id: RUNG_ID,
      at: "2019-03-04T09:00:00Z",
      report_only: true,
      complete: true,
      failure: null,
      released: false,
      removed: 0,
      removed_by_class: [],
      held_by_class: [],
      queued_by_class: [],
      stores: [
        {
          store: UNBROKEN,
          data_class: "metadata_ledger",
          lifetime: "fixed_window",
          days: 1825,
          reached: true,
          beyond_horizon: 1,
          held: 0,
          due: 1,
          removed: 0,
          queued: 0,
          queued_because: UNBROKEN,
          unreached_because: "",
          oldest_days: 2000,
        },
      ],
      holds: [{ hold_id: UNBROKEN, reason_code: "litigation", company_wide: false }],
      findings: [UNBROKEN],
    },
  };

const CONTROLS = {
    may_release: true,
    may_hold: true,
    may_erase: true,
    may_read_exports: true,
    releasing: UNBROKEN,
    withdrawing: UNBROKEN,
    holding: UNBROKEN,
    lifting: UNBROKEN,
    erasing: UNBROKEN,
    exports: UNBROKEN,
    erasures: UNBROKEN,
    exports_not_yours: UNBROKEN,
    kept: [{ data_class: UNBROKEN, lifetime: "fixed_window", days: 30, because: UNBROKEN }],
  };

const ERASURES = {
    requests: [
      {
        request_id: RUNG_ID,
        subject_id: UNBROKEN,
        reason_reference: UNBROKEN,
        requested_by: UNBROKEN,
        requested_at: "2019-03-04T09:00:00Z",
        finished_at: "2019-03-04T09:15:00Z",
        outcome: "incomplete",
        stores: [
          {
            store: "recording",
            disposition: "erase",
            reached: false,
            removed: 0,
            retired: 0,
            kept: 0,
            because: UNBROKEN,
          },
        ],
        holds: [],
      },
    ],
    people: { [UNBROKEN]: UNBROKEN },
  };

const EXPORTS = {
    exports: [
      {
        export_id: RUNG_ID,
        data_set: "audit_trail",
        requested_by: UNBROKEN,
        reason: "regulatory_request",
        reason_reference: UNBROKEN,
        produced_at: "2019-03-04T09:00:00Z",
        first_seq: 0,
        last_seq: 1,
        entries: 2,
        verified: true,
        document_digest: UNBROKEN,
      },
    ],
    people: { [UNBROKEN]: UNBROKEN },
  };

/** What every Retention page reads: the report, the controls and the queue. */
const READS = {
  "/api/v1/govern/retention": REPORT,
  "/api/v1/govern/retention/controls": CONTROLS,
  "/api/v1/govern/erasures": ERASURES,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Retention and erasure. A store name sits in the table; the served sentences and a finding sit
  // outside it and must wrap. No control is pressed here: the confirmations are held in
  // `tests/retention-page.test.tsx`.
  "/retention": { address: "/retention", signedIn: true, drawsValues: true, answers: READS },
  // The Exports view, which alone reads the export log.
  "/retention/:view": {
    address: "/retention/exports",
    signedIn: true,
    drawsValues: true,
    answers: { ...READS, "/api/v1/govern/retention/exports": EXPORTS },
  },
  "/retention/holds/:holdId": { address: `/retention/holds/${UNBROKEN}`, signedIn: true, drawsValues: true, answers: READS },
  "/retention/erasures/:requestId": { address: `/retention/erasures/${RUNG_ID}`, signedIn: true, drawsValues: true, answers: READS },
};
