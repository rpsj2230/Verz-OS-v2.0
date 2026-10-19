/**
 * The console asks who can reach something of a role over a scope, and of one record only through
 * the view that opens for a reader who can already see it.
 *
 * `docs/admin-console-architecture.md` 4.4: the reverse question, "who can reach X and why", is
 * asked of a capability and a scope and never of a record, because the answer to "who can see this
 * invoice" confirms the invoice exists. The owner decided on 2026-09-18 to have one record access
 * view on one condition, that it opens only for somebody who can already see the record, and
 * `docs/needs-rupash.md` item 188 asks whether M27.15.62's wording, which says no screen may answer
 * it, should be narrowed to that. **This file does not decide that and asserts nothing either way
 * about whether the view exists.** It holds what is true under both answers: the console has exactly
 * the reach questions it declares, the role question takes no subject, and the record question is
 * built in one place and drawn in one place, beneath the rows of the same entity the reader is already
 * looking at. `tests/unit/test_reach_questions.py` is the same rule over the routes.
 *
 * **What it reads.** Every string and template literal in the console's source that is an API path
 * naming a holders, access, audience or readers question, found by the syntax tree, so a path quoted
 * in a comment satisfies nothing. A new one is a failure until it is declared here, which is the point
 * of declaring: a new "who can see this" screen is a decision a person made.
 *
 * **What it cannot see.** A path assembled at run time from parts none of which names the question.
 * That is why the route half derives its set from the served document and not from the console.
 *
 * Task ids: M27.15.62
 */

import ts from "typescript";
import { describe, expect, test } from "vitest";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

/** The paths that name a who-can-reach question: holders, a record's access, an audience, readers. */
export const REACH_PATH = /(?:\/holders\b|\/access(?:[?/]|$)|\/audience\b|\/readers\b|\/who-can)/u;

/** Every such path the console builds, as written, and what it is asked of. */
export const DECLARED_REACH_PATHS: Readonly<Record<string, string>> = {
  "/agents/${encodeURIComponent(agentId)}/audience":
    "one agent, for the people who administer it: the departments and named people it is offered to, which is a setting they keep and not a reach computed for a person",
  "/govern/roles/holders": "a role, over the scope each grant carries; takes no subject",
  "/records/${encodeURIComponent(entity)}/access?filter=${term}":
    "one record, for a reader who can already see it; the API answers anybody else as an entity that is not there",
};

/** The one place the record view's path is built, and the one file that may use it. */
export const RECORD_VIEW_BUILDER = "recordAccessApiPath";
export const RECORD_VIEW_DEFINED_IN = "src/pages/recordsQuery.ts";
export const RECORD_VIEW_DRAWN_IN = "src/pages/Records.tsx";

interface Hit {
  readonly key: string;
  readonly where: string;
}

function everyNode(source: ts.SourceFile): ts.Node[] {
  const nodes: ts.Node[] = [];
  const visit = (node: ts.Node): void => {
    nodes.push(node);
    node.forEachChild(visit);
  };
  source.forEachChild(visit);
  return nodes;
}

/** The text of a path literal as written, with each `${...}` kept as source text. */
function pathText(node: ts.Node, source: ts.SourceFile): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isTemplateExpression(node)) {
    return node.getText(source).slice(1, -1);
  }
  return null;
}

/** Every API path in the console's source that names a who-can-reach question. */
export function reachPathsWritten(): Hit[] {
  const hits: Hit[] = [];
  for (const file of consoleSourcePaths("src")) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      const text = pathText(node, source);
      if (text !== null && text.startsWith("/") && REACH_PATH.test(text)) {
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: text, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

/** Every file that names an identifier, with how it is used there. */
function usesOf(name: string): { file: string; node: ts.Identifier }[] {
  const found: { file: string; node: ts.Identifier }[] = [];
  for (const file of consoleSourcePaths("src")) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if (ts.isIdentifier(node) && node.text === name) {
        found.push({ file, node });
      }
    }
  }
  return found;
}

describe("who can reach what, as the console asks it", () => {
  test("the console builds exactly the who-can-reach paths it declares", () => {
    // What breaks if this is deleted: a new screen asking who can see a document or an invoice, which
    // would arrive with every other test green because nothing compared the console's paths to a list.
    const written = [...new Set(reachPathsWritten().map((one) => one.key))].sort();
    expect(written).toEqual(Object.keys(DECLARED_REACH_PATHS).sort());
  });

  test("the reading finds the paths it should, and says what each is asked of", () => {
    // What breaks if this is deleted: the reading finding nothing after a rename, after which the
    // test above compares an empty set with a declared one and the declared one is the failure, or,
    // worse, both are emptied together.
    expect(reachPathsWritten().length).toBeGreaterThanOrEqual(Object.keys(DECLARED_REACH_PATHS).length);
    for (const [path, askedOf] of Object.entries(DECLARED_REACH_PATHS)) {
      expect(askedOf.split(" ").length, `${path} is declared without saying what it is asked of`).toBeGreaterThan(5);
    }
    expect(REACH_PATH.test("/documents/abc/readers")).toBe(true);
    expect(REACH_PATH.test("/govern/access-review")).toBe(false);
    expect(REACH_PATH.test("/access-requests")).toBe(false);
  });

  test("the role question takes no subject: nothing is joined to its path", () => {
    // What breaks if this is deleted: `${HOLDERS_API_PATH}/${documentId}`, the role question quietly
    // turned into one about a thing. Each use must be the whole path handed on or passed as an
    // argument, never part of a template or a sum.
    for (const name of ["HOLDERS_API_PATH"]) {
      const uses = usesOf(name);
      expect(uses.length, `${name} is not used, so the question is not asked`).toBeGreaterThan(0);
      for (const { file, node } of uses) {
        const parent = node.parent;
        const joined =
          ts.isTemplateSpan(parent) ||
          (ts.isBinaryExpression(parent) && parent.operatorToken.kind === ts.SyntaxKind.PlusToken);
        expect(joined, `${file}: ${node.getText()} is joined to something`).toBe(false);
      }
    }
  });

  test("the record view's path is built in one place and used from one file", () => {
    // What breaks if this is deleted: a second page offering "who can see this" beside a row it has
    // not asked the API about, which is the confirmation of existence the rule is about.
    const uses = usesOf(RECORD_VIEW_BUILDER).filter((one) => !ts.isImportSpecifier(one.node.parent));
    const files = [...new Set(uses.map((one) => one.file))].sort();
    expect(files).toEqual([RECORD_VIEW_DEFINED_IN, RECORD_VIEW_DRAWN_IN].sort());
  });

  test("the record view is drawn only beneath the rows of the same entity, keyed by it", () => {
    // What breaks if this is deleted: the view moved above the rows, or drawn where no entity has
    // been named, so a reader is offered "who can see it" before they have looked at any record.
    const source = parseConsoleSource(RECORD_VIEW_DRAWN_IN);
    const drawn = everyNode(source).filter(
      (node): node is ts.JsxSelfClosingElement => ts.isJsxSelfClosingElement(node) && node.tagName.getText(source) === "RecordAccess",
    );
    expect(drawn).toHaveLength(1);
    const view = drawn[0];
    if (view === undefined) {
      throw new Error("unreachable");
    }
    const fragment = view.parent;
    expect(ts.isJsxFragment(fragment)).toBe(true);
    const siblings = (fragment as ts.JsxFragment).children
      .filter((one): one is ts.JsxSelfClosingElement => ts.isJsxSelfClosingElement(one))
      .map((one) => one.tagName.getText(source));
    expect(siblings).toEqual(["RecordRows", "RecordAccess"]);
    const keyed = view.attributes.properties.some(
      (one) => ts.isJsxAttribute(one) && one.name.getText(source) === "key" && one.initializer?.getText(source).includes("entity") === true,
    );
    expect(keyed, "the view is not keyed by the entity").toBe(true);
    // And it sits on the branch where an entity was named, never on the branch where none was.
    const conditional = fragment.parent;
    expect(ts.isConditionalExpression(conditional) || (ts.isParenthesizedExpression(conditional) && ts.isConditionalExpression(conditional.parent))).toBe(true);
  });
});
