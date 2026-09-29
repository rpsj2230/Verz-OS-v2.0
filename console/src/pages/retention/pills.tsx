/**
 * Where an erasure request stands, as a pill whose tone is written beside each word as a literal,
 * for the reason `review/pills.tsx` gives.
 *
 * Task ids: M27.16.1
 */

import { Pill } from "../review/parts";

export function ErasurePill({ outcome }: { readonly outcome: string | null }) {
  switch (outcome) {
    case null:
      return <Pill tone="warn">Waiting</Pill>;
    case "erased":
      return <Pill tone="ok">Erased</Pill>;
    case "incomplete":
      return <Pill tone="crit">Incomplete</Pill>;
    default:
      return <Pill tone="plain">{outcome.replace(/_/g, " ")}</Pill>;
  }
}
