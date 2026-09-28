/**
 * What the console audit holds about the `prompts` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import { editPath, giveBackPath } from "../../../src/pages/promptsQuery";
import { at, audited, type Proofs, type WriteRoute } from "../auditClaims";

const INSTRUCTIONS_PRESSED = audited("test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt");

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/prompts/PromptsPage.tsx editPath(asked.row.agent_id)": [at("POST /api/v1/govern/prompts/{agent_id}", "editPath", editPath("quote-helper"))],
  "src/pages/prompts/PromptsPage.tsx giveBackPath(asked.row.agent_id)": [
    at("POST /api/v1/govern/prompts/{agent_id}/give-back", "giveBackPath", giveBackPath("quote-helper")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/prompts/{agent_id}": {
    row: INSTRUCTIONS_PRESSED,
    audit: INSTRUCTIONS_PRESSED,
    behaviour: INSTRUCTIONS_PRESSED,
  },
  "POST /api/v1/govern/prompts/{agent_id}/give-back": {
    row: INSTRUCTIONS_PRESSED,
    audit: INSTRUCTIONS_PRESSED,
    behaviour: INSTRUCTIONS_PRESSED,
  },
};
