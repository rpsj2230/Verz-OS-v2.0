/**
 * What the console audit holds about the `tools` module: the writes its screens send, each mapped
 * to the routes it reaches, and the tests that follow each route to its row, its ledger entry and
 * what it changes. `support/consoleAudit.ts` collects this file and says why each claim is shaped
 * as it is.
 *
 * Task ids: none
 */

import { switchPath as toolSwitchPath } from "../../../src/pages/toolsQuery";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

const TOOLS_PRESSED = t("test_tool_routes", "test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call", true);

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/tools/ToolDetailPage.tsx switchPath(choice.tool)": [
    at("POST /api/v1/tools/{name}/switch", "switchPath", toolSwitchPath("notes.read_note")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/tools/{name}/switch": {
    row: t("test_tool_routes", "test_a_super_administrator_switches_a_tool_off_for_the_install"),
    audit: TOOLS_PRESSED,
    behaviour: TOOLS_PRESSED,
  },
};
