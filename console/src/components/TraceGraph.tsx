/**
 * A completed run, drawn. The trace half of the drawing surface.
 *
 * **It is read-only because a trace is a record of something that already happened.** There
 * is no editing here to disable: `GraphCanvas` is controlled with no change handlers, so the
 * surface has nowhere to send a change, and this file adds nothing that could. It renders no
 * control of its own, it reaches no module that edits a drawing, and it holds no state and
 * schedules nothing, so it cannot turn the run it was handed into a feed.
 * `tests/trace-graph.test.tsx` holds each of those four as a test rather than as a habit.
 *
 * **It draws a run that has ended, and nothing else** (M20.2.1). The prop is a `CompletedRun`,
 * which only `readCompletedRun` in `graph.ts` makes, and that reader refuses a body that names
 * no ending. The argument is `A_TRACE_IS_DRAWN_WHEN_THE_RUN_HAS_ENDED`: a run still going has
 * steps that have not all been judged against the person reading it, and a step there on one
 * look and gone on the next is the placeholder `graph.ts` forbids, arriving through time rather
 * than through space.
 *
 * **No run yet is not a run with no steps.** Before anything has been read, while a request is
 * in flight and after one has failed, there is no `CompletedRun`, and none of those three says
 * "nothing to show". That sentence is a statement about a run, and there is no run to make it
 * about.
 *
 * **The empty sentence is the grid's sentence, not a second one.** Empty because the run had
 * no steps, and empty because nothing this caller holds reaches any of them, are the same
 * event and must look the same. `brain.app.handle_brain_error` gives DENIED and ABSENT the
 * same status and the same body for exactly that reason, and a canvas that said "no steps you
 * can see" would hand the distinction back in the friendliest possible voice. It is imported
 * from `DataTable.tsx` rather than restated, because two spellings of one sentence is two
 * sentences, and the second one is the one somebody eventually makes more helpful.
 *
 * **Nothing here counts anything.** Not the steps, not the edges, not the depth of the run.
 * The argument is in `graph.ts` and it is the same one `paging.ts` makes about a table
 * footer: the disclosing number does not have to be a count of hidden things.
 *
 * **No route sends a trace graph.** `readCompletedRun` in `graph.ts` reads the shape this
 * console proposes, and nothing under `/api/v1` produces it. What is checked here is this
 * console's half of the conversation.
 *
 * Task ids: M32.5.2.3, M20.2.1
 */

import type { ApiFailure } from "../api/errors";
import { Notice } from "../ui/Notice";
import { NOTHING_TO_SHOW, SOMETHING_DID_NOT_WORK } from "./DataTable";
import { GraphCanvas } from "./GraphCanvas";
import type { CompletedRun } from "./graph";

interface TraceGraphProps {
  /** What this trace is, for a screen reader and for anybody reading it. */
  readonly caption: string;
  /** The run, from `readCompletedRun`, or null while there is no run to draw. */
  readonly run: CompletedRun | null;
  /** The failure, in the API's own words, or null. Rendered instead of the empty sentence. */
  readonly failure?: ApiFailure | null;
  /** A request is in flight, so an empty graph is not yet an answer. */
  readonly busy?: boolean;
}

export function TraceGraph({ caption, run, failure = null, busy = false }: TraceGraphProps) {
  const empty = run !== null && run.graph.nodes.length === 0;

  return (
    <div className="graph">
      <p className="graph__caption">{caption}</p>

      {failure ? (
        <Notice title={SOMETHING_DID_NOT_WORK} traceId={failure.traceId}>
          <p>{failure.message}</p>
        </Notice>
      ) : null}

      {/*
       * The canvas is not mounted for an empty graph. A drawing surface with nothing on it is
       * an expanse of blank space, and a person reading it cannot tell it apart from one that
       * has not finished loading.
       */}
      {!failure && run !== null && !empty ? (
        <GraphCanvas label={caption} graph={run.graph} />
      ) : null}

      {!failure && !busy && empty ? <p className="graph__empty">{NOTHING_TO_SHOW}</p> : null}

      {busy ? (
        <p className="graph__busy" role="status">
          Loading.
        </p>
      ) : null}
    </div>
  );
}
