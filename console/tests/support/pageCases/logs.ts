/**
 * The page cases for `/logs`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Logs. The event, the place, the reference, the exception and a field's name and value are all
  // strings from the API, and none of them has anywhere to break.
  "/logs": {
    address: "/logs",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/logs": {
        start: "2019-03-05T09:00:00Z",
        end: "2019-03-06T09:00:00Z",
        items: [
          {
            at: "2019-03-06T08:30:00Z",
            last_at: "2019-03-06T08:31:00Z",
            level: "warning",
            event: UNBROKEN,
            origin: UNBROKEN,
            reference: UNBROKEN,
            error_type: UNBROKEN,
            repeats: 3,
            fields: { [UNBROKEN]: UNBROKEN },
          },
        ],
        next_cursor: UNBROKEN,
        kept_for_days: 30,
        debug_is_not_kept: true,
        info_is_a_sample: true,
        worker_output_is_not_kept: true,
      },
    },
  },
};
