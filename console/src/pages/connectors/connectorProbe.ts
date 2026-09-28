/**
 * Testing one source's connection: where a test is asked for and read back, and how an answer is
 * read. No React.
 *
 * **Asked for at `POST /api/v1/connectors/{name}/probe`, read back at
 * `GET /api/v1/console/connectors/{name}/probe`** (`brain.connector_routes.ask_probe` and
 * `connector_probe`). Only the worker reads a source's key, so the API writes the asking down and the
 * worker makes one call on its next pass; the answer says whether that is still waiting and what the
 * newest test found, as a word and one of the worker's own sentences. Nothing the source sent is in
 * it, and no key.
 *
 * **A reader keeps only what was sent.** A verdict this console has not heard of is dropped rather
 * than guessed at, and the sentence is drawn as the API wrote it.
 *
 * Task ids: M27.15.8
 */

export function probeApiPath(name: string): string {
  return `/connectors/${encodeURIComponent(name)}/probe`;
}

export function probeStateApiPath(name: string): string {
  return `/console/connectors/${encodeURIComponent(name)}/probe`;
}

/** What a finished test found. Closed on the API side: `brain.ops.connector_sync.ProbeVerdict`. */
export const VERDICTS = ["answered", "waiting", "failed", "not_sent"] as const;
export type ProbeVerdict = (typeof VERDICTS)[number];

/** The words a finished test leads with, before the worker's own sentence. */
export const VERDICT_WORDS: Readonly<Record<ProbeVerdict, string>> = Object.freeze({
  answered: "Connection works.",
  waiting: "The source is busy.",
  failed: "Connection failed.",
  not_sent: "Not tested.",
});

/** What a test waiting for the worker leads with. */
export const TESTING_WORDS = "Testing.";

/** One source's test as this console holds it. */
export interface ProbeState {
  readonly pending: boolean;
  readonly requestedAt?: string;
  readonly verdict?: ProbeVerdict;
  readonly testedAt?: string;
  readonly health?: string;
  /** The sentence to draw: waiting, the newest test's own, or not tested yet. */
  readonly said: string;
  /** What pressing Test connection agrees to, in the API's words. */
  readonly confirm: string;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function instant(value: unknown): string | undefined {
  const text = said(value);
  return text !== undefined && !Number.isNaN(Date.parse(text)) ? text : undefined;
}

function verdictOf(value: unknown): ProbeVerdict | undefined {
  return VERDICTS.find((one) => one === value);
}

/** A test's state out of the API's answer, or null when the body is not one. */
export function readProbe(payload: unknown): ProbeState | null {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `instant` or `verdictOf`.
  const fields = payload as Readonly<Record<string, unknown>>;
  const sentence = said(fields["said"]);
  const confirm = said(fields["confirm"]);
  if (typeof fields["pending"] !== "boolean" || sentence === undefined || confirm === undefined) {
    return null;
  }
  const requestedAt = instant(fields["requested_at"]);
  const verdict = verdictOf(fields["verdict"]);
  const testedAt = instant(fields["tested_at"]);
  const health = said(fields["health"]);
  return {
    pending: fields["pending"],
    ...(requestedAt === undefined ? {} : { requestedAt }),
    ...(verdict === undefined ? {} : { verdict }),
    ...(testedAt === undefined ? {} : { testedAt }),
    ...(health === undefined ? {} : { health }),
    said: sentence,
    confirm,
  };
}

/** Whether there is anything to draw: a test waiting, or one that finished. */
export function worthShowing(probe: ProbeState | null): probe is ProbeState {
  return probe !== null && (probe.pending || probe.verdict !== undefined);
}
