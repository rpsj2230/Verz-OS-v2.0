/**
 * The page cases for `/agent-templates` and `/agent-templates/:templateId`: the address each is
 * mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // The catalogue. Its widest values are a template slug and the publisher's principal id,
  // which are both identifiers, and the summary is a sentence the API wrote.
  "/agent-templates": {
    address: "/agent-templates",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agent-templates": {
        items: [
          {
            template_id: UNBROKEN,
            version: 2,
            display_name: UNBROKEN,
            summary: UNBROKEN,
            published_by: UNBROKEN,
            origin: "built_in",
          },
        ],
        next_cursor: null,
        total: null,
        truncated: false,
      },
    },
  },
  // One template: its name is the heading, what it asks for are chips that wrap, its instructions
  // wrap anywhere, and the version route says whether it can be installed here.
  "/agent-templates/:templateId": {
    address: "/agent-templates/pricing_desk",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agent-templates/pricing_desk": {
        entry: {
          template_id: "pricing_desk",
          version: 2,
          display_name: UNBROKEN,
          summary: UNBROKEN,
          published_by: UNBROKEN,
          origin: "published",
        },
        persona: UNBROKEN,
        tier: "main",
        skills: [UNBROKEN],
        connectors: [UNBROKEN],
        tools: [UNBROKEN],
        capabilities: [`read:${UNBROKEN}`],
        leash: [{ target: UNBROKEN, rung: "shadow" }],
        max_side_effect: "write",
        golden_cases: 3,
      },
      "/api/v1/agent-templates/pricing_desk/versions/2": {
        template_id: "pricing_desk",
        version: 2,
        display_name: UNBROKEN,
        summary: null,
        content_digest: "d".repeat(64),
        starts: UNBROKEN,
        unavailable: null,
      },
    },
  },
};
