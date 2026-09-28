/**
 * The page cases for `/prompts`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Prompts. Instructions are drawn a paragraph per line, outside any table, so an unbroken
  // line is the case that would overflow a phone.
  "/prompts": {
    address: "/prompts",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/prompts": {
        house_rules: [UNBROKEN],
        output_lengths: [{ name: "brief", instruction: UNBROKEN }],
        agents: [
          {
            agent_id: UNBROKEN,
            display_name: UNBROKEN,
            department: UNBROKEN,
            instructions: `${UNBROKEN}\n${UNBROKEN}`,
            template_id: UNBROKEN,
            template_version: 3,
            template_instructions: UNBROKEN,
            overridden: true,
            set_by: UNBROKEN,
            set_at: "2019-03-05T09:00:00Z",
            effective_hash: "a".repeat(64),
            installed: true,
            editable: true,
          },
        ],
        max_chars: 2000,
        editing_switched_on: true,
        system_instructions_are_product_text: true,
        no_model_is_called_yet: true,
        every_change_is_in_the_audit_trail: true,
      },
    },
  },
};
