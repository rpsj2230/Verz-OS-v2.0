/**
 * Reading a graph the API sent, and placing it. No React, no library.
 *
 * The split is the one `paging.ts` makes: this module decides what a graph is and where its
 * nodes go, `GraphCanvas.tsx` draws it. The reason is the case that is always wrong. What a
 * graph does about a step the caller may not see cannot be tested through a component that
 * mounts a canvas and measures a viewport, and it is the only part of a trace graph that has
 * to be right.
 *
 * **A node the caller may not see is absent, not greyed out.** This is the record-level rule,
 * not the field-level one, and the two are different rules that `brain.core.redaction` argues
 * separately. A field inside a record whose existence was already disclosed renders a lock; a
 * whole record the caller may not see is dropped rather than emptied, because returning the
 * husk announces that it exists. A step in a trace is a record. So there is no placeholder
 * node, no dimmed node, no "restricted step" and no gap where one was.
 *
 * **An edge whose other end did not arrive is a placeholder drawn as a line.** This is the
 * rule that has to be enforced here rather than assumed, and it is the one a drawing library
 * will not do for you. A graph payload filtered for a caller can easily carry an edge from a
 * step they may see to a step they may not: the edge is a fact about the step they hold, so a
 * serialiser copying edges off the visible nodes emits it, and every graph library either
 * drops it silently or draws it to a stub. Drawn, it is an arrow leaving a node and ending
 * nowhere, which says a step exists there. So `readGraph` drops every edge with an endpoint
 * that is not among the nodes, and the drop is the point of the function.
 *
 * **The layout is a function of what arrived and of nothing else.** The sharpest version of a
 * placeholder is not an element; it is a space. A layout that assigned a column to every node
 * mentioned by an edge, and then drew only the ones it had, would leave a gap in the row
 * exactly where the withheld step was, and the gap is readable. Positions here are computed
 * from the surviving nodes and the surviving edges, so two callers seeing different subsets
 * get two graphs that are each packed, and neither has a hole in it.
 *
 * **Nothing counts.** No total, no node count, no "3 steps shown", and no edge into a
 * counter. `brain.core.redaction._count_would_be_subtractable` spends four cases on the same
 * rule for records, and its argument is exactly this one: the disclosing number does not have
 * to be a count of hidden things, because a count of everything beside a list of the permitted
 * ones discloses the difference by subtraction.
 *
 * **There is no endpoint that sends any of this.** Nothing under `/api/v1` returns a graph, so
 * the field names below are this console's proposal rather than an agreement, and it is
 * written down because a console and an API that disagree here fail as a graph that silently
 * renders nothing.
 *
 * `paging.ts` was in this position too and no longer is, which is the reason to keep saying
 * so. Its filter parameter carried a spelling no route declared for the life of the module,
 * and the note recording that nothing could check it stood beside it the whole time. What
 * fixed it was a route declaring the grammar and a test reading the declaration out of the
 * Python source. Until an endpoint returns a graph, the names below are still a guess.
 *
 * **A trace graph is drawn for a run that has ended, and for nothing else** (M20.2.1).
 * `readCompletedRun` is the reader a trace screen calls, and it refuses a body that names no
 * ending in `RUN_ENDINGS`. The architecture says it in one phrase, a read-only trace graph of
 * what actually happened on a completed run, and the rule underneath it is this module's own. A
 * run still going has steps that have not all been judged against the reader, so a live graph
 * can show a step at one look and withhold it at the next, which is
 * `AN_EDGE_TO_A_MISSING_NODE_IS_A_MISSING_NODE` with a clock in it. **Rejected: drawing a live
 * run with its unfinished steps dimmed.** A dimmed step is the placeholder node this module
 * refuses, and a view that refreshes is a sequence of graphs somebody can subtract.
 *
 * **The same layout draws a procedure somebody is authoring**, which is why an edge may carry a
 * label. `procedure.ts` builds that graph from the author's own drawing, and nothing the API
 * sends for a trace can set one.
 *
 * Task ids: M32.5.2.3, M20.2.1, M20.2.2
 */

/**
 * Written down because dropping an edge looks like losing information, and the person who
 * restores it will be making the graph more complete.
 */
export const AN_EDGE_TO_A_MISSING_NODE_IS_A_MISSING_NODE =
  "An edge whose other end is not among the nodes is dropped with the node it points at. " +
  "Drawn, it is an arrow that leaves a step and ends nowhere, which tells the reader a step " +
  "is there and that they may not see it. A graph filtered by what somebody may see must " +
  "look like a graph, not like a graph with pieces cut out of it, because the shape of the " +
  "cut is the disclosure.";

/**
 * Written down because a node count is the most natural thing to put above a canvas, and
 * because it is the same mistake the grid's footer would be.
 */
export const A_CANVAS_NEVER_CARRIES_A_COUNT =
  "No count of nodes reaches a screen from here, including a count the API was entitled to " +
  "compute. A canvas showing the steps a caller may see, beside a total that was not " +
  "filtered, discloses the difference by subtraction. Neither is there a count of dropped " +
  "edges, which would be the same number arrived at from the other side.";

/** One node, as this console holds it. Three fields, and none of them is a reason. */
export interface GraphNode {
  readonly id: string;
  /** What a person reads. The API's own words; the console adds nothing to them. */
  readonly label: string;
  /**
   * What kind of step this is, as the API spelled it, or the empty string.
   *
   * Rendered as a chip, which has one appearance and no tone, for the reason `ui/Chip.tsx`
   * gives: the moment a kind could choose a colour, a canvas is deciding that some of its
   * steps are alarming, and the first such decision anybody writes is red for the restricted
   * ones.
   */
  readonly kind: string;
}

/**
 * One edge. Two node ids, and on a procedure canvas which way out of a branch it is.
 *
 * **`readGraph` never sets `label`.** A trace edge is two ids and nothing else, so a label the
 * API sent has nowhere to land, and a label is exactly where a reason would arrive on a line
 * between two steps. `procedure.ts` sets one on each of a branch's two arrows, which are the
 * author's own and say "holds" or "otherwise".
 */
export interface GraphEdge {
  readonly from: string;
  readonly to: string;
  readonly label?: string;
}

/** A whole graph as this console holds it. Two lists, deliberately: see the module note. */
export interface Graph {
  readonly nodes: readonly GraphNode[];
  readonly edges: readonly GraphEdge[];
}

export const EMPTY_GRAPH: Graph = Object.freeze({ nodes: [], edges: [] });

/** A body that was not a graph. A bug in the console or the API, never an answer. */
export class UnreadableGraph extends Error {}

/** A string field off a payload object, or the empty string. */
function text(source: Record<string, unknown>, key: string): string {
  const value = source[key];
  return typeof value === "string" ? value : "";
}

/**
 * Read a graph out of a response body.
 *
 * Throws rather than returning an empty graph, for the reason `readPage` throws: an empty
 * graph is a legitimate answer about somebody's data and a malformed body is a bug, and
 * rendering the second as the first tells a person there were no steps when nobody said so.
 *
 * A node with no id is skipped rather than kept with a generated one. An invented id would
 * make an edge match a node the API never named, which puts a line between two steps that
 * are not connected, and a trace read wrongly is worse than a trace not read.
 *
 * **Nothing but `id`, `label` and `kind` is carried off a node.** A span in
 * `brain.ops.tracing` has `payload_in` and `payload_out`, which are the question and the
 * answer and are masked before they leave the process that made them. They are not fields
 * this reader knows about, so a payload that carried them, masked or not, has nowhere to put
 * them.
 */
export function readGraph(payload: unknown): Graph {
  if (typeof payload !== "object" || payload === null) {
    throw new UnreadableGraph("A graph body must be an object.");
  }
  const fields = payload as { nodes?: unknown; edges?: unknown };
  if (!Array.isArray(fields.nodes)) {
    throw new UnreadableGraph("A graph body must carry a nodes array.");
  }
  if (fields.edges !== undefined && !Array.isArray(fields.edges)) {
    throw new UnreadableGraph("A graph body's edges must be an array or absent.");
  }

  const nodes: GraphNode[] = [];
  const present = new Set<string>();
  for (const entry of fields.nodes) {
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const source = entry as Record<string, unknown>;
    const id = text(source, "id");
    if (id === "" || present.has(id)) {
      continue;
    }
    present.add(id);
    nodes.push({ id, label: text(source, "label"), kind: text(source, "kind") });
  }

  const edges: GraphEdge[] = [];
  for (const entry of fields.edges ?? []) {
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const source = entry as Record<string, unknown>;
    const from = text(source, "from");
    const to = text(source, "to");
    // The drop this function exists for. Both ends have to be here, or the edge is a line to
    // a step the caller was not shown, which says the step is there.
    if (!present.has(from) || !present.has(to)) {
      continue;
    }
    edges.push({ from, to });
  }

  return { nodes, edges };
}

/**
 * How a run ends, in the API's own words: `brain.ops.telemetry.RequestStatus`.
 *
 * A copy, and `tests/trace-graph.test.tsx` holds it against the enum. It is the right vocabulary
 * for two reasons. Every member is a way a request ended and none means "still going", so a body
 * carrying one of these has ended and a body carrying none has not. And it gives DENIED and
 * ABSENT a single member, so an ending is something this console may be told about any run it
 * was sent, without the ending itself separating a refusal from an absence.
 */
export const RUN_ENDINGS: readonly string[] = [
  "answered",
  "nothing_returned",
  "unresolved",
  "degraded",
  "failed",
];

/**
 * Written down because a live view of a run is the feature somebody will ask for next, and it is
 * the placeholder this module forbids, delivered one refresh at a time.
 */
export const A_TRACE_IS_DRAWN_WHEN_THE_RUN_HAS_ENDED =
  "A trace graph draws a run that has ended and never one still going. While a run is going, " +
  "its steps have not all been judged against the person reading the trace, so a step can be " +
  "on the graph at one look and withheld at the next, and a step that vanishes between two " +
  "looks is a placeholder drawn in time rather than in space. Two looks at a graph that is " +
  "still growing are also two graphs somebody can subtract.";

/** A body for a run that has not ended. Refused, rather than drawn half-finished. */
export class UnfinishedRun extends UnreadableGraph {}

/** The brand only `readCompletedRun` applies. It has no value at run time. */
declare const ENDED: unique symbol;

/**
 * A run that has ended, and what happened on it.
 *
 * Branded, so that a component taking one cannot be handed a graph somebody assembled, or the
 * graph of a run still going: under `npm run typecheck` the only way to hold one in `src` is to
 * have called `readCompletedRun`.
 */
export interface CompletedRun {
  readonly [ENDED]: true;
  readonly graph: Graph;
}

/**
 * Read the trace of a run that has ended, or refuse.
 *
 * The body is read as a graph first, so a malformed body is `UnreadableGraph` like any other.
 * Then its `status` must be one of `RUN_ENDINGS`, or it is `UnfinishedRun`, which a screen
 * catching `UnreadableGraph` reports as the failure it is: a route promising a finished run
 * that sent a live one. See `A_TRACE_IS_DRAWN_WHEN_THE_RUN_HAS_ENDED`.
 *
 * The ending is checked and not carried. A canvas has nowhere to put it, and the one reason to
 * read it at all is to refuse a run that has none. `status` is the name `brain.ops.telemetry`'s
 * per-request record gives this vocabulary's field, and like every name here it is this
 * console's proposal until a route sends a trace.
 */
export function readCompletedRun(payload: unknown): CompletedRun {
  const graph = readGraph(payload);
  const ending = (payload as { status?: unknown }).status;
  if (typeof ending !== "string" || !RUN_ENDINGS.includes(ending)) {
    throw new UnfinishedRun("A trace graph draws a run that has ended, and this body names no ending.");
  }
  // A cast rather than a construction, because the brand is a type with nothing behind it at run
  // time, and this is the one place allowed to say that a graph belongs to a run that ended.
  return { graph } as CompletedRun;
}

/** How far apart two nodes sit. Not theme values: a canvas is a coordinate space. */
export const NODE_WIDTH = 200;
export const COLUMN_GAP = 40;
export const ROW_GAP = 110;

/** Where one node goes on the canvas. */
export interface Placement {
  readonly x: number;
  readonly y: number;
}

/**
 * How deep each node is: the longest path to it along the edges that survived.
 *
 * Relaxed rather than sorted topologically, and bounded by the number of nodes, so that a
 * payload carrying a cycle settles instead of looping. A trace over a completed run is a tree
 * and should never contain one; a canvas somebody is still drawing can, and a renderer that
 * hung on it would be a renderer that hangs on a draft.
 */
function depths(graph: Graph): Map<string, number> {
  const depth = new Map<string, number>();
  for (const node of graph.nodes) {
    depth.set(node.id, 0);
  }
  for (let pass = 0; pass < graph.nodes.length; pass += 1) {
    let moved = false;
    for (const edge of graph.edges) {
      const behind = depth.get(edge.from) ?? 0;
      const ahead = depth.get(edge.to) ?? 0;
      if (behind + 1 > ahead) {
        depth.set(edge.to, behind + 1);
        moved = true;
      }
    }
    if (!moved) {
      break;
    }
  }
  return depth;
}

/**
 * Where every node goes, in rows by depth and packed left to right within a row.
 *
 * **A row is packed, so a withheld step leaves no gap.** The column a node gets is its
 * position among the nodes that arrived at that depth, counted here, and never a position
 * reserved for it by the API or derived from anything that did not arrive. Two callers
 * entitled to different subsets get two packed graphs, and neither has a hole where the other
 * has a step.
 *
 * Deliberately not a layout library. `dagre` and `elkjs` both produce a better drawing and
 * both are a dependency whose placement rules nobody here would read, and the property this
 * function has to hold is a property of the placement rule. A hand-written twenty lines that
 * can be checked is worth more here than a good drawing that cannot.
 */
export function layout(graph: Graph): ReadonlyMap<string, Placement> {
  const depth = depths(graph);
  const filled = new Map<number, number>();
  const placement = new Map<string, Placement>();
  for (const node of graph.nodes) {
    const row = depth.get(node.id) ?? 0;
    const column = filled.get(row) ?? 0;
    filled.set(row, column + 1);
    placement.set(node.id, { x: column * (NODE_WIDTH + COLUMN_GAP), y: row * ROW_GAP });
  }
  return placement;
}
