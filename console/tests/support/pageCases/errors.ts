/**
 * The page cases for `/errors`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/errors": {
    address: "/errors",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/errors": {
        start: "2019-02-27T09:00:00Z",
        end: "2019-03-06T09:00:00Z",
        jobs: [
          {
            control: UNBROKEN,
            started_at: "2019-03-06T08:00:00Z",
            finished_at: "2019-03-06T08:00:02Z",
            kind: UNBROKEN,
          },
        ],
        jobs_truncated: true,
        requests: [
          {
            reference: UNBROKEN,
            received_at: "2019-03-06T08:30:00Z",
            lane: "model",
            status: "degraded",
            duration_ms: 812.4,
            routed_tier: "main",
            tier_basis: "default",
            model: UNBROKEN,
            provider: "anthropic",
          },
        ],
        requests_truncated: true,
        process_log_is_not_kept: true,
        failure_messages_stay_on_the_server: true,
      },
    },
  },
};
