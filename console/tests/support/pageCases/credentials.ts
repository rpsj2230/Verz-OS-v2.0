/**
 * The page cases for `/credentials`, `/credentials/:family/:name` and
 * `/credentials/:family/:name/:view`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** The Credentials list as `brain.credential_routes.CredentialsPage` sends it. */
const CREDENTIAL_VAULT = {
  seal: "open",
  told: UNBROKEN,
  slots_unread: "",
  token_policy: "own",
  token_policies: ["application", "default"],
  token_told: UNBROKEN,
  live_reads: "waiting",
  live_reads_told: UNBROKEN,
};

const CREDENTIAL_ROW = {
  slot: "providers/mail_relay",
  family: "providers",
  name: "mail_relay",
  kind: "relay",
  holder: UNBROKEN,
  state: "held",
  held: true,
  set_at: "2019-03-04T09:00:00Z",
  outranked_by: "ANTHROPIC_API_KEY",
  read_by: "application",
  writable: true,
  write_told: "",
};

export const CREDENTIALS = { vault: CREDENTIAL_VAULT, items: [CREDENTIAL_ROW], next_cursor: null };

/** One slot's page as `brain.credential_routes.CredentialDetailView` sends it. */
export const CREDENTIAL = {
  vault: CREDENTIAL_VAULT,
  row: CREDENTIAL_ROW,
  description: UNBROKEN,
  fields: [{ field: "value", label: "Password", accepts: UNBROKEN }],
  ask_for: [UNBROKEN],
  never: [UNBROKEN],
  takes_effect: "outranked",
  takes_effect_told: UNBROKEN,
  use_recorded: false,
  last_used_at: null,
  last_used_told: UNBROKEN,
  history: [{ at: "2019-03-04T09:00:00Z", by: UNBROKEN, by_id: UNBROKEN }],
  history_told: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Credentials. The list's table scrolls; the vault card's sentences and the policies wrap above it.
  "/credentials": {
    address: "/credentials",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/credentials": CREDENTIALS },
  },
  // One credential's Dashboard: its figures, where it stands and the vault card.
  "/credentials/:family/:name": {
    address: "/credentials/providers/mail_relay",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/credentials/providers/mail_relay": CREDENTIAL },
  },
  // Its Profile, the view with the write-only form, the hints and the links to where else it is used.
  "/credentials/:family/:name/:view": {
    address: "/credentials/providers/mail_relay/profile",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/credentials/providers/mail_relay": CREDENTIAL },
  },
};
