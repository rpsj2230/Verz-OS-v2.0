/**
 * The state pills of Access reviews and elevation: a holding's last review and where an elevation
 * request stands. Each word's tone is written beside it as a literal, in one switch per vocabulary,
 * because `tests/status-primitives.test.tsx` holds that nothing outside `ui/Status.tsx` computes a
 * tone from data; a word this console has not heard of is drawn as itself in the plain tone.
 *
 * Task ids: M27.16.1
 */

import { STATE_WORDS, type ElevationRequestRow } from "../governPeopleQuery";
import { Pill } from "./parts";

/** A holding's last review. Never reviewed is the one that asks for attention. */
export function ReviewPill({ decision }: { readonly decision: string | null }) {
  if (decision === null) {
    return <Pill tone="warn">Never reviewed</Pill>;
  }
  return decision === "keep" ? <Pill tone="ok">Kept</Pill> : <Pill tone="plain">Removed</Pill>;
}

/** Where an elevation request stands. */
export function ElevationPill({ state }: { readonly state: ElevationRequestRow["state"] }) {
  switch (state) {
    case "pending":
      return <Pill tone="warn">{STATE_WORDS.pending}</Pill>;
    case "denied":
      return <Pill tone="crit">{STATE_WORDS.denied}</Pill>;
    case "live":
      return <Pill tone="ok">{STATE_WORDS.live}</Pill>;
    default:
      return <Pill tone="plain">{STATE_WORDS[state] ?? state}</Pill>;
  }
}
