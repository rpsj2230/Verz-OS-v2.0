/**
 * The only place this console mounts React Flow. Read-only by construction, for both surfaces.
 *
 * **One mount, for the same reason there is one `fetch`.** A trace graph over a completed run
 * and a canvas somebody is drawing a procedure on are different screens with different
 * grammars, and they are the same drawing surface. Two mounts would be two sets of
 * interaction flags, and the second one is where somebody leaves `nodesConnectable` on
 * because it was the default.
 *
 * **That held when the procedure canvas arrived, and it is why it arrived the way it did.** An
 * authoring surface is where a second mount looks necessary, because dragging steps about and
 * wiring them handle to handle is what the library is for. `ProcedureCanvas.tsx` draws through
 * this component instead and changes its drawing with native controls beside it, so the flags
 * below are the same for both surfaces and there is still nowhere on either for a change to go.
 * `tests/procedure-canvas.test.tsx` fails if React Flow is imported anywhere else or if any
 * file hands it a change handler, and `procedure.ts` records the three reasons.
 *
 * **Read-only is a shape here, not a setting.** The nodes and the edges are passed as props
 * with no `onNodesChange` and no `onEdgesChange`, which is React Flow's controlled mode: there
 * is nowhere for a change to go. The interaction flags below are belt and braces on top of
 * that, and they are what stops a node carrying a drag handler and a `selectable` class that says
 * it can be acted on when it cannot. The distinction matters because a control that looks live and
 * does nothing is read by the person using it as a permission problem.
 *
 * **A step can be reached by the keyboard, and that is the one place this file changed its mind
 * (2026-10-14).** It used to refuse a tab stop on a node, on the argument above. The owner's
 * requirement for this surface is that nodes are keyboard focusable and that there is a text
 * alternative, and the two are not in conflict: `nodesFocusable` gives each box a tab stop and a
 * spoken name (its words, then its kind), and `disableKeyboardA11y` is what keeps the library's
 * select-and-move keys, and the sentence it speaks about them, off a surface that has neither. A
 * focused step does nothing when a key is pressed, which is read as "nothing to do here" and not
 * as a permission problem because nothing about it looks pressable (no drag, no select, no
 * pointer). Rejected: leaving the nodes out of the tab order and relying on the list alone, which
 * fails a keyboard user who can see the drawing and wants to follow it. The cost is one tab stop
 * per step, which is why `skipTo` puts a skip link ahead of the drawing, to the list.
 *
 * **A node is drawn from `graph.ts` and never from a measurement.** Positions come from
 * `layout`, which packs each row of the graph it was given, so a step this caller may not see
 * leaves no gap. The argument for that, and for dropping an edge whose other end did not
 * arrive, is in `graph.ts`; it is the whole reason a graph needs its own reader.
 *
 * **An edge carries a label only when the procedure canvas gives it one.** A branch has two
 * arrows out and which is which is part of what was drawn, so `procedure.ts` labels them. A
 * trace edge never has one: `readGraph` copies two ids off an edge and nothing else, so a label
 * the API sent, which is exactly where a reason would arrive on a line between two steps, has
 * nowhere to land.
 *
 * **The stylesheet is `base.css`, not `style.css`.** The first is the mechanics: transforms,
 * stacking, the pane and the viewport. The second adds a visual theme with its own colours,
 * which would be a second palette in a project whose entire theme is one file of tokens. The
 * node's appearance is `styles/app.css` and the two library variables it needs, the edge
 * stroke and the handle, are pointed at tokens there.
 *
 * **Nothing here fetches and nothing here decides.** A graph arrives as a value; see
 * `graph.ts` for the shape and for the fact that no route sends one yet.
 *
 * Task ids: M32.5.2.3, M20.2.1, M20.2.2
 */

import {
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { Chip } from "../ui/Chip";
import { layout, stepWords, type Graph } from "./graph";

/** What one node carries into the drawing surface. The same three names `graph.ts` reads. */
type StepData = { readonly label: string; readonly kind: string };
type StepNodeShape = Node<StepData, "step">;

/**
 * One step on the canvas.
 *
 * **Its class list is a constant.** There is no `graph-node--denied`, no
 * `graph-node--restricted` and no modifier of any kind, for the reason `.lock` has none and
 * `.badge` has exactly four tones named after loudness: a node that looked different when the
 * reason was one thing rather than another would let two people comparing screens read the
 * difference off. The kind is shown as text in a chip, which has one appearance, so a canvas
 * cannot decide that some of its steps are alarming.
 *
 * The handles exist because an edge needs somewhere to attach and for no other reason. They
 * are not connectable: a drawing surface that could be wired up by dragging is an editor, and
 * a trace of something that already happened is not editable.
 */
function StepNode({ data }: NodeProps<StepNodeShape>) {
  return (
    <div className="graph-node">
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <span className="graph-node__label">{data.label}</span>
      {data.kind === "" ? null : <Chip label={data.kind} />}
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </div>
  );
}

/**
 * The node types this console has: one.
 *
 * Declared at module level because React Flow warns when it is handed a new object on every
 * render, and because a registry built inside a component is a registry a component can
 * decide the contents of.
 */
const NODE_TYPES: NodeTypes = { step: StepNode };

/**
 * The edges as the library takes them, with a label only where the graph has one.
 *
 * Exported because jsdom lays nothing out, and React Flow draws no edge between two nodes it
 * measured at zero size, so what the library is handed is the only part of an edge a test here
 * can read. The label is in the id as well, because a branch whose two ways lead to one step
 * has two edges between the same pair, and the library keeps one edge per id.
 */
export function flowEdges(graph: Graph): Edge[] {
  return graph.edges.map((edge) =>
    edge.label === undefined
      ? { id: `${edge.from} ${edge.to}`, source: edge.from, target: edge.to }
      : {
          id: `${edge.from} ${edge.to} ${edge.label}`,
          source: edge.from,
          target: edge.to,
          label: edge.label,
        },
  );
}

/** Where a keyboard user may jump to instead of tabbing across every step. */
export interface SkipTo {
  /** The id of the element that holds the same steps as a list. */
  readonly anchor: string;
  readonly words: string;
}

export const SKIP_TO_THE_LIST = "Skip the drawing, to the steps as a list";

interface GraphCanvasProps {
  /** What this canvas shows, for a screen reader. */
  readonly label: string;
  /** A skip link ahead of the drawing. Absent when the drawing is its own list. */
  readonly skipTo?: SkipTo | undefined;
  /** The graph, already read and pruned by `readGraph`, or drawn by `procedure.ts`. */
  readonly graph: Graph;
}

export function GraphCanvas({ label, graph, skipTo }: GraphCanvasProps) {
  const placement = layout(graph);
  const nodes: StepNodeShape[] = graph.nodes.map((node) => ({
    id: node.id,
    type: "step",
    position: placement.get(node.id) ?? { x: 0, y: 0 },
    data: { label: node.label, kind: node.kind },
    // What a screen reader says on arriving at the step: its words, then its kind.
    ariaLabel: stepWords(node),
  }));

  return (
    <>
      {skipTo === undefined ? null : (
        <a className="skip-link" href={`#${skipTo.anchor}`}>
          {skipTo.words}
        </a>
      )}
      <div className="graph__canvas" role="group" aria-label={label}>
        <ReactFlow
          nodes={nodes}
          edges={flowEdges(graph)}
          nodeTypes={NODE_TYPES}
          // Controlled with no change handlers, so nothing that happens on the surface can
          // reach the graph. Each flag below removes a way the surface would otherwise say it
          // could be acted on.
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable
          disableKeyboardA11y
          edgesFocusable={false}
          edgesReconnectable={false}
          elementsSelectable={false}
          fitView
        />
      </div>
    </>
  );
}
