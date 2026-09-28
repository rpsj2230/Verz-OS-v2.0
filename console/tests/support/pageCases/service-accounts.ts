/**
 * The page cases for `/service-accounts` and `/service-accounts/:clientId`: the address each is
 * mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Service accounts. The ids, capabilities and key handles sit in the two tables, which scroll; the
  // API's two sentences under them wrap. No control is pressed here: the confirmations, the issue
  // form and the key shown once are held in `tests/service-accounts-page.test.tsx`.
  "/service-accounts": {
    address: "/service-accounts",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/service-accounts": {
        items: [
          {
            client_id: UNBROKEN,
            label: "",
            ceiling: [`read:${UNBROKEN}`],
            lapses_at: "2999-03-04T09:00:00Z",
            created_at: "2019-03-04T09:00:00Z",
            keys: [
              {
                handle: UNBROKEN,
                label: "",
                issued_at: "2019-03-04T09:00:00Z",
                lapses_at: "2999-03-04T09:00:00Z",
              },
            ],
            not_held_now: [],
          },
        ],
        next_cursor: null,
        truncated: false,
        reach: "A service account acts at your reach, narrowed to the capabilities it lists.",
        ownership: "A service account acts at its owner's reach, so only its owner may change it.",
      },
    },
  },
  // One service account. The name is the heading and wraps; the capabilities are chips that wrap;
  // the id and the key's handle are in Advanced.
  "/service-accounts/:clientId": {
    address: "/service-accounts/svc_one",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/service-accounts/svc_one": {
        client_id: "svc_one",
        label: UNBROKEN,
        ceiling: [`read:${UNBROKEN}`],
        lapses_at: "2999-03-04T09:00:00Z",
        created_at: "2019-03-04T09:00:00Z",
        keys: [
          {
            handle: "hdl_one",
            label: UNBROKEN,
            issued_at: "2019-03-04T09:00:00Z",
            lapses_at: "2999-03-04T09:00:00Z",
          },
        ],
        not_held_now: [],
      },
    },
  },
};
