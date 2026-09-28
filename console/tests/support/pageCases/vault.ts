/**
 * The page cases for `/vault`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const VAULT_SLOT = {
  slot: UNBROKEN,
  description: UNBROKEN,
  state: "held",
  set_at: "2019-03-04T09:00:00Z",
  request: [UNBROKEN],
  refuse: [UNBROKEN],
};

const VAULT = {
  seal: "open",
  told: UNBROKEN,
  slots_unread: "",
  providers: [VAULT_SLOT],
  connectors: [VAULT_SLOT],
  leases: [{ connector: UNBROKEN, issued: 3, revoked: 2, expired: 1, not_revoked: 0 }],
  leases_told: UNBROKEN,
  lease_ttl_minutes: 15,
  rotation: UNBROKEN,
  audit: { entries: 4, refused: 1, last_shipped_at: "2019-03-04T09:00:00Z", told: UNBROKEN },
  token_policy: "own",
  token_policies: [UNBROKEN],
  token_told: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Vault activity. The lease table scrolls; the shipping sentences wrap outside it.
  "/vault": {
    address: "/vault",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/vault": VAULT },
  },
};
