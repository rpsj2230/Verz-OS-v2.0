/**
 * What the console audit holds about the `credentials` module: the writes its screens send, each
 * mapped to the routes it reaches, and the tests that follow each route to its row, its ledger
 * entry and what it changes. `support/consoleAudit.ts` collects this file and says why each claim
 * is shaped as it is.
 *
 * Task ids: none
 */

import { credentialApiPath } from "../../../src/pages/credentials/credentialRows";
import { at, type Proofs, t, type WriteRoute } from "../auditClaims";

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/credentials/SetValueForm.tsx credentialApiPath(detail.row.slot)": [
    at("PUT /api/v1/credentials/{family}/{name}", "credentialApiPath", credentialApiPath("providers/mail_relay")),
  ],
};

export const PROOFS: Readonly<Record<string, Proofs>> = {
  "PUT /api/v1/credentials/{family}/{name}": {
    row: t("test_credential_routes", "test_setting_a_key_writes_the_slot_and_answers_that_it_is_held_and_when"),
    audit: t("test_credential_routes", "test_a_key_set_from_the_console_is_recorded_as_its_setter_with_their_reach_and_trace"),
    behaviour: t("test_credentials", "test_a_key_kept_here_is_handed_to_this_process_unless_the_environment_outranks_it"),
  },
};
