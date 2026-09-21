/**
 * What the Secrets vault screen asks `brain.vault_routes` for, and how the answer is read. No React.
 *
 * The screen describes the vault and never what it holds: the seal, each slot's state and when it
 * was written, how each connected source's run tokens ended, and how much of the vault's audit log
 * reached the ledger. No field on the answer could hold a key or a token, and nothing here asks for
 * one. A count the API could not take is null with a sentence beside it, and is drawn as that
 * sentence rather than as zero.
 *
 * Task ids: M31.3.2.1, M31.3.2.2, M31.3.2.3, M31.3.2.4, M31.3.2.5, M31.3.2.6, M38.4.1.3
 */

import type { components } from "../api/schema";

export type VaultBody = components["schemas"]["VaultView"];
export type VaultSlot = components["schemas"]["VaultSlotView"];
export type LeaseRow = components["schemas"]["LeaseView"];

/** Where the API keeps the screen. */
export const VAULT_API_PATH = "/vault";

/** The console address and the menu's label. */
export const VAULT_PATH = "/vault";
export const VAULT_LABEL = "Secrets vault";

/** Read `VaultView` out of a response body, or null when it is not one. */
export function readVault(payload: unknown): VaultBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { seal?: unknown; providers?: unknown; connectors?: unknown; audit?: unknown };
  if (
    typeof body.seal !== "string" ||
    !Array.isArray(body.providers) ||
    !Array.isArray(body.connectors) ||
    typeof body.audit !== "object" ||
    body.audit === null
  ) {
    return null;
  }
  return payload as VaultBody;
}

/** The seal in words a person reads at a glance; the API's sentence says what to do. */
export const SEAL_WORDS: Readonly<Record<string, string>> = {
  absent: "No vault",
  unreachable: "Not answering",
  uninitialised: "Never initialised",
  sealed: "Sealed",
  open: "Open",
};

/** A slot's state in words. `defined` is a connector slot the installer made with no key yet. */
export const SLOT_WORDS: Readonly<Record<string, string>> = {
  held: "Holds a key",
  defined: "Defined, empty",
  empty: "Empty",
  unknown: "Not known",
};

/** Whether this process's token carries its own role's policy alone; the API's sentence says why. */
export const TOKEN_WORDS: Readonly<Record<string, string>> = {
  own: "Its own policy only",
  other: "Not its own policy alone",
  unknown: "Not known",
};

export function tokenInWords(state: string): string {
  return TOKEN_WORDS[state] ?? state;
}

export function sealInWords(seal: string): string {
  return SEAL_WORDS[seal] ?? seal;
}

export function slotInWords(slot: VaultSlot): string {
  return SLOT_WORDS[slot.state] ?? slot.state;
}
