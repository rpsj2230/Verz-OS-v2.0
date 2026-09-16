/**
 * A procedure being drawn: the drawing on the one canvas, and the controls that draw it.
 *
 * **The drawing surface is `GraphCanvas`, unchanged, and it is still read-only.** It is the only
 * place this console mounts React Flow, and it takes a graph as a value with no change handlers
 * on it, so nothing that happens on the surface can reach the drawing. The drawing changes
 * because the controls below it change it, and the canvas redraws what it is given. That is
 * `procedure.ts`'s argument for not connecting steps by dragging, and it keeps the trace graph's
 * guarantee intact: the two surfaces share a mount, and neither can edit anything through it.
 *
 * **Every control is a native element beside the drawing.** Adding a step is a button, choosing a
 * tool or where an arrow goes is a select, and a question is a textarea. A keyboard reaches all of
 * them in document order, a screen reader announces each by its label, and jsdom can press every
 * one, so everything an author can do here is something a test here does.
 *
 * **The bound is kept where the edit is made.** At `MAX_STEPS` there is no button to add a step,
 * and a sentence says why; an arrow that would close a loop is not among the choices. Neither is
 * a courtesy the server relies on, because the server re-checks every drawing it is sent, and
 * neither is a refusal an author meets after drawing something, which is the reason to keep them
 * here as well. See `procedure.ts`.
 *
 * **What comes out is the server's SKILL.md, shown as it was written.** This component hands the
 * drawing up in the shape `brain.builder.procedure.read_drawing` reads, and renders the document
 * it is given back. It writes no SKILL.md of its own, for the reason
 * `brain.builder.procedure` rejects a serialiser in the console: two serialisers are two answers
 * to what a drawing says, and the one in a browser is on the wrong side of the trust boundary. A
 * refusal is shown in the API's own words, which name the author's own steps and never anything
 * the author was not shown.
 *
 * **No route takes a drawing yet.** Nothing under `/api/v1` accepts one or answers a SKILL.md, so
 * this is mounted on no page, and what is checked is this console's half of the exchange: that
 * drawing on it produces the drawing the server's own test reads.
 *
 * Task ids: M20.2.2, M32.5.2.3
 */

import { useState } from "react";
import type { ApiFailure } from "../api/errors";
import { Chip } from "../ui/Chip";
import { GraphCanvas } from "./GraphCanvas";
import {
  ADDABLE_KINDS,
  AT_THE_BOUND,
  CLAUSE_OPS,
  NEW_DRAWING,
  START_ID,
  WAYS_OUT,
  addStep,
  canAddStep,
  connect,
  disconnect,
  drawingGraph,
  drawingPayload,
  removeStep,
  targetOf,
  targetsFor,
  updateStep,
  type Clause,
  type ClauseOp,
  type Drawing,
  type DrawingPayload,
  type Step,
} from "./procedure";
import { FailureNotice } from "../ui/FailureNotice";

interface ProcedureCanvasProps {
  /** What this procedure is, for a screen reader and for anybody reading it. */
  readonly caption: string;
  /** The tools this author may call, in the API's words. A tool call offers these and no others. */
  readonly tools: readonly string[];
  /** Where the drawing begins. A new drawing holds its start and nothing else. */
  readonly initial?: Drawing;
  /** Called after every edit with the drawing in the shape the server reads. */
  readonly onChange?: (drawing: DrawingPayload) => void;
  /** The SKILL.md the server wrote from the last drawing it was sent, or null. */
  readonly skill?: string | null;
  /** The server's refusal or failure, in its own words, or null. */
  readonly failure?: ApiFailure | null;
}

interface Change {
  readonly drawing: Drawing;
  readonly change: (next: Drawing) => void;
}

/** A branch's tests. All of them apply at once, because a scope has no "or". */
function ClauseControls({ step, drawing, change }: Change & { readonly step: Step }) {
  const replace = (clauses: readonly Clause[]): void => {
    change(updateStep(drawing, step.id, { clauses }));
  };
  const edit = (index: number, part: Partial<Clause>): void => {
    replace(step.clauses.map((clause, at) => (at === index ? { ...clause, ...part } : clause)));
  };

  return (
    <div className="procedure-step__clauses">
      {step.clauses.map((clause, index) => {
        const id = `${step.id}-clause-${index}`;
        return (
          <div key={id} className="procedure-step__clause">
            <label htmlFor={`${id}-field`}>Field</label>
            <input
              id={`${id}-field`}
              className="form-control"
              value={clause.field}
              onChange={(event) => edit(index, { field: event.target.value })}
            />
            <label htmlFor={`${id}-op`}>Test</label>
            <select
              id={`${id}-op`}
              className="form-control"
              value={clause.op}
              // A cast at the DOM boundary: the options are exactly `CLAUSE_OPS`, so the value a
              // select reports is one of them, and proving that again buys nothing.
              onChange={(event) => edit(index, { op: event.target.value as ClauseOp })}
            >
              {CLAUSE_OPS.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </select>
            <label htmlFor={`${id}-value`}>Value</label>
            {clause.op === "in" ? (
              <textarea
                id={`${id}-value`}
                className="form-control"
                value={clause.value}
                onChange={(event) => edit(index, { value: event.target.value })}
              />
            ) : (
              <input
                id={`${id}-value`}
                className="form-control"
                value={clause.value}
                onChange={(event) => edit(index, { value: event.target.value })}
              />
            )}
            <button
              type="button"
              className="button"
              onClick={() => replace(step.clauses.filter((_, at) => at !== index))}
            >
              Remove this test
            </button>
          </div>
        );
      })}
      <button
        type="button"
        className="button"
        onClick={() => replace([...step.clauses, { field: "", op: "eq", value: "" }])}
      >
        Add a test
      </button>
    </div>
  );
}

/** Everything about one step an author can change, and where each of its ways out goes. */
function StepControls({
  step,
  drawing,
  tools,
  change,
}: Change & { readonly step: Step; readonly tools: readonly string[] }) {
  const id = (part: string): string => `${step.id}-${part}`;

  return (
    <fieldset className="procedure-step__fields">
      <legend className="procedure-step__heading">
        <code>{step.id}</code> <Chip label={step.kind} />
      </legend>

      {step.kind === "tool_call" ? (
        <div className="procedure-step__field">
          <label htmlFor={id("tool")}>Tool</label>
          <select
            id={id("tool")}
            className="form-control"
            value={tools.includes(step.tool) ? step.tool : ""}
            onChange={(event) => change(updateStep(drawing, step.id, { tool: event.target.value }))}
          >
            <option value="">Choose a tool</option>
            {tools.map((tool) => (
              <option key={tool} value={tool}>
                {tool}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {step.kind === "ask" ? (
        <div className="procedure-step__field">
          <label htmlFor={id("prompt")}>Question</label>
          <textarea
            id={id("prompt")}
            className="form-control"
            value={step.prompt}
            onChange={(event) =>
              change(updateStep(drawing, step.id, { prompt: event.target.value }))
            }
          />
        </div>
      ) : null}

      {step.kind === "branch" ? (
        <ClauseControls step={step} drawing={drawing} change={change} />
      ) : null}

      {WAYS_OUT[step.kind].map((way) => (
        <div key={way} className="procedure-step__field">
          <label htmlFor={id(way)}>{way}</label>
          <select
            id={id(way)}
            className="form-control"
            value={targetOf(drawing, step.id, way)}
            onChange={(event) =>
              change(
                event.target.value === ""
                  ? disconnect(drawing, step.id, way)
                  : connect(drawing, step.id, way, event.target.value),
              )
            }
          >
            <option value="">Nowhere yet</option>
            {targetsFor(drawing, step.id).map((target) => (
              <option key={target.id} value={target.id}>
                {target.id}
              </option>
            ))}
          </select>
        </div>
      ))}

      {step.id === START_ID ? null : (
        <button
          type="button"
          className="button"
          onClick={() => change(removeStep(drawing, step.id))}
        >
          Remove {step.id}
        </button>
      )}
    </fieldset>
  );
}

export function ProcedureCanvas({
  caption,
  tools,
  initial = NEW_DRAWING,
  onChange,
  skill = null,
  failure = null,
}: ProcedureCanvasProps) {
  const [drawing, setDrawing] = useState<Drawing>(initial);

  const change = (next: Drawing): void => {
    setDrawing(next);
    onChange?.(drawingPayload(next));
  };

  return (
    <div className="procedure">
      <p className="procedure__caption">{caption}</p>

      <GraphCanvas label={caption} graph={drawingGraph(drawing)} />

      {canAddStep(drawing) ? (
        <div className="procedure__palette" role="group" aria-label="Add a step">
          {ADDABLE_KINDS.map((kind) => (
            <button
              key={kind}
              type="button"
              className="button"
              onClick={() => change(addStep(drawing, kind))}
            >
              Add {kind}
            </button>
          ))}
        </div>
      ) : (
        <p className="procedure__bound">{AT_THE_BOUND}</p>
      )}

      <ol className="procedure__steps">
        {drawing.steps.map((step) => (
          <li key={step.id} className="procedure-step">
            <StepControls step={step} drawing={drawing} tools={tools} change={change} />
          </li>
        ))}
      </ol>

      {skill === null ? null : (
        <figure className="procedure__skill">
          <figcaption className="procedure__skill-caption">SKILL.md</figcaption>
          <pre className="procedure__skill-text">{skill}</pre>
        </figure>
      )}

      {failure ? (
        <FailureNotice failure={failure} />
      ) : null}
    </div>
  );
}
