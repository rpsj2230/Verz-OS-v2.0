/**
 * A control that deletes says which act it is, and the interface never sends a hard delete.
 *
 * `docs/admin-console-architecture.md` rule R4: "every 'delete' in the interface is retire, end,
 * disconnect, switch off, withdraw, detach or supersede, and says which; hard deletes only where
 * designed." `tests/destructive-confirmed.test.ts` holds the other half of the same sentence, that a
 * destructive write is asked about first and that the question says what will happen. Neither said
 * what the button is called, and on 2026-10-14 the first run of this file found thirty-four labels
 * that said only that something would go: `Remove` beside a person's grant, `Delete` beside a
 * memory that is in fact retired and stays on the record, `Take it out` beside an agent in a group
 * chat. A person asked to press `Remove` has to guess whether it is the grant that goes, the person
 * or the record, and the product's whole rule is that it is the grant that is withdrawn, the person
 * who stays and the record that is kept.
 *
 * **Four properties, each read from the syntax tree** (`support/typescript.ts` says why a tree):
 *
 * 1. No string a person reads starts with a generic verb for removing: delete, remove, discard,
 *    erase, destroy, purge, wipe, drop, or take-it-out, take-it-off, take-away. A label, a
 *    confirmation's question, an accessible name and a menu item are all strings that start with
 *    the verb, so one rule over every string literal and JSX text catches all four.
 * 2. The console sends no `DELETE`. Every removal is a retirement a route records, which is why
 *    `tests/unit/test_hard_deletes.py` can derive the six tables the application may delete from and
 *    none of them is reachable from a button here.
 * 3. Every one of the seven acts is the label of some confirmation, so the sweep above cannot pass
 *    by there being no destructive control at all.
 * 4. No confirmation is answered with a bare word: OK, Yes, Confirm, Continue.
 *
 * **What is allowed, and why each is not a gap.** A control that edits a draft in the browser, a row of
 * a form not yet saved, removes nothing that is stored, and its words are the form library's. Each
 * entry says so, and an entry that no longer names a string fails, so the list cannot outlive its
 * reason.
 *
 * **What this cannot see.** A label assembled from parts at run time, and a label that names an act
 * wrongly: `Retire` over a control that hard-deletes would pass, which is why the other half is a
 * derivation of what the database lets the application delete, and not a reading of words.
 *
 * Task ids: M27.15.52, M27.8.4
 */

import ts from "typescript";
import { describe, expect, test } from "vitest";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";
import { everyConfirmation, everyWrite } from "./support/writes";

/** The seven acts the requirement names, as the words a label leads with. */
export const THE_SEVEN_ACTS: readonly string[] = ["Retire", "End", "Disconnect", "Switch off", "Withdraw", "Detach", "Supersede"];

/** The generic verbs for removing, which say that something goes and not which act it is. */
export const GENERIC_REMOVAL =
  /^\s*(Delete|Remove|Discard|Erase|Destroy|Purge|Wipe|Drop|Take (?:it |them |this |that |these |him |her )?(?:\w+ )?(?:off|out|away)|Take out|Take away)\b/u;

/** An answer to a confirmation that says nothing about the act. */
export const BARE_ANSWER = /^\s*(OK|Okay|Yes|No|Confirm|Continue|Proceed|Sure|Are you sure\??)\s*$/iu;

/** The directories whose strings a person reads. */
const SCREEN_DIRECTORIES = ["src/pages", "src/components", "src/layout"] as const;

/**
 * Strings that begin with a generic verb and are not a delete of anything stored, keyed
 * `file text`, with the reason.
 */
export const EDITS_OF_AN_UNSAVED_DRAFT: Readonly<Record<string, string>> = {
  "src/components/formWords.ts Remove":
    "The library's remove button beside one entry of a list inside a form that has not been sent. It " +
    "drops a row from the browser's copy of the form and sends nothing, and every screen with such a " +
    "list names the entry beside it for a screen reader.",
  "src/pages/connectors/CustomConnectorsPage.tsx Remove":
    "The column heading, read only by a screen reader, over the button that drops one field row from a " +
    "definition being written. Nothing is stored until the definition is submitted for review.",
  "src/pages/connectors/CustomConnectorsPage.tsx Remove field ":
    "The accessible name of the button that drops one field row from a definition being written, in " +
    "the browser's copy only; nothing is stored until the definition is submitted for review.",
  "src/components/ProcedureCanvas.tsx Remove this test":
    "Drops one test from a procedure step being drawn on the canvas, in the browser's copy of the " +
    "drawing. The procedure is saved as a draft only by its own save, which is confirmed.",
  "src/components/ProcedureCanvas.tsx Remove":
    "Drops a step from the procedure being drawn, in the browser's copy of the drawing. The " +
    "procedure is saved as a draft only by its own save, which is confirmed.",
  "src/pages/agents/agentCoauthorQuery.ts Drop these suggestions":
    "Sets aside the co-author's suggestions the person has not taken. They are held in the browser and " +
    "were never written to the draft, which is why taking them is the confirmed act.",
};

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

function screenFiles(): string[] {
  return SCREEN_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory));
}

/** The text a node contributes to what a person reads, or null when it contributes none. */
function readableText(node: ts.Node): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateHead(node)) {
    return node.text;
  }
  if (ts.isJsxText(node)) {
    return node.text.trim();
  }
  return null;
}

/** Every readable string that begins with a generic removal verb. */
export function genericRemovals(): Hit[] {
  const hits: Hit[] = [];
  for (const file of screenFiles()) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      const text = readableText(node);
      if (text !== null && GENERIC_REMOVAL.test(text)) {
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: `${file} ${text}`, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

/** Every top-level string a name is bound to, or an object's string values, across the screen files. */
function namedStrings(): ReadonlyMap<string, readonly string[]> {
  const found = new Map<string, string[]>();
  const add = (name: string, values: readonly string[]): void => {
    found.set(name, [...(found.get(name) ?? []), ...values]);
  };
  const stringsIn = (node: ts.Node): string[] => {
    const values: string[] = [];
    const visit = (one: ts.Node): void => {
      if (ts.isStringLiteral(one) || ts.isNoSubstitutionTemplateLiteral(one)) {
        values.push(one.text);
      }
      one.forEachChild(visit);
    };
    visit(node);
    return values;
  };
  for (const file of screenFiles()) {
    const source = parseConsoleSource(file);
    for (const statement of source.statements) {
      if (!ts.isVariableStatement(statement)) {
        continue;
      }
      for (const declaration of statement.declarationList.declarations) {
        if (ts.isIdentifier(declaration.name) && declaration.initializer !== undefined) {
          add(declaration.name.text, stringsIn(declaration.initializer));
        }
      }
    }
  }
  return found;
}

/** Every string a confirmation's `confirmLabel` can be, following names to what they are bound to. */
export function confirmationLabels(): string[] {
  const named = namedStrings();
  const labels: string[] = [];
  for (const one of everyConfirmation()) {
    const label = one.attributes["confirmLabel"];
    if (label === undefined || label === null) {
      continue;
    }
    const visit = (node: ts.Node): void => {
      if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
        labels.push(node.text);
        return;
      }
      if (ts.isTemplateExpression(node)) {
        labels.push(node.head.text);
      }
      if (ts.isIdentifier(node)) {
        labels.push(...(named.get(node.text) ?? []));
      }
      if (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) {
        if (ts.isIdentifier(node.expression)) {
          labels.push(...(named.get(node.expression.text) ?? []));
        }
      }
      node.forEachChild(visit);
    };
    visit(label);
  }
  return labels;
}

const keys = (hits: readonly Hit[]): string[] => [...new Set(hits.map((one) => one.key))];

describe("a control that deletes says which act it is", () => {
  test("no string a person reads begins with a generic verb for removing", () => {
    // What breaks if this is deleted: `Remove` beside a person's grant, `Delete` beside a memory that
    // is retired, `Take it out` beside an agent in a chat: a button that says something goes and not
    // which of the seven acts it is, so a person cannot tell the grant from the person from the record.
    const found = genericRemovals().filter((one) => !(one.key in EDITS_OF_AN_UNSAVED_DRAFT));
    expect(found.map((one) => `${one.key} (${one.where})`)).toEqual([]);
  });

  test("every excused string is still written, and still argues why it deletes nothing stored", () => {
    // What breaks if this is deleted: the allowlist outliving the line it excuses, so it excuses
    // whatever somebody writes there next.
    const written = keys(genericRemovals());
    for (const [key, reason] of Object.entries(EDITS_OF_AN_UNSAVED_DRAFT)) {
      expect(written, `${key} is excused and is no longer written`).toContain(key);
      expect(reason.split(" ").length, `${key} is excused without a reason`).toBeGreaterThan(15);
    }
  });

  test("the reading finds generic verbs where they are, so the rule above is read over a real list", () => {
    // What breaks if this is deleted: the reading finding nothing after a rename, after which the
    // first test passes over an empty list. The excused strings are real, so it must find them all.
    expect(keys(genericRemovals())).toEqual(expect.arrayContaining(Object.keys(EDITS_OF_AN_UNSAVED_DRAFT)));
  });

  test("the pattern refuses the generic verbs and lets the seven acts through", () => {
    // What breaks if this is deleted: the pattern edited into one that matches nothing, or into one
    // that matches `Retire`, either of which leaves the rule above satisfied by its own docstring.
    for (const refused of ["Delete", "Remove the grant", "Take it out", "Take it off", "Take out", "Discard this", "Erase"]) {
      expect(GENERIC_REMOVAL.test(refused), refused).toBe(true);
    }
    for (const allowed of [...THE_SEVEN_ACTS, "Retire the pack", "Withdraw the grant", "Detach it", "Removed", "Revoke key"]) {
      expect(GENERIC_REMOVAL.test(allowed), allowed).toBe(false);
    }
  });

  test("the console sends no DELETE: every removal is a retirement a route records", () => {
    // What breaks if this is deleted: a button that sends a hard delete, which the database would
    // refuse for every table but six, and which would fail as a 500 on the install rather than at
    // review. `tests/unit/test_hard_deletes.py` holds the six; this holds that none is a button.
    const writes = everyWrite();
    expect(writes.length).toBeGreaterThan(50);
    expect(writes.filter((one) => one.method === "DELETE").map((one) => one.key)).toEqual([]);
    expect(new Set(writes.map((one) => one.method))).toContain("POST");
  }, 60_000);

  test("each of the seven acts is the label of some confirmation", () => {
    // What breaks if this is deleted: the sweep above passing because no control names an act at
    // all. A rename that dropped `Detach` from the whole console would leave it green otherwise.
    const labels = confirmationLabels();
    expect(labels.length).toBeGreaterThan(100);
    for (const act of THE_SEVEN_ACTS) {
      expect(
        labels.some((label) => label === act || label.startsWith(`${act} `)),
        `no confirmation is labelled ${act}`,
      ).toBe(true);
    }
  }, 60_000);

  test("no confirmation is answered with a bare word", () => {
    // What breaks if this is deleted: a confirmation whose button reads OK, which is a second click
    // and not a statement of what the press does.
    expect(confirmationLabels().filter((label) => BARE_ANSWER.test(label))).toEqual([]);
    expect(BARE_ANSWER.test("OK")).toBe(true);
    expect(BARE_ANSWER.test("Retire the pack")).toBe(false);
  }, 60_000);
});
