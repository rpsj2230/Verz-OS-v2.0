/**
 * The draft of a stepped flow: what the person has typed and the step they are on, kept so that
 * leaving the page and coming back finds them where they were.
 *
 * **In this tab's memory, under their name, and nothing more.** It is `flowMemory.ts`: a map that lives
 * as long as the console stays open and is emptied as the person signs out. The key carries the
 * principal (`kit/caller.tsx`), so a flow opened by somebody else in the same tab is not handed this
 * one, and **a flow whose caller is not yet known keeps nothing**, which is the same refusal the saved
 * filters make. Rejected: the browser's storage, which would keep a half-written install across
 * restarts and for the next person on a shared computer, and the API, which has no table for a draft
 * of an install that has not happened.
 *
 * **Never a secret.** Whatever is passed in is stored as it is, so a flow that collects a credential
 * does not put it here: it keeps it in its own field (`ui/secret-field.tsx`), which holds it outside
 * React, and the draft holds only what the flow would print back on its confirmation. The only flow
 * that uses this at present, installing a template, asks for a name, a tick and some channels.
 *
 * Task ids: M27.15.68
 */

import { useCallback, useRef, useState } from "react";
import { forgetFlow, recallFlow, rememberFlow } from "./flowMemory";

export interface FlowDraft<T> {
  /** What was kept for this key, or the initial value. */
  readonly draft: T;
  /** Replace the draft, or derive the next one from the last; kept at once. */
  readonly change: (next: T | ((before: T) => T)) => void;
  /** Throw the draft away and return to the initial value. */
  readonly forget: () => void;
  /** Whether anything was kept before this mount, so the flow can say it picked up where they were. */
  readonly resumed: boolean;
}

export function useFlowDraft<T>(key: string | null, initial: T): FlowDraft<T> {
  const [resumed] = useState(() => key !== null && recallFlow<T>(key) !== undefined);
  const [draft, setDraft] = useState<T>(() => (key === null ? initial : (recallFlow<T>(key) ?? initial)));
  const latest = useRef(draft);
  latest.current = draft;
  const change = useCallback(
    (next: T | ((before: T) => T)) => {
      const made = typeof next === "function" ? (next as (before: T) => T)(latest.current) : next;
      latest.current = made;
      setDraft(made);
      if (key !== null) {
        rememberFlow(key, made);
      }
    },
    [key],
  );
  const forget = useCallback(() => {
    latest.current = initial;
    setDraft(initial);
    if (key !== null) {
      forgetFlow(key);
    }
  }, [key, initial]);
  return { draft, change, forget, resumed };
}
