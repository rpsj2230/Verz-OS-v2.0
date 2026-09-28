/**
 * The page cases for `/compliance`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, RUNG_ID, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Compliance. A topic's named person and a connector's entities sit in tables that scroll; the
  // served sentences, a case's references and its findings sit outside them and must wrap. One
  // closed case and one open one, so every form a case draws is on the page. No control is
  // pressed here: the confirmations are held in `tests/compliance-page.test.tsx`.
  "/compliance": {
    address: "/compliance",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/compliance/topics": {
        topics: [
          {
            topic: "grievance",
            label: "Grievances",
            named: { principal_id: UNBROKEN, named_by: UNBROKEN, named_at: "2019-03-04T09:00:00Z" },
          },
          { topic: "salary", label: "Salary", named: null },
        ],
        tally: { period: "2019-03", total: null, by_topic: null, suppressed: true },
        referral: UNBROKEN,
        routing: UNBROKEN,
      },
      "/api/v1/govern/compliance/register": {
        connectors: [
          {
            connector: "xero",
            label: UNBROKEN,
            connected_by: UNBROKEN,
            connected_at: "2019-03-04T09:00:00Z",
            transport: "https",
            version: "1",
            entities: [{ entity: UNBROKEN, tier: "projected", fields: [UNBROKEN], classes: ["contact"] }],
            categories: ["contact"],
            write_capable: false,
            records_read: 12,
            documents_read: null,
            last_read_at: "2019-03-04T10:00:00Z",
            problem: UNBROKEN,
          },
        ],
        counts: UNBROKEN,
      },
      "/api/v1/govern/compliance/breaches": {
        cases: [
          {
            case_id: "22222222-2222-4222-8222-222222222222",
            became_aware_at: "2019-03-01T09:00:00Z",
            clock_starts_at: "2019-03-01T09:00:00Z",
            awareness_basis: "observed",
            awareness_source: "internal_detection",
            recorded_by: UNBROKEN,
            evidence_reference: UNBROKEN,
            assessed_at: "2019-03-02T09:00:00Z",
            significant_harm: false,
            affected_count: 3,
            outcome: "not_notifiable",
            commission_notified_at: null,
            individuals_notified_at: null,
            exception_ground: null,
            closed_at: "2019-03-03T09:00:00Z",
            closed_by: UNBROKEN,
            obligations: [],
            findings: [],
            closable: false,
          },
          {
            case_id: RUNG_ID,
            became_aware_at: "2019-03-04T09:00:00Z",
            clock_starts_at: "2019-03-04T08:00:00Z",
            awareness_basis: "estimated",
            awareness_source: "staff_report",
            recorded_by: UNBROKEN,
            evidence_reference: UNBROKEN,
            assessed_at: null,
            significant_harm: null,
            affected_count: null,
            outcome: null,
            commission_notified_at: null,
            individuals_notified_at: null,
            exception_ground: null,
            closed_at: null,
            closed_by: null,
            obligations: [
              {
                kind: "assess",
                basis: "guideline",
                due_before: "2019-04-03T08:00:00Z",
                satisfied: false,
                overdue: true,
                satisfied_late: false,
                out_of_order: false,
              },
            ],
            findings: [UNBROKEN],
            closable: false,
          },
        ],
        closing: UNBROKEN,
      },
    },
  },
};
