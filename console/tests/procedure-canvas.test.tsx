/**
 * The procedure canvas: bounded where the edit is made, and drawing on it produces the drawing
 * the server turns into a SKILL.md.
 *
 * M20.2.2 is "a bounded procedure canvas outputting a SKILL.md". The SKILL.md is written on the
 * server, from the drawing, by `brain.builder.procedure`, and
 * `tests/unit/test_builder_procedure.py` holds that it reads back as exactly the drawing it came
 * from. This file holds the canvas's half. The bound and the vocabulary are the server's, read
 * out of the Python source rather than restated. An edit the server would refuse for size or for
 * a loop is never offered. And pressing the controls produces exactly
 * `fixtures/procedure-drawing.json`, which the Python suite reads, bounds and writes a SKILL.md
 * from. That file is where the two halves meet, and without it each would be tested against its
 * own idea of the other.
 *
 * M32.5.2.3 is React Flow for the trace graph and the procedure canvas. What makes one library
 * safe for both is that it is mounted once, read-only, and the procedure is drawn through that
 * mount rather than beside it, which the last test holds.
 *
 * Under jsdom a canvas lays nothing out, so what is read is which steps reach the drawing and
 * what the controls send, never where anything sits on a screen.
 *
 * Task ids: M20.2.2, M32.5.2.3
 */

import { fireEvent, render } from "@testing-library/react";
import ts from "typescript";
import { describe, expect, test } from "vitest";
import { flowEdges } from "../src/components/GraphCanvas";
import {
  ADDABLE_KINDS,
  AT_THE_BOUND,
  CLAUSE_OPS,
  NEW_DRAWING,
  RefusedEdit,
  STEP_KINDS,
  WAYS,
  WAYS_OUT,
  addStep,
  canAddStep,
  connect,
  drawingGraph,
  drawingPayload,
  removeStep,
  targetsFor,
  updateStep,
  type Drawing,
  type DrawingPayload,
} from "../src/components/procedure";
import { ProcedureCanvas } from "../src/components/ProcedureCanvas";
import {
  backendClauseOps,
  backendDrawingKeys,
  backendMaxSteps,
  backendNodeKinds,
  backendStepIdPattern,
  backendWays,
  backendWaysOut,
} from "./support/python";
import { readConsoleFile } from "./support/repo";
import {
  consoleSourcePaths,
  jsxAttributeUses,
  packageOf,
  parseConsoleSource,
} from "./support/typescript";

const TOOLS = ["crm.read_client", "billing.create_invoice"];
const CAPTION = "A procedure";

function theFixture(): unknown {
  return JSON.parse(readConsoleFile("tests/fixtures/procedure-drawing.json"));
}

function stepsDrawn(container: HTMLElement): string[] {
  return [...container.querySelectorAll(".react-flow__node")].map(
    (node) => node.getAttribute("data-id") ?? "",
  );
}

function control(container: HTMLElement, id: string): HTMLElement {
  const found = container.querySelector(`#${id}`);
  if (!(found instanceof HTMLElement)) {
    throw new Error(`Nothing on the canvas has the id ${id}.`);
  }
  return found;
}

function set(container: HTMLElement, id: string, value: string): void {
  fireEvent.change(control(container, id), { target: { value } });
}

function press(container: HTMLElement, name: string): void {
  const button = [...container.querySelectorAll("button")].find((one) => one.textContent === name);
  if (button === undefined) {
    throw new Error(`No button on the canvas reads ${name}.`);
  }
  fireEvent.click(button);
}

function choices(container: HTMLElement, id: string): string[] {
  return [...control(container, id).querySelectorAll("option")].map((option) => option.value);
}

/** A drawing at the bound, built by the canvas's own edits, with a stop in case they never stop. */
function aFullDrawing(): Drawing {
  let drawing = NEW_DRAWING;
  for (let added = 0; added < 1000 && canAddStep(drawing); added += 1) {
    drawing = addStep(drawing, "ask");
  }
  return drawing;
}

function importsOf(path: string): string[] {
  return parseConsoleSource(path)
    .statements.filter(ts.isImportDeclaration)
    .map((statement) =>
      ts.isStringLiteral(statement.moduleSpecifier) ? statement.moduleSpecifier.text : "",
    );
}

describe("what bounds the canvas", () => {
  test("the canvas holds as many steps as the server allows, which is the gate's bound on a plan", () => {
    // What breaks if this is deleted: the canvas and the server disagree about "bounded". A
    // canvas that stopped one step short refuses a drawing the server would take, and one that
    // went one step past lets an author draw something the server refuses after the fact. The
    // figure is read from `brain.builder.procedure`, which must spell it as the gate's own
    // `MAX_PLAN_TOOLS`, so a bound tuned on either side fails here.
    const full = aFullDrawing();

    expect(full.steps).toHaveLength(backendMaxSteps());
    expect(() => addStep(full, "finish")).toThrow(RefusedEdit);
    expect(canAddStep(removeStep(full, "step_1"))).toBe(true);
  });

  test("at the bound there is no step to add, and the canvas says why", () => {
    // What breaks if this is deleted: the refusal becomes a button that does nothing, which a
    // person reads as a permission problem, or a button that adds a step the server will refuse.
    const container = render(
      <ProcedureCanvas caption={CAPTION} tools={TOOLS} initial={aFullDrawing()} />,
    ).container;

    expect(container.querySelector(".procedure__palette")).toBeNull();
    expect(container.querySelector(".procedure__bound")?.textContent).toBe(AT_THE_BOUND);
    expect(stepsDrawn(container)).toHaveLength(backendMaxSteps());
  });

  test("below the bound every kind but the start is offered, and a step added is drawn", () => {
    // What breaks if this is deleted: the positive sibling of the two above, which a canvas that
    // offered nothing would satisfy. The kinds offered are the server's own, less the start,
    // because a procedure has exactly one and a second is a refusal waiting to happen.
    const container = render(<ProcedureCanvas caption={CAPTION} tools={TOOLS} />).container;
    const offered = [...container.querySelectorAll(".procedure__palette button")].map(
      (button) => button.textContent,
    );

    expect(offered).toEqual(
      backendNodeKinds()
        .filter((kind) => kind !== "start")
        .map((kind) => `Add ${kind}`),
    );
    for (const kind of ADDABLE_KINDS) {
      press(container, `Add ${kind}`);
    }
    expect(stepsDrawn(container)).toEqual(["start", "step_1", "step_2", "step_3", "step_4"]);
    expect(container.querySelector(".procedure__bound")).toBeNull();
  });

  test("the kinds, the ways out and the tests a branch may make are the server's own", () => {
    // What breaks if this is deleted: a sixth kind, a third way out of a branch, or an "or" in the
    // predicate grammar arrives in the browser first. Each is a copy of a Python vocabulary and
    // each is compared with the vocabulary. `any` is the one test left out, on purpose, because a
    // clause that matches every row cannot change which way a branch goes.
    expect([...STEP_KINDS]).toEqual(backendNodeKinds());
    expect([...WAYS]).toEqual(backendWays());
    expect(WAYS_OUT).toEqual(backendWaysOut());

    const ops = backendClauseOps();
    expect(ops["ANY"]).toBeDefined();
    expect([...CLAUSE_OPS]).toEqual(
      Object.entries(ops)
        .filter(([name]) => name !== "ANY")
        .map(([, value]) => value),
    );

    const branching = updateStep(addStep(NEW_DRAWING, "branch"), "step_1", {
      clauses: [{ field: "tier", op: "eq", value: "gold" }],
    });
    const container = render(
      <ProcedureCanvas caption={CAPTION} tools={TOOLS} initial={branching} />,
    ).container;
    expect(choices(container, "step_1-clause-0-op")).toEqual([...CLAUSE_OPS]);
  });

  test("an arrow that would close a loop is never offered, and is refused if made anyway", () => {
    // What breaks if this is deleted: "bounded" loses its second half. Without a loop no run
    // takes a step twice, which is what makes the step bound a bound on every run. Three rules
    // decide the choices, and each is exercised: never the start, never the step itself, and
    // never a step that already leads back. The connected choice is the positive sibling.
    let drawing = addStep(addStep(addStep(NEW_DRAWING, "ask"), "ask"), "ask");
    drawing = connect(drawing, "start", "next", "step_1");
    drawing = connect(drawing, "step_1", "next", "step_2");
    const container = render(
      <ProcedureCanvas caption={CAPTION} tools={TOOLS} initial={drawing} />,
    ).container;

    expect(choices(container, "step_2-next")).toEqual(["", "step_3"]);
    expect(choices(container, "step_3-next")).toEqual(["", "step_1", "step_2"]);
    expect(() => connect(drawing, "step_2", "next", "step_1")).toThrow(RefusedEdit);
    expect(() => connect(drawing, "step_3", "next", "start")).toThrow(RefusedEdit);

    expect(targetsFor(drawing, "step_2").map((step) => step.id)).toEqual(["step_3"]);
    expect(connect(drawing, "step_2", "next", "step_3").arrows).toContainEqual({
      from: "step_2",
      way: "next",
      to: "step_3",
    });
  });
});

describe("what the canvas sends", () => {
  test("drawing on the canvas produces exactly the drawing the server turns into a SKILL.md", () => {
    // What breaks if this is deleted: the canvas and the server each pass against their own idea
    // of the wire. This presses the controls a person would press, and the last drawing the
    // canvas hands up is compared with the file `tests/unit/test_builder_procedure.py` reads,
    // bounds, writes a SKILL.md from and reads back.
    const sent: DrawingPayload[] = [];
    const { container } = render(
      <ProcedureCanvas caption={CAPTION} tools={TOOLS} onChange={(drawing) => sent.push(drawing)} />,
    );

    press(container, "Add tool_call");
    press(container, "Add branch");
    press(container, "Add ask");
    press(container, "Add finish");
    set(container, "step_1-tool", "crm.read_client");
    press(container, "Add a test");
    set(container, "step_2-clause-0-field", "tier");
    set(container, "step_2-clause-0-value", "gold");
    set(container, "step_3-prompt", "Shall I raise the invoice?");
    set(container, "start-next", "step_1");
    set(container, "step_1-next", "step_2");
    set(container, "step_2-holds", "step_3");
    set(container, "step_2-otherwise", "step_4");
    set(container, "step_3-next", "step_4");

    expect(sent.at(-1)).toEqual(theFixture());
    expect(stepsDrawn(container)).toEqual(["start", "step_1", "step_2", "step_3", "step_4"]);
  });

  test("a drawing carries the keys the server reads and no others, so no position reaches it", () => {
    // What breaks if this is deleted: a coordinate, a colour or a label rides along to a server
    // that refuses any key the SKILL.md cannot say. The key sets are read out of
    // `brain.builder.procedure`, and an `in` test is sent as the list the scope grammar takes.
    const keys = backendDrawingKeys();
    let drawing = NEW_DRAWING;
    for (const kind of ADDABLE_KINDS) {
      drawing = addStep(drawing, kind);
    }
    drawing = updateStep(drawing, "step_2", {
      clauses: [{ field: "region", op: "in", value: "north\nsouth\n" }],
    });
    drawing = connect(drawing, "start", "next", "step_1");
    drawing = connect(drawing, "step_2", "holds", "step_4");
    const payload = drawingPayload(drawing);

    expect(Object.keys(payload).sort()).toEqual(keys.drawing);
    for (const node of payload.nodes) {
      for (const key of Object.keys(node)) {
        expect(keys.nodes, key).toContain(key);
      }
    }
    for (const edge of payload.edges) {
      expect(Object.keys(edge).sort()).toEqual(keys.edges);
    }
    expect(payload.nodes[2]).toEqual({
      id: "step_2",
      kind: "branch",
      predicate: { clauses: [{ field: "region", op: "in", value: ["north", "south"] }] },
    });
  });

  test("every id the canvas makes is one the server accepts, and none is made twice", () => {
    // What breaks if this is deleted: ids are how every line of the SKILL.md points at a step,
    // so an id outside the server's grammar is a drawing refused for something the author never
    // typed, and a reused id is two steps an arrow cannot tell apart. Removing a step and adding
    // another is the case that reuses one when ids are counted rather than numbered.
    const grammar = new RegExp(backendStepIdPattern());
    let drawing = NEW_DRAWING;
    for (const kind of ADDABLE_KINDS) {
      drawing = addStep(drawing, kind);
    }
    drawing = addStep(removeStep(drawing, "step_2"), "ask");
    const ids = drawing.steps.map((step) => step.id);

    for (const id of ids) {
      expect(id).toMatch(grammar);
    }
    expect(new Set(ids).size).toBe(ids.length);
    expect(() => removeStep(drawing, "start")).toThrow(RefusedEdit);
  });

  test("a tool call offers the author's tools and no others", () => {
    // What breaks if this is deleted: the canvas offers a tool the API did not send, which is a
    // tool this author may not call, and the server refuses the drawing for it in words that do
    // not say whether it exists. The canvas holds no catalogue of its own to offer from.
    const container = render(
      <ProcedureCanvas caption={CAPTION} tools={TOOLS} initial={addStep(NEW_DRAWING, "tool_call")} />,
    ).container;

    expect(choices(container, "step_1-tool")).toEqual(["", ...TOOLS]);
  });

  test("a branch's two arrows are told apart on the drawing, and a step's only arrow is not labelled", () => {
    // What breaks if this is deleted: a branch drawn as two identical arrows, so the one fact the
    // SKILL.md is most careful about, which way is "holds", is invisible on the canvas. Two
    // arrows from one branch to one step stay two edges, because the library keeps one per id.
    let drawing = addStep(addStep(addStep(NEW_DRAWING, "branch"), "finish"), "finish");
    drawing = connect(drawing, "start", "next", "step_1");
    drawing = connect(drawing, "step_1", "holds", "step_2");
    drawing = connect(drawing, "step_1", "otherwise", "step_3");

    expect(
      flowEdges(drawingGraph(drawing)).map((edge) => [edge.source, edge.target, edge.label]),
    ).toEqual([
      ["start", "step_1", undefined],
      ["step_1", "step_2", "holds"],
      ["step_1", "step_3", "otherwise"],
    ]);

    const joined = connect(drawing, "step_1", "otherwise", "step_2");
    const ids = flowEdges(drawingGraph(joined)).map((edge) => edge.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("what comes out", () => {
  test("the SKILL.md shown is the server's, character for character, and a refusal is its own words", () => {
    // What breaks if this is deleted: the console tidies the document, trims a line or renders
    // it as markdown, and the SKILL.md an author approves on screen is not the one the server
    // wrote. A refusal is shown exactly as the API worded it and replaces nothing it did not
    // replace, because the words name the author's own steps and nothing else.
    const skill =
      "---\nname: invoice_on_request\ndescription: Reads a client.\ntools: []\n---\n" +
      "Follow these steps from the first. Each one names the step that comes after it.\n\n" +
      "1. `start` (start): go to `done`.\n2. `done` (finish): stop.\n";
    const shown = render(<ProcedureCanvas caption={CAPTION} tools={TOOLS} skill={skill} />).container;
    expect(shown.querySelector(".procedure__skill-text")?.textContent).toBe(skill);

    const message =
      "step 'step_1' never leaves by next, so a run that reaches it stops somewhere that is not a finish";
    const refused = render(
      <ProcedureCanvas
        caption={CAPTION}
        tools={TOOLS}
        failure={{ status: 422, message, traceId: "trace-abc", outcome: "", problems: [], secondFactorNeeded: false }}
      />,
    ).container;
    expect(refused.querySelector(".notice__body")?.textContent).toBe(message);
    expect(refused.querySelector(".procedure__skill")).toBeNull();
  });
});

describe("one mount of React Flow", () => {
  test("React Flow is imported in one file, handed no change handler anywhere, and the procedure draws through it", () => {
    // What breaks if this is deleted: M32.5.2.3's safety. The obvious way to build an authoring
    // canvas is a second React Flow mount with its change handlers switched on, and from that
    // day the trace graph's read-only guarantee is a matter of which mount a screen happens to
    // use. Every source file is read, so a second mount anywhere fails, and the drawing is
    // checked to really come through the one there is.
    const sources = consoleSourcePaths("src");
    const mounting = sources.filter((path) =>
      importsOf(path).some((specifier) => packageOf(specifier) === "@xyflow/react"),
    );
    expect(mounting).toEqual(["src/components/GraphCanvas.tsx"]);

    for (const path of sources.filter((one) => one.endsWith(".tsx"))) {
      const source = parseConsoleSource(path);
      for (const handler of ["onNodesChange", "onEdgesChange", "onConnect"]) {
        expect(jsxAttributeUses(source, handler), `${handler} in ${path}`).toEqual([]);
      }
    }

    expect(importsOf("src/components/ProcedureCanvas.tsx")).toContain("./GraphCanvas");
    const container = render(
      <ProcedureCanvas caption={CAPTION} tools={TOOLS} initial={addStep(NEW_DRAWING, "finish")} />,
    ).container;
    expect(container.querySelectorAll(".react-flow")).toHaveLength(1);
    expect(stepsDrawn(container)).toEqual(["start", "step_1"]);
  });
});
