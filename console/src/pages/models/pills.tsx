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

/** The failover matrix's pills, rounded as the owner's screenshot draws them. */
const ROUND = "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11.5px] leading-4 font-medium";

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

/**
 * A step's role, as the owner's screenshot has it: the default as a rounded pill in the install's
 * accent, its border and wash, with a dot before the word; every later step in small quiet words.
 */
export function RolePill({ role }: { readonly role: string }): ReactElement {
  return role === "primary" ? (
    <span data-slot="role-pill" className={`${ROUND} border-brand/60 bg-acc-wash text-acc-text`}>
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-brand" />
      {roleWords(role)}
    </span>
  ) : (
    <span data-slot="role-pill" className="text-[12px] text-dim">
      {roleWords(role)}
    </span>
  );
}

/** A marker's words as a pill starts them: with a capital, "No key". */
export function markerWords(marker: StepMarker): string {
  return `${marker.label.charAt(0).toUpperCase()}${marker.label.slice(1)}`;
}

/** Why a step will not answer the next call, drawn only when it will not, beside its role. */
export function MarkerPill({ marker }: { readonly marker: StepMarker }): ReactElement {
  switch (marker.kind) {
    case "resting":
    case "no_key":
    case "cannot_call":
    case "key_refused":
      return (
        <span data-slot="marker-pill" className={`${ROUND} border-warn/30 bg-warn-wash text-warn`}>
          {markerWords(marker)}
        </span>
      );
    case "paused":
    case "turned_off":
    case "local_only":
      return (
        <span data-slot="marker-pill" className={`${ROUND} border-line bg-sunk text-dim`}>
          {markerWords(marker)}
        </span>
      );
  }
}
