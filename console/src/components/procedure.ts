/**
 * A procedure somebody is drawing, as this console holds it. No React, no library.
 *
 * The split is the one `graph.ts` makes: this module decides what a drawing is and what an
 * edit to it may do, `ProcedureCanvas.tsx` renders it. The reason is the case that is always
 * wrong. Whether an edit would take a drawing past its bound, or close a loop, cannot be tested
 * through a component that mounts a canvas, and it is the part of an authoring surface that has
 * to be right.
 *
 * **The bound is the server's, and the canvas keeps it where the edit happens.**
 * `brain.builder.procedure` refuses a drawing past `MAX_STEPS`, one that loops, one with a step
 * nobody can reach, and one with a way out left unconnected, and it re-checks all of that
 * whatever this console believed, because the console is not a trust boundary. What the canvas
 * adds is that an author is never offered the edit the server would refuse for size or for a
 * loop: past the bound there is no button to add a step, and an arrow that would close a loop is
 * not among the choices. A control that looks live and is refused afterwards is read by the
 * person using it as a permission problem, which is the argument `GraphCanvas.tsx` makes about
 * interaction flags. The number itself is a copy, and `tests/procedure-canvas.test.tsx` holds it
 * against the Python constant and that constant against the gate's.
 *
 * **Reachability and completeness are not checked here.** A drawing is incomplete for most of
 * the time somebody is drawing it, so a step with nowhere to go yet is a normal state rather
 * than an error, and saying so on every keystroke would be a canvas arguing with its author. The
 * server says it once, in its own words, when the drawing is sent.
 *
 * **Where a step sits is not part of a procedure, so this module holds no position.** A SKILL.md
 * has no way to say where a box was, so a canvas that let an author place steps would carry an
 * arrangement the document drops, and an order expressed by placing steps left to right would
 * vanish between the drawing and the skill. `brain.builder.procedure` refuses a position for that
 * reason, and the canvas lays a drawing out with `graph.ts`'s own `layout` from the arrows alone,
 * so what an author sees ordered is what the document orders.
 *
 * **Rejected: connecting steps by dragging between handles.** It is what React Flow offers and it
 * is the wrong surface here for three reasons. It would need a second mount of the library with
 * change handlers on it, where `GraphCanvas.tsx` is read-only as a shape; a drag between two
 * handles has no keyboard equivalent, and every control in this console is a native element; and
 * jsdom lays nothing out, so a connection made by dragging is a behaviour no test here could make.
 * Connecting is a choice in a list beside the drawing, which is all three of those the other way
 * round.
 *
 * Task ids: M20.2.2, M32.5.2.3
 */

import type { Graph, GraphEdge } from "./graph";

/** The five kinds a step may be, in the API's own words: `brain.builder.compose.NodeKind`. */
export const STEP_KINDS = ["start", "tool_call", "branch", "ask", "finish"] as const;
export type StepKind = (typeof STEP_KINDS)[number];

/** The id of the one start. It is placed when a drawing begins and is never offered again. */
export const START_ID = "start";

/**
 * The kinds an author adds. Every kind but the start, because a procedure has exactly one start
 * and a canvas that offered a second would be offering a refusal.
 */
export const ADDABLE_KINDS: readonly StepKind[] = STEP_KINDS.filter((kind) => kind !== "start");

/** Which way out of a step an arrow leaves by: `brain.builder.procedure.Way`. */
export const WAYS = ["next", "holds", "otherwise"] as const;
export type Way = (typeof WAYS)[number];

/** The ways out of each kind, every one required: `brain.builder.procedure.WAYS`. */
export const WAYS_OUT: Readonly<Record<StepKind, readonly Way[]>> = {
  start: ["next"],
  tool_call: ["next"],
  branch: ["holds", "otherwise"],
  ask: ["next"],
  finish: [],
};

/**
 * The tests a branch may make: `brain.core.scope.Op`, less `any`.
 *
 * A clause that matches every row changes nothing in a conjunction, and a predicate made only of
 * such clauses is refused by the server as a branch that cannot fail. Offering it would be
 * offering a control that does nothing or is refused.
 */
export const CLAUSE_OPS = ["eq", "in", "prefix"] as const;
export type ClauseOp = (typeof CLAUSE_OPS)[number];

/**
 * The most steps a procedure may hold, start included.
 *
 * A copy of `brain.builder.procedure.MAX_STEPS`, which is `brain.gate.caches.MAX_PLAN_TOOLS`
 * imported rather than restated; the suite reads both out of the Python source.
 */
export const MAX_STEPS = 24;

/** What the canvas says in place of its buttons once a drawing is at the bound. */
export const AT_THE_BOUND =
  `A procedure holds at most ${MAX_STEPS} steps, start and finish included, and this one ` +
  "holds that many. A longer procedure is two skills.";

/**
 * Written down because offering every step as a target is the obvious list to build, and the
 * loop it admits is refused by the server after the author has drawn it.
 */
export const AN_ARROW_THAT_CLOSES_A_LOOP_IS_NOT_OFFERED =
  "An arrow may point at any step except the start, the step it leaves, and any step that " +
  "already leads back to the step it leaves. The last is the loop, and a loop on a procedure " +
  "canvas is a while with no bound on it, which the server refuses.";

/** One test a branch makes. The value is text as typed; an `in` test takes one value a line. */
export interface Clause {
  readonly field: string;
  readonly op: ClauseOp;
  readonly value: string;
}

/** One step. Every kind carries every field, and the payload keeps only the one its kind uses. */
export interface Step {
  readonly id: string;
  readonly kind: StepKind;
  /** The tool a `tool_call` invokes, or empty. */
  readonly tool: string;
  /** What an `ask` puts to the person, or empty. */
  readonly prompt: string;
  /** What a `branch` tests, all of them at once. There is no "or", as in every scope. */
  readonly clauses: readonly Clause[];
}

/** One arrow: from a step, by one of its ways out, to another step. */
export interface Arrow {
  readonly from: string;
  readonly way: Way;
  readonly to: string;
}

/** A whole drawing. Steps and arrows, and deliberately no coordinates: see the module note. */
export interface Drawing {
  readonly steps: readonly Step[];
  readonly arrows: readonly Arrow[];
}

/** What the canvas sends, in the shape `brain.builder.procedure.read_drawing` reads. */
export interface DrawingPayload {
  readonly nodes: readonly Readonly<Record<string, unknown>>[];
  readonly edges: readonly { readonly from: string; readonly to: string; readonly way: Way }[];
}

/** An edit this canvas does not make. A bug in whatever asked for it, never a state to show. */
export class RefusedEdit extends Error {}

function blank(id: string, kind: StepKind): Step {
  return { id, kind, tool: "", prompt: "", clauses: [] };
}

/** A drawing with its one start and nothing else, which is where every procedure begins. */
export const NEW_DRAWING: Drawing = Object.freeze({
  steps: [blank(START_ID, "start")],
  arrows: [],
});

/** Whether another step fits. */
export function canAddStep(drawing: Drawing): boolean {
  return drawing.steps.length < MAX_STEPS;
}

/**
 * The next free id, `step_` and a number one past the highest in use.
 *
 * Generated rather than typed, so an id always survives being written into a SKILL.md line,
 * which is the grammar `brain.builder.procedure.STEP_ID_RE` holds a drawing to.
 */
function nextId(drawing: Drawing): string {
  let highest = 0;
  for (const step of drawing.steps) {
    const numbered = /^step_(\d+)$/.exec(step.id);
    if (numbered?.[1] !== undefined) {
      highest = Math.max(highest, Number(numbered[1]));
    }
  }
  return `step_${highest + 1}`;
}

/** The drawing with one more step of this kind, or a refusal at the bound. */
export function addStep(drawing: Drawing, kind: StepKind): Drawing {
  if (!ADDABLE_KINDS.includes(kind)) {
    throw new RefusedEdit(`A ${kind} is not a step an author adds.`);
  }
  if (!canAddStep(drawing)) {
    throw new RefusedEdit(AT_THE_BOUND);
  }
  return { ...drawing, steps: [...drawing.steps, blank(nextId(drawing), kind)] };
}

/** The drawing without this step and without every arrow to or from it. */
export function removeStep(drawing: Drawing, id: string): Drawing {
  if (id === START_ID) {
    throw new RefusedEdit("The start is where every run begins, so it is not removed.");
  }
  return {
    steps: drawing.steps.filter((step) => step.id !== id),
    arrows: drawing.arrows.filter((arrow) => arrow.from !== id && arrow.to !== id),
  };
}

/** The drawing with one step's tool, question or tests replaced. */
export function updateStep(
  drawing: Drawing,
  id: string,
  change: Partial<Pick<Step, "tool" | "prompt" | "clauses">>,
): Drawing {
  return {
    ...drawing,
    steps: drawing.steps.map((step) => (step.id === id ? { ...step, ...change } : step)),
  };
}

/** Every step some chain of arrows leads to from this one. */
function downstream(drawing: Drawing, from: string): ReadonlySet<string> {
  const reached = new Set<string>();
  const waiting = [from];
  while (waiting.length > 0) {
    const current = waiting.pop();
    for (const arrow of drawing.arrows) {
      if (arrow.from === current && !reached.has(arrow.to)) {
        reached.add(arrow.to);
        waiting.push(arrow.to);
      }
    }
  }
  return reached;
}

/**
 * The steps an arrow out of `from` may point at, in drawing order.
 *
 * See `AN_ARROW_THAT_CLOSES_A_LOOP_IS_NOT_OFFERED`. The arrow currently leaving by that way is
 * always among them, because it did not close a loop when it was drawn.
 */
export function targetsFor(drawing: Drawing, from: string): readonly Step[] {
  return drawing.steps.filter(
    (step) =>
      step.id !== START_ID && step.id !== from && !downstream(drawing, step.id).has(from),
  );
}

/** Where a step's way out currently points, or the empty string. */
export function targetOf(drawing: Drawing, from: string, way: Way): string {
  return drawing.arrows.find((arrow) => arrow.from === from && arrow.way === way)?.to ?? "";
}

/** The drawing with this way out of `from` pointing at `to`, replacing wherever it pointed. */
export function connect(drawing: Drawing, from: string, way: Way, to: string): Drawing {
  const source = drawing.steps.find((step) => step.id === from);
  if (source === undefined || !WAYS_OUT[source.kind].includes(way)) {
    throw new RefusedEdit(`Step ${from} does not leave by ${way}.`);
  }
  if (!targetsFor(drawing, from).some((step) => step.id === to)) {
    throw new RefusedEdit(AN_ARROW_THAT_CLOSES_A_LOOP_IS_NOT_OFFERED);
  }
  const kept = drawing.arrows.filter((arrow) => !(arrow.from === from && arrow.way === way));
  return { ...drawing, arrows: [...kept, { from, way, to }] };
}

/** The drawing with this way out of `from` pointing nowhere. */
export function disconnect(drawing: Drawing, from: string, way: Way): Drawing {
  return {
    ...drawing,
    arrows: drawing.arrows.filter((arrow) => !(arrow.from === from && arrow.way === way)),
  };
}

function clausePayload(clause: Clause): Readonly<Record<string, unknown>> {
  if (clause.op === "in") {
    const values = clause.value
      .split("\n")
      .map((value) => value.trim())
      .filter((value) => value !== "");
    return { field: clause.field, op: clause.op, value: values };
  }
  return { field: clause.field, op: clause.op, value: clause.value };
}

/**
 * The drawing in the shape the server reads.
 *
 * Each node carries only the field its kind uses, because `brain.builder.compose.Node` refuses a
 * tool on anything but a tool call and a predicate on anything but a branch. The arrows come out
 * step by step and way by way, so the payload is the same however the author happened to connect
 * things, and nothing about the order of their clicks reaches the server.
 */
export function drawingPayload(drawing: Drawing): DrawingPayload {
  const nodes = drawing.steps.map((step): Readonly<Record<string, unknown>> => {
    if (step.kind === "tool_call") {
      return { id: step.id, kind: step.kind, tool: step.tool };
    }
    if (step.kind === "ask") {
      return { id: step.id, kind: step.kind, prompt: step.prompt };
    }
    if (step.kind === "branch") {
      return { id: step.id, kind: step.kind, predicate: { clauses: step.clauses.map(clausePayload) } };
    }
    return { id: step.id, kind: step.kind };
  });
  const edges: { from: string; to: string; way: Way }[] = [];
  for (const step of drawing.steps) {
    for (const way of WAYS_OUT[step.kind]) {
      const to = targetOf(drawing, step.id, way);
      if (to !== "") {
        edges.push({ from: step.id, to, way });
      }
    }
  }
  return { nodes, edges };
}

/**
 * The drawing as `GraphCanvas` draws it.
 *
 * A step is labelled with its id, which is the word every line of the SKILL.md uses for it and
 * the word the controls beside the drawing use. An arrow out of a branch is labelled with its
 * way, because which of a branch's two arrows is which is part of what was drawn; an arrow that
 * is a step's only way out needs no label and gets none.
 */
export function drawingGraph(drawing: Drawing): Graph {
  const edges = drawing.arrows.map(
    (arrow): GraphEdge =>
      arrow.way === "next"
        ? { from: arrow.from, to: arrow.to }
        : { from: arrow.from, to: arrow.to, label: arrow.way },
  );
  return {
    nodes: drawing.steps.map((step) => ({ id: step.id, label: step.id, kind: step.kind })),
    edges,
  };
}
