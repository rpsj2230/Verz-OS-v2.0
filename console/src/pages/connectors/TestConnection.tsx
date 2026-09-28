/**
 * Test connection on a source's page: the button, its confirmation, and what the worker found.
 *
 * **A press asks, and the worker answers.** Only the worker reads a source's key, so pressing the
 * button (after its confirmation, in the API's words) writes a request, and the worker makes one
 * call on its next pass and records what it found on the source's health. Until then the page says
 * the test is waiting; once it is recorded, the page says what it found in a word and the worker's
 * own sentence, and asks the source's page again so its health shows the test. Nothing the source
 * sent is ever on this page: the API has no field that could carry it.
 *
 * **Asking again while the worker has the test is a bounded timer, and it is the one timer here.**
 * `api/useResource.ts` asks again only when a version moves, because a page that re-asked on a timer
 * would re-ask for ever. This one moves the version every `POLL_MS` while the answer says a test is
 * waiting, and stops after `MOST_POLLS` (three minutes, six worker ticks), after which Check again
 * is the way to ask. The answer is being made by another process after the request has ended, so
 * without it the person would press Check again to see a result that is already there.
 *
 * **Who sees what.** The result is shown to anybody the source's page is for; the button only to a
 * reader who may manage the source, because a test spends one call of the source's allowance.
 *
 * Task ids: M27.15.8
 */

import { PlugZap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";
import { ACT_LABELS } from "./connectorActions";
import {
  probeApiPath,
  probeStateApiPath,
  readProbe,
  TESTING_WORDS,
  VERDICT_WORDS,
  type ProbeState,
  type ProbeVerdict,
} from "./connectorProbe";
import { dateWords } from "./connectorSources";

/** How often the page asks again while a test waits, and for how long. */
export const POLL_MS = 5_000;
export const MOST_POLLS = 36;

export const CHECK_AGAIN = "Check again";
export const NOT_TESTED = "The connection was not tested";
export const NOT_NOW = "Not now";

const VERDICT_TONE: Readonly<Record<ProbeVerdict, string>> = {
  answered: "text-ok",
  waiting: "text-warn",
  failed: "text-crit",
  not_sent: "text-dim",
};

/** One source's test: what the API last said, and a way to ask again. */
export interface ConnectionTest {
  readonly probe: ProbeState | null;
  /** Take a fresh answer, from a press, and start asking again while it waits. */
  readonly took: (answer: ProbeState | null) => void;
  readonly checkAgain: () => void;
}

/**
 * The test's state for one source, asked for once the source is known to be connected.
 *
 * `onFinished` is called when a test that was waiting is recorded, so the page can ask for the
 * source again and draw the health the test left.
 */
export function useConnectionTest(name: string, connected: boolean, onFinished: () => void): ConnectionTest {
  const [path, setPath] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [probe, setProbe] = useState<ProbeState | null>(null);
  const polls = useRef(0);
  const waited = useRef(false);
  const answer = useResource<unknown>(path, version);

  useEffect(() => {
    // Kept once set, so the page asking for the source again does not ask for the test again.
    if (connected) {
      setPath(probeStateApiPath(name));
    }
  }, [connected, name]);

  useEffect(() => {
    const read = answer.data === null ? null : readProbe(answer.data);
    if (read !== null) {
      setProbe(read);
    }
  }, [answer.data]);

  useEffect(() => {
    if (probe?.pending !== true || polls.current >= MOST_POLLS) {
      return;
    }
    const timer = setTimeout(() => {
      polls.current += 1;
      setVersion((count) => count + 1);
    }, POLL_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [probe]);

  useEffect(() => {
    if (probe === null) {
      return;
    }
    if (waited.current && !probe.pending) {
      onFinished();
    }
    waited.current = probe.pending;
  }, [probe, onFinished]);

  const took = useCallback((fresh: ProbeState | null) => {
    polls.current = 0;
    if (fresh === null) {
      setVersion((count) => count + 1);
      return;
    }
    setProbe(fresh);
  }, []);
  const checkAgain = useCallback(() => {
    polls.current = 0;
    setVersion((count) => count + 1);
  }, []);
  return { probe, took, checkAgain };
}

/** The button and its confirmation. Shown only to a reader who may manage the source. */
export function TestConnectionButton({
  name,
  label,
  probe,
  onAsked,
  onFailed,
}: {
  readonly name: string;
  readonly label: string;
  /** The test's state; the button waits for it, because the confirmation is in its words. */
  readonly probe: ProbeState | null;
  readonly onAsked: (answer: ProbeState | null) => void;
  readonly onFailed: (failure: ApiFailure | null) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  function send(): void {
    setBusy(true);
    onFailed(null);
    void (async () => {
      const result = await request<unknown>(probeApiPath(name), { method: "POST" });
      setBusy(false);
      setConfirming(false);
      if (!result.ok) {
        onFailed(result.failure);
        return;
      }
      onAsked(readProbe(result.data));
    })();
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 sm:min-h-8"
        disabled={probe === null || probe.pending || busy}
        onClick={() => {
          setConfirming(true);
        }}
      >
        <PlugZap aria-hidden />
        {ACT_LABELS.test}
      </Button>
      <ConfirmDialog
        open={confirming && probe !== null}
        question={`Test the connection to ${label}?`}
        consequence={probe?.confirm ?? ""}
        confirmLabel={ACT_LABELS.test}
        cancelLabel={NOT_NOW}
        busy={busy}
        onConfirm={() => {
          send();
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

/** What the newest test found, or that one is waiting, in plain words. */
export function ConnectionTestNote({ probe, onCheckAgain }: { readonly probe: ProbeState; readonly onCheckAgain: () => void }) {
  const lead = probe.pending || probe.verdict === undefined ? TESTING_WORDS : VERDICT_WORDS[probe.verdict];
  const tone = probe.pending || probe.verdict === undefined ? "text-dim" : VERDICT_TONE[probe.verdict];
  return (
    <div data-slot="connection-test" className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1 text-[12.5px] leading-snug">
      <span className={cn("font-semibold", tone)}>{lead}</span>
      <span className="min-w-0 text-body">{probe.said}</span>
      {probe.pending || probe.testedAt === undefined ? null : <span className="text-dim">{dateWords(probe.testedAt)}</span>}
      {probe.pending ? (
        <Button variant="link" size="xs" onClick={onCheckAgain}>
          {CHECK_AGAIN}
        </Button>
      ) : null}
    </div>
  );
}
