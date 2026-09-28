/**
 * A provider's switch, its status and a step's role, as pills in the design of record.
 *
 * **Each colour is a literal on its own case**, so the word carries the meaning and the colour only
 * repeats it, and no colour is computed from a row (`tests/ui-rules.test.ts`,
 * `tests/status-primitives.test.tsx`). The declared return type is what makes a status added
 * without a pill a type error.
 *
 * Task ids: M27.16.1
 */

import type { ReactElement } from "react";
import { roleWords, type ProviderStatus, type StepMarker } from "../modelsQuery";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

export const ON = "On";
export const OFF = "Off";

/** Switched on or off. */
export function OnOffPill({ on }: { readonly on: boolean }): ReactElement {
  return on ? (
    <span data-slot="on-off-pill" className={`${PILL} bg-ok-wash text-ok`}>
      {ON}
    </span>
  ) : (
    <span data-slot="on-off-pill" className={`${PILL} bg-sunk text-dim`}>
      {OFF}
    </span>
  );
}

/** A provider's status in words, from `modelsQuery.providerStatus`. */
export function StatusPill({ status }: { readonly status: ProviderStatus }): ReactElement {
  switch (status.kind) {
    case "working":
      return (
        <span data-slot="status-pill" className={`${PILL} bg-ok-wash text-ok`}>
          {status.label}
        </span>
      );
    case "resting":
    case "key_refused":
      return (
        <span data-slot="status-pill" className={`${PILL} bg-warn-wash text-warn`}>
          {status.label}
        </span>
      );
    case "off":
    case "no_key":
    case "server_only":
    case "unused":
      // Quiet: a provider nobody has given a key or turned on is a task for whoever set it up, not
      // an incident.
      return (
        <span data-slot="status-pill" className={`${PILL} bg-sunk text-dim`}>
          {status.label}
        </span>
      );
  }
}

/** A step's role: the default as a pill, a later step in words, as the owner's screenshot has it. */
export function RolePill({ role }: { readonly role: string }): ReactElement {
  return role === "primary" ? (
    <span data-slot="role-pill" className={`${PILL} bg-acc-wash text-acc-text`}>
      {roleWords(role)}
    </span>
  ) : (
    <span data-slot="role-pill" className="text-[12.5px] text-dim">
      {roleWords(role)}
    </span>
  );
}

/** Why a step will not answer the next call, drawn only when it will not. */
export function MarkerPill({ marker }: { readonly marker: StepMarker }): ReactElement {
  switch (marker.kind) {
    case "resting":
    case "no_key":
    case "cannot_call":
    case "key_refused":
      return (
        <span data-slot="marker-pill" className={`${PILL} bg-warn-wash text-warn`}>
          {marker.label}
        </span>
      );
    case "paused":
    case "turned_off":
    case "local_only":
      return (
        <span data-slot="marker-pill" className={`${PILL} bg-sunk text-dim`}>
          {marker.label}
        </span>
      );
  }
}
