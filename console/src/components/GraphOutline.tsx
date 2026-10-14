/**
 * A drawn graph, in words: the text alternative to the canvas (M32.5.2.3).
 *
 * **A drawing is not available to everyone, and a list is the same facts in the order a person
 * reads them.** The canvas gives every step a place a keyboard can reach and a name a screen reader
 * speaks, but following lines across a canvas by tabbing is following a picture by its corners. The
 * list says each step, what kind it is and which steps it leads to, by their own words, so a person
 * who cannot use the drawing loses nothing the drawing says. It is drawn for everybody and not
 * hidden for those who can see: a list beside a picture is also the quickest way to read a long
 * run, and a hidden one is an alternative nobody tests.
 *
 * **It says no more than the drawing does.** The argument is `THE_LIST_SAYS_WHAT_THE_DRAWING_SAYS`
 * in `graph.ts`, and the three things it forbids are the three a list invites: a count of steps, an
 * "ends here" under a step with nothing after it, and a step's number, which on a trace is a gap
 * where a withheld step was. It reads the graph `readGraph` already pruned, so a step the caller
 * may not see is not in it.
 *
 * **It is the target of the skip link above the canvas**, so a keyboard user who does not want to
 * tab across every box can jump here. It holds no state and fetches nothing.
 *
 * Task ids: M32.5.2.3, M20.2.1
 */

import { Chip } from "../ui/Chip";
import { outlineOf, type Graph } from "./graph";

export const OUTLINE_HEADING = "The steps as a list";
export const THEN_WORD = "Then";

interface GraphOutlineProps {
  /** The element id the skip link points at. */
  readonly anchor: string;
  /** What the graph is, for a screen reader. */
  readonly label: string;
  /** The graph, already read and pruned by `readGraph`, or drawn by `procedure.ts`. */
  readonly graph: Graph;
}

export function GraphOutline({ anchor, label, graph }: GraphOutlineProps) {
  const steps = outlineOf(graph);
  if (steps.length === 0) {
    return null;
  }
  return (
    <section className="graph__outline-wrap" aria-label={`${label}: ${OUTLINE_HEADING.toLowerCase()}`}>
      <h3 className="graph__outline-heading">{OUTLINE_HEADING}</h3>
      {/* Focusable by the skip link and not by the tab key, so the page has one tab stop fewer. */}
      <ol id={anchor} tabIndex={-1} className="graph__outline">
        {steps.map((step) => (
          <li key={step.id} className="graph__outline-step">
            <span className="graph__outline-label">{step.label}</span>
            {step.kind === "" ? null : (
              <>
                {" "}
                <Chip label={step.kind} />
              </>
            )}
            {step.then.length === 0 ? null : (
              <span className="graph__outline-then">
                {" "}
                {THEN_WORD}: {step.then.join("; ")}.
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
