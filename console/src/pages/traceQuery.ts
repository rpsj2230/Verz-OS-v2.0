/**
 * Reading a run's stored trace: the address, the body, and the graph the canvas is handed.
 *
 * `brain.trace_routes` serves one trace to a reader whose sign-in carries the payload role, after
 * writing a row naming who read it and why, and answers anybody else, and a trace that is not
 * there, with one refusal. This module turns its `TraceView` into the payload `graph.ts` reads, so
 * the rules about a step the reader may not see are `readGraph`'s and are not written again here.
 *
 * **A step is a node, its parent an edge, and nothing else crosses.** The id is the step's number,
 * the label its name and the kind its kind. A step's `attributes` and its masked `payload_in` and
 * `payload_out` are not copied onto a node, because `readGraph` would drop them anyway and the
 * canvas has no field a payload belongs in: the payload is read under the role for an incident,
 * and drawing it on a canvas a screenshot carries off is a different decision.
 *
 * **The ending is the request step's own `outcome`.** `brain.ops.trace_store.steps_of` records how
 * the request ended on its root step, in `RequestStatus`'s words, which are `graph.RUN_ENDINGS`; a
 * trace is only stored once its request has finished. A root step without one is a run this
 * console will not draw, which `readCompletedRun` refuses as `UnfinishedRun`.
 *
 * Task ids: M32.5.2.3, M20.2.1
 */

/** The read route for one trace, as `brain.trace_routes.TRACE_READ_PATH` declares it. */
export function traceReadPath(traceId: string): string {
  return `/traces/${encodeURIComponent(traceId)}/read`;
}

/** The console's address for reading a trace, under the Audit log. */
export const TRACE_PAGE_PATH = "/audit/trace";

/** The longest reason the route keeps, `brain.tables.telemetry.READ_REASON_CHARS`. */
export const READ_REASON_CHARS = 500;

/** The longest trace id a person can type here. A trace id is a value the console copies. */
export const TRACE_ID_CHARS = 128;

/** One stored step, as `brain.trace_routes.TraceStepView` sends it. */
export interface TraceStep {
  readonly step: number;
  readonly parent: number | null;
  readonly kind: string;
  readonly name: string;
  readonly attributes: Readonly<Record<string, unknown>>;
}

/** What each field takes, said before anything is sent. */
export const TRACE_HINTS = Object.freeze({
  traceId: "The run's trace id, as the person reporting it or its log entry gave it.",
  reason: "Why you are reading it. It is recorded against you before the trace is shown.",
});

/** What a reader is told is missing from the form, before anything is sent. */
export const TRACE_PROBLEMS = Object.freeze({
  traceId: `Paste the run's trace id, up to ${String(TRACE_ID_CHARS)} characters.`,
  reason: `Say why the trace is being read, up to ${String(READ_REASON_CHARS)} characters. It is recorded against you.`,
});

/** Which fields of the form are not yet something the route would take. */
export function traceProblems(traceId: string, reason: string): (keyof typeof TRACE_PROBLEMS)[] {
  const problems: (keyof typeof TRACE_PROBLEMS)[] = [];
  const id = traceId.trim();
  if (id === "" || id.length > TRACE_ID_CHARS) {
    problems.push("traceId");
  }
  const why = reason.trim();
  if (why === "" || why.length > READ_REASON_CHARS) {
    problems.push("reason");
  }
  return problems;
}

/** The body the read route takes. */
export function traceReadBody(reason: string): { reason: string } {
  return { reason: reason.trim() };
}

function stepsOf(body: unknown): readonly TraceStep[] {
  if (typeof body !== "object" || body === null) {
    return [];
  }
  const steps = (body as { steps?: unknown }).steps;
  if (!Array.isArray(steps)) {
    return [];
  }
  return steps.filter(
    (one): one is TraceStep =>
      typeof one === "object" &&
      one !== null &&
      typeof (one as TraceStep).step === "number" &&
      typeof (one as TraceStep).name === "string",
  );
}

/**
 * The read route's answer as the payload `graph.readCompletedRun` reads: nodes, edges and the
 * ending. See the module note for what does not cross.
 */
export function traceGraphPayload(body: unknown): unknown {
  const steps = stepsOf(body);
  const root = steps.find((one) => one.parent === null);
  const outcome = root?.attributes.outcome;
  return {
    nodes: steps.map((one) => ({ id: String(one.step), label: one.name, kind: typeof one.kind === "string" ? one.kind : "" })),
    edges: steps
      .filter((one) => typeof one.parent === "number")
      .map((one) => ({ from: String(one.parent), to: String(one.step) })),
    status: typeof outcome === "string" ? outcome : undefined,
  };
}
