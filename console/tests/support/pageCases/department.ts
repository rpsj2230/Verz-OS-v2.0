/**
 * The page cases for `/department`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { departmentConsole, NAVIGATION_ADDRESS } from "../navigation";
import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Department, SCREEN 2's overview, mounted as a department admin would open it: the stand-in API
  // gives a department's console, so the menu drawn above it is that console's and not the
  // company's, and the department's name is an unbroken value in the header and on the page. The
  // three cards each draw a value the API sent: a count, an agent's name, and the sentence every
  // asker is told.
  "/department": {
    address: "/department",
    signedIn: true,
    drawsValues: true,
    answers: {
      [NAVIGATION_ADDRESS]: departmentConsole(UNBROKEN),
      "/api/v1/report/usage": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        departments: [{ department: UNBROKEN, questions: 3, people: 1 }],
        people: [{ person: UNBROKEN, questions: 3 }],
        questions: 3,
        machine_included: false,
        not_measured: [],
        tokens: [
          {
            axis: "model",
            lines: [{ key: UNBROKEN, runs: 3, tokens_in: 1200, tokens_out: 300 }],
            total_runs: 3,
            total_tokens_in: 1200,
            total_tokens_out: 300,
          },
        ],
      },
      "/api/v1/agents": {
        items: [{ agent_id: "quote-helper", display_name: UNBROKEN, owner_id: UNBROKEN }],
        next_cursor: null,
        truncated: false,
      },
      "/api/v1/report/questions": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [],
        nothing_connected: true,
        answered_when_nothing_connected: UNBROKEN,
        answered_when_nothing_found: UNBROKEN,
        unanswered_are_recorded: false,
      },
    },
  },
};
