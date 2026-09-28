/**
 * The page cases for `/people` and `/people/:subject`: the address each is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, SCOPES, UNBROKEN } from "../pageFixtures";

/** One page of people, whose subject key and capability are both unbreakable tokens. */
const PEOPLE = {
  items: [{ subject: `principal:${UNBROKEN}`, capabilities: [UNBROKEN] }],
  next_cursor: null,
  total: null,
  truncated: false,
  editable: true,
  staleness: null,
};

/**
 * The People screen's Data steward card with nobody appointed, so its form is drawn. Sentences
 * rather than tokens, because the card draws the API's sentences and never an identifier.
 */
const NO_STEWARD = {
  appointed: false,
  principal_id: null,
  display_name: null,
  told: "No data steward is appointed.",
  appointing_another: "They are granted the reads of every connected source.",
  appointing_yourself: "Your account then holds both.",
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // The four govern screens. Every one of them draws an identifier from the API with nowhere to
  // break: a subject key, a capability, a scope slug and a clause are all one token, and a
  // capability is the longest of them. The people screen is mounted twice, once from the menu
  // and once at a subject's own address, because the second draws a second list and a form.
  "/people": {
    address: "/people",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/people": PEOPLE, "/api/v1/govern/data-steward": NO_STEWARD },
  },
  "/people/:subject": {
    address: `/people/${encodeURIComponent(`principal:${UNBROKEN}`)}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/people": PEOPLE,
      "/api/v1/govern/scopes": SCOPES,
      "/api/v1/govern/data-steward": NO_STEWARD,
      "/api/v1/govern/packs": { packs: [{ slug: "helpdesk", label: UNBROKEN, capabilities: [UNBROKEN] }] },
    },
  },
};
