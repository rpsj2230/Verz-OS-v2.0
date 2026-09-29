/**
 * The page cases for `/approvals` and `/approvals/:suspensionId`: the address each is mounted at
 * and what the stand-in API answers it with. `support/pageCases.ts` collects this file by its name
 * and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";
import { DRAFT_SUMMARY } from "./agents";

function card(id: string): Record<string, unknown> {
  return {
    suspension_id: id,
    artefact: `ticket.update_status on ticket\n  note: ${UNBROKEN}`,
    runs_as: UNBROKEN,
    raised_at: "2019-03-04T09:00:00Z",
    expires_at: "2019-03-04T13:00:00Z",
  };
}

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/approvals": {
    address: "/approvals",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/approvals": { items: [card("sus_1")], next_cursor: null, truncated: false },
      // The agent publishes waiting for this reader as the second person, drawn below the cards.
      "/api/v1/agent-drafts": { items: [], waiting_for_you: [DRAFT_SUMMARY] },
    },
  },
  "/approvals/:suspensionId": {
    address: "/approvals/sus_1",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/approvals/sus_1": card("sus_1") },
  },
};
