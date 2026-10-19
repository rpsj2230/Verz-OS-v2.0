/**
 * Every screen reports a failed request through the one failure component, and none words, heads or
 * references a failure for itself.
 *
 * `ui/FailureNotice.tsx` is where a failure is drawn: it tells a Brain that could not be reached from
 * one that refused, shows the reference a person can quote, says when none came back, and offers a
 * fresh sign-in when a second factor is needed. `kit/states.tsx` `FailureState` is its frame for the
 * kit. `tests/screen-states.test.tsx` holds what each page draws when a request fails on arrival. What
 * it cannot hold is a write that fails afterwards, because that is drawn by whatever the page's author
 * wrote, and on 2026-10-14 twelve of them were a paragraph of `failure.message` under a red class: no
 * reference, no heading, no unreachable case, no way to sign in again, and the same words as the
 * `screen-states` rule would have refused on arrival.
 *
 * **Four things are refused, each as a property of the syntax tree** (`support/typescript.ts` says why
 * a tree and not a search):
 *
 * 1. Reading `.message` or `.traceId` of an `ApiFailure` in a page, a component or the layout. A
 *    failure is handed whole to `FailureNotice` or `FailureState`; taking its sentence out is how a
 *    private copy begins.
 * 2. A `traceId` attribute on `<Notice>` outside `ui/FailureNotice.tsx`. That is a failure drawn by
 *    hand with its reference, which is the component's job.
 * 3. A failure heading typed out as a string literal outside `ui/FailureNotice.tsx`. Seven screens
 *    had each typed `Something did not work`, and eight each typed `The Brain could not be reached`,
 *    so a heading reworded in one place was reworded in none of the others.
 * 4. A component of its own declared to draw a failure: a function component whose name is a failure,
 *    a problem or a refusal and whose props take an `ApiFailure`.
 *
 * **What is allowed, and why each is not a gap.** Each entry says what the code draws instead. An entry
 * that no longer names a violation fails, so the list cannot outlive its reason.
 *
 * **What this cannot see.** A failure turned into a string somewhere other than a `.message` read, and a
 * sentence a server already worded. Neither is a failure being drawn.
 *
 * Task ids: M27.15.72
 */

import { describe, expect, test } from "vitest";
import ts from "typescript";
import { consoleSourcePaths, parseConsoleSource } from "./support/typescript";

/** The directories whose files draw a screen. `ui` and `api` are the shared parts themselves. */
export const SCREEN_DIRECTORIES = ["src/pages", "src/components", "src/layout"] as const;

/** The file that is the one failure component, which may do all four things. */
export const THE_FAILURE_COMPONENT = "src/ui/FailureNotice.tsx";

/**
 * The kit's frame around the one component: `FailureState` is `FailureNotice` in a `data-slot` wrapper
 * and says so in its own docstring, and is the only component of a screen directory allowed to take
 * an `ApiFailure` by that name.
 */
export const THE_KIT_FRAME = "src/components/kit/states.tsx";

/** The headings a failure is given. Typed out anywhere but the component, each is a private copy. */
export const FAILURE_HEADINGS: readonly string[] = [
  "That did not work",
  "Something did not work",
  "The Brain could not be reached",
  "This needs a sign-in with a second factor",
];

/**
 * Reads of a failure's words that are not a failure being drawn, keyed `file line-text` as
 * `readsOfAFailuresWords` spells them, and what each draws instead.
 */
export const NOT_A_FAILURE_DRAWN: Readonly<Record<string, string>> = {
  "src/pages/knowledge/addForms.tsx result.failure.message":
    "A batch of files is told one line per file, each naming the file and why it was not queued. One line per " +
    "file in a list is the answer, and a heading and a reference under each of thirty files would bury it; " +
    "the sentence is the API's own and every other failure on the page goes through the failure component.",
  "src/pages/connectors/CustomConnectorsPage.tsx result.failure.message":
    "A review that was refused is told as one entry of the form's own list of problems, drawn by " +
    "ui/FieldProblems.tsx beside the field it is about, which is where a refused field is meant to be said.",
};

/** A `<Notice traceId=...>` that is not a failure, and what it is. */
export const NOT_A_FAILURE_NOTICE: Readonly<Record<string, string>> = {
  "src/pages/Ask.tsx":
    "A frame inside an open answer stream says the answer failed and carries the reference of the stream. " +
    "There is no response, so there is no ApiFailure to hand to the failure component; the notice draws " +
    "the same reference line the component does, and tests/ask-page.test.tsx holds it.",
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

const FAILURE_VALUE = /(^|\.)[a-zA-Z]*[fF]ailure$/u;

function screenFiles(): string[] {
  return SCREEN_DIRECTORIES.flatMap((directory) => consoleSourcePaths(directory));
}

/** Every read of `.message` or `.traceId` on something named for a failure, in the screen files. */
export function readsOfAFailuresWords(): Hit[] {
  const hits: Hit[] = [];
  for (const file of screenFiles()) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if (
        ts.isPropertyAccessExpression(node) &&
        (node.name.text === "message" || node.name.text === "traceId") &&
        FAILURE_VALUE.test(node.expression.getText(source))
      ) {
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: `${file} ${node.getText(source)}`, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

/** Every `<Notice traceId=...>` in the screen files: a failure drawn by hand with its reference. */
export function noticesWithAReference(): Hit[] {
  const hits: Hit[] = [];
  for (const file of screenFiles()) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if (
        (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) &&
        node.tagName.getText(source) === "Notice" &&
        node.attributes.properties.some((one) => ts.isJsxAttribute(one) && one.name.getText(source) === "traceId")
      ) {
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: file, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

/** Every string literal in `src` that is exactly a failure heading, outside the failure component. */
export function typedOutHeadings(): Hit[] {
  const hits: Hit[] = [];
  for (const file of consoleSourcePaths("src")) {
    if (file === THE_FAILURE_COMPONENT) {
      continue;
    }
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && FAILURE_HEADINGS.includes(node.text)) {
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: `${file} ${node.text}`, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

/** Every function component of a screen file that is named for a failure and takes an `ApiFailure`. */
export function privateFailureComponents(): Hit[] {
  const hits: Hit[] = [];
  for (const file of screenFiles().filter((one) => one !== THE_KIT_FRAME)) {
    const source = parseConsoleSource(file);
    for (const node of everyNode(source)) {
      if (!ts.isFunctionDeclaration(node) || node.name === undefined || !/^[A-Z]/u.test(node.name.text)) {
        continue;
      }
      const named = /(Failure|Problem|Refus|Failed)/u.test(node.name.text);
      const takes = node.parameters.some((one) => one.getText(source).includes("ApiFailure"));
      if (named && takes) {
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        hits.push({ key: `${file} ${node.name.text}`, where: `${file}:${String(line)}` });
      }
    }
  }
  return hits;
}

const keys = (hits: readonly Hit[]): string[] => [...new Set(hits.map((one) => one.key))];

describe("every failure is drawn by the one failure component", () => {
  test("no screen takes the words or the reference out of a failure to draw them itself", () => {
    // What breaks if this is deleted: a write that fails drawn as `failure.message` under a red
    // class, which shows no reference, no heading and no way to sign in again, as twelve did on
    // 2026-10-14 while every page-level failure test was green.
    const found = readsOfAFailuresWords().filter((one) => !(one.key in NOT_A_FAILURE_DRAWN));
    expect(found.map((one) => `${one.key} (${one.where})`)).toEqual([]);
  });

  test("every allowed read of a failure's words is still written", () => {
    // What breaks if this is deleted: the allowlist outliving the line it excuses, so it excuses a
    // line somebody writes next.
    const written = keys(readsOfAFailuresWords());
    for (const [key, reason] of Object.entries(NOT_A_FAILURE_DRAWN)) {
      expect(written, `${key} is allowed and is no longer written`).toContain(key);
      expect(reason.split(" ").length, `${key} is allowed without a reason`).toBeGreaterThan(15);
    }
  });

  test("the reading finds the reads it should, so the rule above is read over a real list", () => {
    // What breaks if this is deleted: the reading finding nothing after a rename, after which the
    // first test passes over an empty list. The allowed reads are real `.message` reads of a
    // failure, so the reading must find them.
    expect(keys(readsOfAFailuresWords())).toEqual(expect.arrayContaining(Object.keys(NOT_A_FAILURE_DRAWN)));
  });

  test("no screen draws a notice with a reference of its own", () => {
    // What breaks if this is deleted: a failure drawn by hand with its trace id, which is the
    // component's job and the thing a hand-drawn copy forgets when the reference is missing.
    const found = noticesWithAReference().filter((one) => !(one.key in NOT_A_FAILURE_NOTICE));
    expect(found.map((one) => one.where)).toEqual([]);
    const written = keys(noticesWithAReference());
    for (const [file, reason] of Object.entries(NOT_A_FAILURE_NOTICE)) {
      expect(written, `${file} is allowed and no longer draws one`).toContain(file);
      expect(reason.split(" ").length, `${file} is allowed without a reason`).toBeGreaterThan(15);
    }
  });

  test("a failure heading is typed out in one file and nowhere else", () => {
    // What breaks if this is deleted: the eight copies of `The Brain could not be reached` and
    // seven of `Something did not work` coming back one at a time, each a heading that is reworded
    // in one place and not in the others.
    expect(typedOutHeadings().map((one) => `${one.key} (${one.where})`)).toEqual([]);
  });

  test("the failure component itself holds every heading, so the rule above is not vacuous", () => {
    // What breaks if this is deleted: a heading renamed in the component so it no longer matches the
    // list, after which the sweep above searches for words nothing writes.
    const source = parseConsoleSource(THE_FAILURE_COMPONENT);
    const literals = everyNode(source)
      .filter((node): node is ts.StringLiteral => ts.isStringLiteral(node))
      .map((node) => node.text);
    for (const heading of FAILURE_HEADINGS) {
      expect(literals, heading).toContain(heading);
    }
  });

  test("no screen declares a component of its own for drawing a failure", () => {
    // What breaks if this is deleted: a `FailureBanner` written inside a page, which is the shape
    // the twenty private copies took before 2026-09-17.
    expect(privateFailureComponents().map((one) => `${one.key} (${one.where})`)).toEqual([]);
  });
});
