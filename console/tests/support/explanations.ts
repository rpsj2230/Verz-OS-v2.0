/**
 * The sentences the API serves for an act the console cannot offer, read from the server's own
 * registry rather than typed into a test.
 *
 * `brain.console.explanations.EXPLANATIONS` is what `GET /console/explanations/{act}` serves, and
 * `scripts/export-openapi.py` writes it to `src/api/generated/explanations.json` beside the API
 * document. **A test that asserts a page shows a sentence reads it here**, because until
 * 2026-10-15 the console held the sentence as a constant and a test compared the page with the
 * same constant it imported: change the words and both sides moved together. Now the words are
 * the server's, so the comparison is between a page and a document the page did not write.
 *
 * `fakeIdentityProvider` (in `auth.ts`) answers the route from this file when a test has not
 * answered it itself, which is what lets every page mount in a test without each one stubbing a
 * request it is not about. A test about a failed read overrides it with its own answer.
 *
 * Like `openapi.ts`, the file is generated and not committed, and a missing one throws with the
 * command that produces it rather than answering nothing and turning every assertion built on it
 * into a comparison between two empty things.
 *
 * Task ids: M27.15.70
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect } from "vitest";
import { apiDocument } from "./openapi";
import { CONSOLE_ROOT } from "./repo";

const DOCUMENT = "src/api/generated/explanations.json";

/** One registered explanation, as the exporter writes it (`retired_by` stays on the server's side of the wire). */
export interface Registered {
  readonly act: string;
  readonly form: "action" | "line" | "note";
  readonly lead: "" | "soon" | "not-yet";
  readonly sentence: string;
  readonly retired_by: string;
}

let held: readonly Registered[] | null = null;

/** Every registered explanation. Throws when the file has not been generated. */
export function registered(): readonly Registered[] {
  if (held !== null) {
    return held;
  }
  const full = join(CONSOLE_ROOT, ...DOCUMENT.split("/"));
  if (!existsSync(full)) {
    throw new Error(
      `${DOCUMENT} is not there, so no test can say what an explanation reads. ` +
        "Run `npm run api:schema`, which needs no running server.",
    );
  }
  const read = JSON.parse(readFileSync(full, "utf8")) as readonly Registered[];
  if (read.length === 0) {
    throw new Error(`${DOCUMENT} holds no explanation, which would make every assertion built on it vacuous.`);
  }
  held = read;
  return read;
}

/** The explanation registered for an act. Throws for one nobody registered. */
export function explanationFor(act: string): Registered {
  const found = registered().find((one) => one.act === act);
  if (found === undefined) {
    throw new Error(`No explanation is registered for ${act}.`);
  }
  return found;
}

/** The sentence an act is served with, lead excluded (a note's lead is drawn beside it). */
export function sentenceFor(act: string): string {
  return explanationFor(act).sentence;
}

/** Where the route is, as the stand-in API sees the path. */
export const EXPLANATIONS_ADDRESS = "/api/v1/console/explanations/";

/**
 * The body the route answers for one act, or null for one nobody registered. The same fields as
 * `brain.explanation_routes.ExplanationView`, and not `retired_by`.
 */
export function servedBody(act: string): { act: string; form: string; lead: string; sentence: string } | null {
  const found = registered().find((one) => one.act === act);
  return found === undefined ? null : { act: found.act, form: found.form, lead: found.lead, sentence: found.sentence };
}

/**
 * The expression whose match against a route's path means the explanation's act now has a route.
 * Python and JavaScript read these patterns the same way (groups, `\b`, `\{`, `[^}]+`), and a pattern
 * that one reads and the other does not would throw here rather than match nothing.
 */
export function retiringPattern(act: string): RegExp {
  const pattern = explanationFor(act).retired_by;
  if (pattern === "") {
    throw new Error(`${act} has no expiry, so there is no route that retires it.`);
  }
  return new RegExp(pattern);
}

/** Every explanation that has an expiry, by act. */
export function actsWithAnExpiry(): readonly string[] {
  return registered()
    .filter((one) => one.retired_by !== "")
    .map((one) => one.act);
}

/**
 * That no route the API document lists matches the expiry of any of these acts, so no page is
 * still saying "coming soon" about something that has landed. `tests/unit/test_console_explanations.py`
 * holds the same against every registered act; a console module names its own here so the failure
 * is read where the control is drawn.
 */
export function noRouteRetires(acts: readonly string[]): void {
  const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
  for (const act of acts) {
    const pattern = retiringPattern(act);
    expect(
      paths.filter((path) => pattern.test(path)),
      act,
    ).toEqual([]);
  }
}
