/**
 * Every act the console cannot offer is explained by one component, in a sentence the server serves.
 *
 * `docs/admin-console-architecture.md` 5.2 asks that an act the install cannot yet perform, or the
 * reader cannot perform here, is explained and never hidden. Until 2026-10-15 that was three
 * components and a dozen typed constants, so how an explanation looked and what it said were each
 * written in many places. These tests hold the shape that replaced them, by reading the source as a
 * syntax tree (`support/typescript.ts` says why) and the sentences from the server's own registry
 * (`support/explanations.ts`), never from a constant a page also imports.
 *
 * **What is held, in four rules.** The markup of an unavailable control is written in
 * `components/kit/explanation.tsx` and nowhere else, and no component under another name stands in for
 * it; a `Note` never leads with coming soon or not available yet, because that is an explanation; every
 * `Explanation` names a registered act in the form it is registered in, or hands in a sentence the API
 * sent (a field read off data, never a literal, a template or a constant); and a control is disabled
 * only for a reason this file names, because a disabled control with no sentence is the thing the task
 * is about. The readers are tested on synthetic source first, since a detector that finds nothing in
 * real source is also what a broken detector does.
 *
 * Task ids: M27.15.70
 */

import ts from "typescript";
import { describe, expect, test } from "vitest";
import { registered } from "./support/explanations";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

const THE_ONE_FILE = "src/components/kit/explanation.tsx";

/** Every hand-written tsx file the console draws pages and parts with. */
function screens(): readonly string[] {
  return consoleSourcePaths("src").filter((path) => path.endsWith(".tsx"));
}

function parse(text: string): ts.SourceFile {
  return ts.createSourceFile("synthetic.tsx", text, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TSX);
}

function walk(node: ts.Node, visit: (found: ts.Node) => void): void {
  visit(node);
  ts.forEachChild(node, (child) => {
    walk(child, visit);
  });
}

function tagOf(element: ts.JsxOpeningLikeElement): string {
  return element.tagName.getText();
}

function openings(source: ts.SourceFile): ts.JsxOpeningLikeElement[] {
  const found: ts.JsxOpeningLikeElement[] = [];
  walk(source, (node) => {
    if (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) {
      found.push(node);
    }
  });
  return found;
}

function attributeOf(element: ts.JsxOpeningLikeElement, name: string): ts.JsxAttribute | undefined {
  for (const one of element.attributes.properties) {
    if (ts.isJsxAttribute(one) && one.name.getText() === name) {
      return one;
    }
  }
  return undefined;
}

/** A string literal's text, whether written `"x"` or `{"x"}`. */
function literalOf(attribute: ts.JsxAttribute): string | null {
  const value = attribute.initializer;
  if (value === undefined) {
    return null;
  }
  if (ts.isStringLiteral(value)) {
    return value.text;
  }
  if (ts.isJsxExpression(value) && value.expression !== undefined && ts.isStringLiteralLike(value.expression)) {
    return value.expression.text;
  }
  return null;
}

// ----------------------------------------------------------------------------- the markup is one

/** Every attribute that marks an unavailable control, or a sentence in place of one, in this source. */
export function unavailableMarkupIn(source: ts.SourceFile): string[] {
  const found: string[] = [];
  for (const element of openings(source)) {
    for (const one of element.attributes.properties) {
      if (!ts.isJsxAttribute(one)) {
        continue;
      }
      const name = one.name.getText();
      if (name === "aria-disabled" || name === "data-unavailable") {
        found.push(`${tagOf(element)} ${name}`);
      }
      if (name === "data-slot" && literalOf(one) === "not-offered") {
        found.push(`${tagOf(element)} data-slot="not-offered"`);
      }
    }
  }
  return found;
}

/** Components declared under a name that says they are an unavailable act's stand-in. */
export function standInsDeclaredIn(source: ts.SourceFile): string[] {
  const named = /^(UnavailableAction|NotOffered|ComingSoon\w*|NotAvailable\w*|Inert[A-Z]\w*|Unavailable[A-Z]\w*)$/;
  const found: string[] = [];
  walk(source, (node) => {
    if (ts.isFunctionDeclaration(node) && node.name !== undefined && named.test(node.name.text)) {
      found.push(node.name.text);
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && named.test(node.name.text)) {
      found.push(node.name.text);
    }
  });
  for (const element of openings(source)) {
    if (named.test(tagOf(element))) {
      found.push(`<${tagOf(element)}>`);
    }
  }
  return found;
}

/** Every `Note` that says it is about something not built or not on, which is an explanation. */
export function notesThatExplain(source: ts.SourceFile): string[] {
  const found: string[] = [];
  for (const element of openings(source)) {
    if (tagOf(element) !== "Note") {
      continue;
    }
    const kind = attributeOf(element, "kind");
    if (kind === undefined) {
      continue;
    }
    walk(kind, (node) => {
      if (ts.isStringLiteralLike(node) && (node.text === "soon" || node.text === "not-yet")) {
        found.push(`Note kind ${node.text}`);
      }
    });
  }
  return found;
}

describe("the markup of an unavailable act is written once", () => {
  test("a reading of source finds the markup, the stand-ins and the notes, and none in plain source", () => {
    // What breaks if this is deleted: a detector that finds nothing in real source, which is also what
    // a detector with a mistyped attribute name does, so every sweep below would pass over nothing.
    const found = parse(`const a = <button aria-disabled="true" data-unavailable="" />;
      const b = <p data-slot="not-offered">x</p>;
      const c = <Note kind={ok ? "done" : "not-yet"}>y</Note>;
      function NotOffered() { return <i />; }
      const d = <UnavailableAction />;`);
    expect(unavailableMarkupIn(found)).toEqual([
      "button aria-disabled",
      "button data-unavailable",
      'p data-slot="not-offered"',
    ]);
    expect(notesThatExplain(found)).toEqual(["Note kind not-yet"]);
    expect(standInsDeclaredIn(found).sort()).toEqual(["<UnavailableAction>", "NotOffered"]);
    const plain = parse(`const a = <button disabled={busy}>x</button>; const b = <Note kind="works">y</Note>;`);
    expect(unavailableMarkupIn(plain)).toEqual([]);
    expect(notesThatExplain(plain)).toEqual([]);
    expect(standInsDeclaredIn(plain)).toEqual([]);
  });

  test("only components/kit/explanation.tsx draws an inert control or a not-offered sentence", () => {
    // What breaks if this is deleted: a page that draws its own dashed, inert control, which is the
    // private copy of the component this task removed, and which drifts the day the real one changes.
    const stray = screens()
      .filter((path) => path !== THE_ONE_FILE)
      .flatMap((path) => unavailableMarkupIn(parseConsoleSource(path)).map((one) => `${path}: ${one}`));
    expect(stray).toEqual([]);
    expect(unavailableMarkupIn(parseConsoleSource(THE_ONE_FILE))).toEqual(
      expect.arrayContaining(["Button aria-disabled", "Button data-unavailable", 'p data-slot="not-offered"']),
    );
  });

  test("no component is declared or drawn under another name for an unavailable act", () => {
    // What breaks if this is deleted: `UnavailableAction` or `NotOffered` coming back as a thin wrapper
    // that two pages use and a third forks, which is two components again.
    const stray = screens().flatMap((path) => standInsDeclaredIn(parseConsoleSource(path)).map((one) => `${path}: ${one}`));
    expect(stray).toEqual([]);
  });

  test("no Note leads with coming soon or not available yet, because that is an Explanation", () => {
    // What breaks if this is deleted: the third form of the explanation coming back inside `Note`, with
    // its own colour and its own icon, beside the component that is meant to be the only one.
    const stray = screens().flatMap((path) => notesThatExplain(parseConsoleSource(path)).map((one) => `${path}: ${one}`));
    expect(stray).toEqual([]);
  });
});

// ------------------------------------------------------------------------ every use is served

/** One `Explanation` as it is written: its form, its act, and what it was told. */
interface Use {
  readonly form: string | null;
  readonly acts: readonly string[];
  readonly problems: readonly string[];
}

const FORMS = ["action", "line", "note"];

/** What an expression is, for deciding whether it could be a sentence typed into the page. */
function toldProblem(expression: ts.Expression): string | null {
  if (ts.isStringLiteralLike(expression) || ts.isTemplateExpression(expression)) {
    return "a sentence typed into the page";
  }
  if (ts.isBinaryExpression(expression)) {
    return "a sentence joined from pieces on the page";
  }
  if (ts.isCallExpression(expression)) {
    return "a sentence made by a function on the page";
  }
  if (ts.isIdentifier(expression)) {
    return /^[A-Z][A-Z0-9_]*$/.test(expression.text) ? `the typed constant ${expression.text}` : null;
  }
  if (ts.isPropertyAccessExpression(expression) || ts.isNonNullExpression(expression)) {
    let inner: ts.Expression = expression;
    while (ts.isPropertyAccessExpression(inner) || ts.isNonNullExpression(inner)) {
      inner = inner.expression;
    }
    if (ts.isIdentifier(inner) && /^[A-Z][A-Z0-9_]*$/.test(inner.text)) {
      return `a typed constant's field ${expression.getText()}`;
    }
    return null;
  }
  return `an expression this sweep does not recognise as a field read off data: ${expression.getText()}`;
}

/** The acts an `act` attribute can name: one literal, or the literals of a conditional. */
function actsIn(attribute: ts.JsxAttribute, problems: string[]): string[] {
  const value = attribute.initializer;
  if (value !== undefined && ts.isStringLiteral(value)) {
    return [value.text];
  }
  if (value !== undefined && ts.isJsxExpression(value) && value.expression !== undefined) {
    const expression = value.expression;
    if (ts.isStringLiteralLike(expression)) {
      return [expression.text];
    }
    if (
      ts.isConditionalExpression(expression) &&
      ts.isStringLiteralLike(expression.whenTrue) &&
      ts.isStringLiteralLike(expression.whenFalse)
    ) {
      return [expression.whenTrue.text, expression.whenFalse.text];
    }
  }
  problems.push("act is not a literal, or a choice between two literals");
  return [];
}

export function usesIn(source: ts.SourceFile): Use[] {
  const uses: Use[] = [];
  for (const element of openings(source)) {
    if (tagOf(element) !== "Explanation") {
      continue;
    }
    const problems: string[] = [];
    const formAttribute = attributeOf(element, "form");
    const form = formAttribute === undefined ? null : literalOf(formAttribute);
    if (form === null || !FORMS.includes(form)) {
      problems.push("form is not one of action, line or note, written as a literal");
    }
    const act = attributeOf(element, "act");
    const told = attributeOf(element, "told");
    if ((act === undefined) === (told === undefined)) {
      problems.push("it names exactly one of act and told");
    }
    const acts = act === undefined ? [] : actsIn(act, problems);
    if (told !== undefined) {
      const value = told.initializer;
      if (value === undefined || !ts.isJsxExpression(value) || value.expression === undefined) {
        problems.push("told is not an expression");
      } else {
        const problem = toldProblem(value.expression);
        if (problem !== null) {
          problems.push(`told is ${problem}`);
        }
      }
    }
    if (form === "action" && attributeOf(element, "label") === undefined) {
      problems.push("an action has no label to be named by");
    }
    if (form !== "note" && attributeOf(element, "lead") !== undefined) {
      problems.push("only a note carries a lead");
    }
    uses.push({ form, acts, problems });
  }
  return uses;
}

describe("every explanation is served, in the form it is registered in", () => {
  test("a reading of an Explanation tells a registered act from a typed sentence", () => {
    // What breaks if this is deleted: the reading accepting a literal, a template or a constant for
    // `told`, which is the typed sentence this component exists to stop, with every sweep below green.
    const good = usesIn(parse(`const a = <Explanation form="note" act="agent.overview" />;
      const b = <Explanation form="line" act={x ? "role.not_edited" : "agent.computer_use"} />;
      const c = <Explanation form="action" told={draft.publishUnavailable} label="L" />;
      const d = <Explanation form="note" lead="not-yet" told={one} />;`));
    expect(good.map((one) => one.problems)).toEqual([[], [], [], []]);
    expect(good[1]?.acts).toEqual(["role.not_edited", "agent.computer_use"]);
    const bad = usesIn(parse(`const a = <Explanation form="note" told="Coming soon: x" />;
      const b = <Explanation form="note" told={\`x \${y}\`} />;
      const c = <Explanation form="note" told={NO_GOLDEN} />;
      const d = <Explanation form="note" told={"a" + b} />;
      const e = <Explanation form="note" act="a.b" told={x} />;
      const f = <Explanation form="action" act="a.b" />;
      const g = <Explanation form="note" act={pick()} />;
      const h = <Explanation act="a.b" />;
      const i = <Explanation form="line" lead="soon" act="a.b" />;
      const j = <Explanation form="note" told={TABLE.field} />;`));
    expect(bad.map((one) => one.problems.length > 0)).toEqual([true, true, true, true, true, true, true, true, true, true]);
  });

  test("every Explanation in the console names a registered act in its own form, or is told a field", () => {
    // What breaks if this is deleted: a page naming an act nobody registered (a 404 where its sentence
    // should be), asking for a note where the server registered a control, or typing the sentence
    // into the page again.
    const byAct = new Map(registered().map((one) => [one.act, one.form]));
    const wrong: string[] = [];
    let seen = 0;
    for (const path of screens()) {
      for (const use of usesIn(parseConsoleSource(path))) {
        seen += 1;
        for (const problem of use.problems) {
          wrong.push(`${path}: ${problem}`);
        }
        for (const act of use.acts) {
          const form = byAct.get(act);
          if (form === undefined) {
            wrong.push(`${path}: ${act} is not registered`);
          } else if (form !== use.form) {
            wrong.push(`${path}: ${act} is registered as ${form} and drawn as ${use.form ?? "nothing"}`);
          }
        }
      }
    }
    expect(seen).toBeGreaterThan(40);
    expect(wrong).toEqual([]);
  });

  test("every registered act is drawn by some page, so no sentence is kept that nothing says", () => {
    // What breaks if this is deleted: a sentence in the server's registry that no page draws, which is
    // a statement the product makes to nobody and can go stale unseen.
    const drawn = new Set<string>();
    for (const path of screens()) {
      for (const use of usesIn(parseConsoleSource(path))) {
        for (const act of use.acts) {
          drawn.add(act);
        }
      }
    }
    expect(registered().filter((one) => !drawn.has(one.act)).map((one) => one.act)).toEqual([]);
  });
});

// ------------------------------------------------------- a disabled control has a recorded reason

/** What a transient state reads like: the control is off while something is on its way. */
const TRANSIENT =
  /\b(busy|pending|saving|submitting|fetching|fetchingMore|loading|working|sending|running|asking|confirming|authenticating|marked)\b/;

/** Why a control may be `disabled` for a reason that is not a state of the press. */
export const DISABLED_BECAUSE = Object.freeze({
  PASSED_ON: "the component takes `disabled` as a prop and its caller decides, where it is written and held to this list",
  EDGE: "there is no previous, next or neighbouring item to go to, which is where a control is, not what a reader may do",
  INCOMPLETE: "the form is not complete, or its inputs exclude each other, which the form's own message says",
  LOADING: "the answer the control acts on has not arrived",
  EXPLAINED: "the API says it is not offered, and an Explanation beside the control says why",
});

/**
 * Every `disabled` control that is not transient, by file and expression. **A new one is a decision**:
 * a control that is off because the install cannot do the act, or the reader may not, is an
 * `Explanation`, which says why; `disabled` is for the reasons here, each of which a person can see
 * from the control's own surroundings.
 */
export const DISABLED_FOR: Readonly<Record<string, string>> = Object.freeze({
  "src/components/CredentialField.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/components/DataTable.tsx::!canGoBack": DISABLED_BECAUSE.EDGE,
  "src/components/DataTable.tsx::!hasNext": DISABLED_BECAUSE.EDGE,
  "src/components/RoutingSettings.tsx::wholeCompany": DISABLED_BECAUSE.INCOMPLETE,
  "src/components/kit/ConnectFlow.tsx::index === 0": DISABLED_BECAUSE.EDGE,
  "src/components/kit/formTemplates.tsx::disabled === true || readonly === true": DISABLED_BECAUSE.PASSED_ON,
  "src/components/kit/formTemplates.tsx::off || !hasMoveUp": DISABLED_BECAUSE.EDGE,
  "src/components/kit/formTemplates.tsx::off || !hasMoveDown": DISABLED_BECAUSE.EDGE,
  "src/components/kit/formTemplates.tsx::off": DISABLED_BECAUSE.PASSED_ON,
  "src/components/kit/formTemplates.tsx::given?.props?.disabled === true": DISABLED_BECAUSE.PASSED_ON,
  "src/components/kit/formTemplates.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/components/kit/formTemplates.tsx::disabled || readonly": DISABLED_BECAUSE.PASSED_ON,
  "src/components/kit/formTemplates.tsx::enumDisabled?.includes(one.value) === true": DISABLED_BECAUSE.PASSED_ON,
  "src/components/kit/SavedFilters.tsx::fullForThisName": DISABLED_BECAUSE.EDGE,
  "src/components/kit/WizardSteps.tsx::index === 0": DISABLED_BECAUSE.EDGE,
  "src/pages/agent-templates/TemplateTransfer.tsx::reading.unavailable !== \"\" && !reading.withdrawn": DISABLED_BECAUSE.EXPLAINED,
  "src/pages/AskDictation.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/pages/AskProject.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/pages/AskStart.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/pages/AskStarters.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/pages/FirstRun.tsx::at === 0": DISABLED_BECAUSE.EDGE,
  "src/pages/agents/AgentLeash.tsx::to === chosen.rung": DISABLED_BECAUSE.INCOMPLETE,
  "src/pages/agents/AutomationAuthoring.tsx::one.notOffered !== null": DISABLED_BECAUSE.EXPLAINED,
  "src/pages/connectors/ConnectorsPage.tsx::page === null": DISABLED_BECAUSE.LOADING,
  "src/pages/connectors/CustomConnectorsPage.tsx::entity.fields.length === 1": DISABLED_BECAUSE.INCOMPLETE,
  "src/pages/connectors/LarkFlow.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
  "src/pages/connectors/LarkFlow.tsx::guide.scopes.length === 0": DISABLED_BECAUSE.EDGE,
  "src/pages/skills/SkillForms.tsx::agent === undefined": DISABLED_BECAUSE.INCOMPLETE,
  "src/pages/skills/SkillForms.tsx::file !== null": DISABLED_BECAUSE.INCOMPLETE,
  "src/pages/staff-sources/ConnectDrawer.tsx::disabled": DISABLED_BECAUSE.PASSED_ON,
});

/** The `disabled` attributes in this source that are not a transient state, as the text of each expression. */
export function disabledForReasonsOtherThanTime(source: ts.SourceFile): string[] {
  const found: string[] = [];
  for (const element of openings(source)) {
    const attribute = attributeOf(element, "disabled");
    const value = attribute?.initializer;
    if (value === undefined || !ts.isJsxExpression(value) || value.expression === undefined) {
      continue;
    }
    const text = value.expression.getText();
    if (!TRANSIENT.test(text)) {
      found.push(text);
    }
  }
  return found;
}

describe("a control is disabled only for a reason this file names", () => {
  test("a reading of a disabled control tells a transient state from any other", () => {
    // What breaks if this is deleted: a reading that counts every `disabled` as transient, after which
    // a control switched off for a reason of the reader's would pass unlisted for ever.
    const found = parse(`const a = <Button disabled={busy || asking !== null} />;
      const b = <Button disabled={!reader.mayChange} />;
      const c = <Button disabled />;
      const d = <input disabled={saving} />;`);
    expect(disabledForReasonsOtherThanTime(found)).toEqual(["!reader.mayChange"]);
  });

  test("every disabled control that is not waiting on something is listed with the reason it is disabled", () => {
    // What breaks if this is deleted: a control disabled because the install cannot do an act, or the
    // reader may not, with no sentence saying so, which is the thing the task is about. A new one is
    // listed here, and the list is where a reviewer decides whether it should be an Explanation.
    const unlisted: string[] = [];
    const seen = new Set<string>();
    for (const path of screens()) {
      if (path.startsWith("src/components/ui/") || path === THE_ONE_FILE) {
        continue;
      }
      for (const expression of disabledForReasonsOtherThanTime(parseConsoleSource(path))) {
        const key = `${path}::${expression}`;
        seen.add(key);
        if (!(key in DISABLED_FOR)) {
          unlisted.push(key);
        }
      }
    }
    expect(unlisted).toEqual([]);
    expect([...seen].length).toBeGreaterThan(15);
    expect(Object.keys(DISABLED_FOR).filter((key) => !seen.has(key))).toEqual([]);
    for (const why of Object.values(DISABLED_FOR)) {
      expect(Object.values(DISABLED_BECAUSE)).toContain(why);
    }
  });

  test("a control listed as explained has an Explanation in the file that draws it", () => {
    // What breaks if this is deleted: a control listed as explained after the sentence beside it was
    // removed, which leaves a disabled option nobody can choose and nothing says why (it was so for the
    // automation form's not-offered trigger until 2026-10-15, when only the chosen one showed its reason).
    const explained = Object.entries(DISABLED_FOR).filter(([, why]) => why === DISABLED_BECAUSE.EXPLAINED);
    expect(explained.length).toBeGreaterThan(0);
    for (const [key] of explained) {
      const path = key.split("::")[0] ?? "";
      expect(usesIn(parseConsoleSource(path)).length, key).toBeGreaterThan(0);
    }
  });
});
