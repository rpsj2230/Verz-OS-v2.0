/**
 * What the page in front of the reader was read from a copy of the database that is behind.
 *
 * The API puts a `staleness` field on every route body that may be
 * read from a replica (estate, directory, people, govern, learning and memory), with the sentence a
 * reader needs: how many seconds behind the copy is. It is a field and never a caption
 * (the banner describes the copy and never its rows), and the console used to draw it on two pages
 * and ignore it on the rest, so a person reading the People page from a copy a minute behind was
 * told nothing. Every request notes what it was told here, and the frame draws it once above
 * whichever page is showing, so a page that gains the field needs no code to be honest about it.
 *
 * **A body that carries the field at all settles it**, so `staleness: null` from a read of the
 * primary clears a sentence an earlier read of a copy left. A body with no such field says nothing,
 * and the frame clears the sentence itself when the address changes, because a sentence about one
 * page's copy is not a sentence about the next page's.
 *
 * Task ids: M36.1.2.3
 */

import { useSyncExternalStore } from "react";

let current: string | null = null;
const listeners = new Set<() => void>();

function publish(next: string | null): void {
  if (next === current) {
    return;
  }
  current = next;
  for (const listener of listeners) {
    listener();
  }
}

/** Read what a response said about its copy, if it said anything. */
export function noteStaleness(payload: unknown): void {
  if (typeof payload !== "object" || payload === null || !("staleness" in payload)) {
    return;
  }
  const said = (payload as { staleness: unknown }).staleness;
  const message = typeof said === "object" && said !== null ? (said as { message?: unknown }).message : null;
  publish(typeof message === "string" && message.trim() !== "" ? message : null);
}

/** Forget it, for an address the reader has left. */
export function clearStaleness(): void {
  publish(null);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The sentence to draw above the page, or null when what the page shows is current. */
export function useStaleness(): string | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}
