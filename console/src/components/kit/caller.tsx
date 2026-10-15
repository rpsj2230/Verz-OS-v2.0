/**
 * Who is signed in, as far as the components under the shell need to know: one principal, for the
 * things a person keeps for themselves in their own browser.
 *
 * **Supplied by the shell and by nothing else.** The shell already asks `GET /me` once, for the
 * second-factor banner, and the same answer says who is asking. This context hands that one fact down
 * so a component that keeps something per person (`kit/savedFilterStore.ts`) does not make its own
 * request, and so the console has one place that learns who the caller is. It never reads a token:
 * `scripts/check-boundaries.mjs` refuses that, and a second way of learning the caller's identity is
 * a second place for it to be wrong.
 *
 * **Unknown is a state, and it keeps nothing.** Until `/me` has answered, when it fails, and for a
 * component mounted outside the shell, there is no caller, and a component that keeps something per
 * person draws nothing and stores nothing. A stored value under a guessed or shared name would be
 * the thing this exists to prevent.
 *
 * Task ids: M27.16.3
 */

import { createContext, useContext } from "react";

const Caller = createContext<string | null>(null);

/** The shell's provider. The value is the principal `GET /me` named, or null while unknown. */
export const CallerProvider = Caller.Provider;

/** The principal the shell was told is signed in, or null when it does not know. */
export function useCallerId(): string | null {
  return useContext(Caller);
}

/** The principal out of a `/me` body, or null for a body that does not carry one. */
export function readCallerId(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const { principal_id: id } = payload as Record<string, unknown>;
  return typeof id === "string" && id !== "" ? id : null;
}
